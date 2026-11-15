#!/usr/bin/env python3
"""
葛南维均线评分 — 每日数据采集 & 批量打分脚本
================================================
功能：
    1. 自动读取 data/concept/limit_up_down_data.json 最新交易日的涨停股清单
       （或 --codes 手动指定股票代码）
    2. 用 akshare 拉取每只股票的日线收盘价历史（前复权，避免除权缺口干扰均线）
    3. 计算 MA5 / MA10 / MA20 / MA30 / MA60
    4. 调用 granville_scorer.granville_score 葛南维八大法则打分
    5. 结果落盘 data/stocks/granville/{YYYYMMDD}.json（按日期缓存，可每日执行）

用法：
    python3 scripts/fetch_granville_data.py                    # 最新交易日涨停股全量
    python3 scripts/fetch_granville_data.py --top 20           # 仅封单金额前 20
    python3 scripts/fetch_granville_data.py --codes 000017,301218   # 指定代码
    python3 scripts/fetch_granville_data.py --all-dates        # 对历史每个交易日依次打分

输出：
    data/stocks/granville/{YYYYMMDD}.json
    {
      "date": "20260828", "generated_at": "...", "stock_count": 65,
      "stocks": [ { code, name, close, ma5..ma60, score, rating, suggestion, signals, details }, ... ]  # 按分数降序
    }

依赖：
    pip install akshare pandas   （与 fetch_limit_data.py 相同环境）

数据源：
    ak.stock_zh_a_daily()   新浪-个股日K（前复权，主源；部分网络环境东财 push2his 不可达）
    ak.stock_zh_a_hist()    东方财富-个股日K（前复权，备用源）
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# 让同目录下的 granville_scorer 可被 import
sys.path.insert(0, str(Path(__file__).resolve().parent))
from granville_scorer import granville_score  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIMIT_DATA_FILE = PROJECT_ROOT / "data" / "concept" / "limit_up_down_data.json"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data" / "stocks" / "granville"

MA_WINDOWS = [5, 10, 20, 30, 60]
# 拉取日线的历史长度（自然日）：MA60 需 ≥60 个交易日 ≈ 85 个自然日，留余量取 200
LOOKBACK_CALENDAR_DAYS = 200
# 相邻请求间隔（秒），对数据源友好
REQUEST_INTERVAL = 0.35


def load_limit_up_stocks(date: str = ""):
    """从 limit_up_down_data.json 读取指定交易日（默认最新）的涨停股清单。"""
    if not LIMIT_DATA_FILE.exists():
        raise FileNotFoundError(f"未找到 {LIMIT_DATA_FILE}，请先执行 make fetch-limit-info")
    data = json.loads(LIMIT_DATA_FILE.read_text(encoding="utf-8"))
    days = data.get("data") or {}
    if not days:
        raise ValueError("limit_up_down_data.json 中无数据")
    if not date:
        date = sorted(days.keys())[-1]
    if date not in days:
        raise ValueError(f"日期 {date} 不在数据中，可用: {sorted(days.keys())[-3:]}")
    stocks = (days[date] or {}).get("limit_up_stocks") or []
    return date, stocks


def _sina_symbol(code: str) -> str:
    """6位纯代码 → 新浪带市场前缀代码（sz000017 / sh600519）。北交所暂不支持。"""
    c = str(code).strip().lower()
    if c.startswith(("sh", "sz", "bj")):
        return c
    if c.startswith(("60", "68", "90", "11", "51")):
        return f"sh{c}"
    if c.startswith(("00", "30", "20", "12", "15")):
        return f"sz{c}"
    return f"bj{c}"


def fetch_daily_closes(ak, code: str, end_date: str):
    """
    拉取个股前复权日线收盘价序列（升序）。返回 (dates, closes) 或 (None, None)。

    主源：新浪 ak.stock_zh_a_daily()（当前网络环境东财 push2his 不可达）；
    备源：东财 ak.stock_zh_a_hist()。任一成功即返回。
    """
    start = (datetime.strptime(end_date, "%Y%m%d") - timedelta(days=LOOKBACK_CALENDAR_DAYS)).strftime("%Y%m%d")
    last_err = None

    # 主源：新浪
    try:
        df = ak.stock_zh_a_daily(symbol=_sina_symbol(code), start_date=start, end_date=end_date, adjust="qfq")
        if df is not None and not df.empty:
            dates = df["date"].astype(str).tolist()
            closes = df["close"].astype(float).tolist()
            return dates, closes
    except Exception as e:  # noqa: BLE001
        last_err = e

    # 备源：东财
    try:
        df = ak.stock_zh_a_hist(symbol=str(code).strip(), period="daily", start_date=start, end_date=end_date, adjust="qfq")
        if df is not None and not df.empty:
            dates = df["日期"].astype(str).tolist()
            closes = df["收盘"].astype(float).tolist()
            return dates, closes
    except Exception as e:  # noqa: BLE001
        last_err = e

    if last_err:
        raise last_err
    return None, None


def compute_mas(closes):
    """按 MA_WINDOWS 计算各周期均线（用最后 N 个收盘价的均值）。数据不足返回 None。"""
    mas = {}
    for w in MA_WINDOWS:
        if len(closes) < w:
            return None
        mas[w] = sum(closes[-w:]) / w
    return mas


def score_one(ak, code: str, name: str, end_date: str):
    """拉数据 + 算均线 + 打分。返回结果 dict（失败/数据不足时带 error/skip 字段）。"""
    try:
        dates, closes = fetch_daily_closes(ak, code, end_date)
    except Exception as e:  # noqa: BLE001
        return {"code": code, "name": name, "error": f"日线获取失败: {e}"}
    if not closes:
        return {"code": code, "name": name, "error": "日线数据为空（可能已退市/代码错误）"}

    mas = compute_mas(closes)
    close = closes[-1]
    if mas is None:
        return {
            "code": code,
            "name": name,
            "close": round(close, 2),
            "trade_days": len(closes),
            "skip": f"上市时间不足，仅 {len(closes)} 个交易日（MA60 需要 60）",
        }

    result = granville_score(
        name=name, code=code, close=close,
        ma5=mas[5], ma10=mas[10], ma20=mas[20], ma30=mas[30], ma60=mas[60],
        verbose=False,
    )
    return {
        "code": code,
        "name": name,
        "close": round(close, 2),
        "ma5": round(mas[5], 2), "ma10": round(mas[10], 2),
        "ma20": round(mas[20], 2), "ma30": round(mas[30], 2),
        "ma60": round(mas[60], 2),
        "ma5_slope": round((mas[5] - mas[10]) / mas[10] * 100, 2),
        "spread_5_20": round((mas[5] - mas[20]) / mas[20] * 100, 2),
        "score": result["score"],
        "rating": result["rating"],
        "suggestion": result["suggestion"],
        "signals": result["signals"],
        "details": result["details"],
    }


def run_date(ak, date: str, stocks, out_dir: Path, quiet=False) -> Path:
    """对某交易日的涨停股批量打分并落盘。返回输出文件路径。"""
    out = {
        "date": date,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "akshare.stock_zh_a_daily(qfq)/stock_zh_a_hist(qfq)",
        "stock_count": len(stocks),
        "stocks": [],
        "skipped": [],
        "errors": [],
    }
    for i, s in enumerate(stocks, 1):
        code, name = s.get("code", ""), s.get("name", "")
        r = score_one(ak, code, name, date)
        if "error" in r:
            out["errors"].append(r)
        elif "skip" in r:
            out["skipped"].append(r)
        else:
            out["stocks"].append(r)
        if not quiet:
            tag = r.get("score", "?")
            print(f"  [{i}/{len(stocks)}] {name}({code}) → {tag}分"
                  + (f" [{r['rating']}]" if "rating" in r else
                     f" [跳过: {r.get('skip', r.get('error', ''))}]" if ("skip" in r or "error" in r) else ""))
        time.sleep(REQUEST_INTERVAL)

    out["stocks"].sort(key=lambda x: x["score"], reverse=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{date}.json"
    out_file.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # 控制台摘要
    scored = out["stocks"]
    print(f"\n{'=' * 70}")
    print(f"  葛南维均线评分汇总 — {date}　打分 {len(scored)} 只 / 跳过 {len(out['skipped'])} / 失败 {len(out['errors'])}")
    print(f"  输出: {out_file}")
    print("=" * 70)
    if scored:
        top = scored[:15]
        print(f"  {'排名':<4}{'名称':<10}{'代码':<10}{'收盘':>8}{'MA5':>8}{'MA20':>8}{'MA60':>8}{'分数':>6}  评级")
        for i, r in enumerate(top, 1):
            print(f"  {i:<4}{r['name']:<10}{r['code']:<10}{r['close']:>8.2f}"
                  f"{r['ma5']:>8.2f}{r['ma20']:>8.2f}{r['ma60']:>8.2f}{r['score']:>6}  {r['rating']}")
        if len(scored) > 15:
            print(f"  … 其余 {len(scored) - 15} 只见 JSON 文件")
    return out_file


def main():
    parser = argparse.ArgumentParser(description="葛南维均线评分 — 每日数据采集 & 批量打分")
    parser.add_argument("--codes", help="手动指定股票代码，逗号分隔（如 000017,301218），默认读最新交易日涨停股")
    parser.add_argument("--top", type=int, help="仅取封单金额前 N 只（默认全部）")
    parser.add_argument("--date", help="指定交易日 YYYYMMDD（默认数据里最新一天，且为拉取日线的截止日）")
    parser.add_argument("--all-dates", action="store_true", help="对数据中每个交易日依次打分（第一次补历史用）")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT_DIR), help="输出目录，默认 data/stocks/granville")
    args = parser.parse_args()

    try:
        import akshare as ak  # noqa: F401
    except ImportError:
        print("缺少依赖：pip3 install akshare pandas", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output_dir)

    if args.codes:
        # 手动指定代码模式
        date = args.date or datetime.now().strftime("%Y%m%d")
        stocks = [{"code": c.strip(), "name": c.strip()} for c in args.codes.split(",") if c.strip()]
        run_date(ak, date, stocks, out_dir)
        return

    # 默认：读涨停股清单
    dates = []
    if args.all_dates:
        if not LIMIT_DATA_FILE.exists():
            print(f"未找到 {LIMIT_DATA_FILE}", file=sys.stderr)
            sys.exit(1)
        dates = sorted((json.loads(LIMIT_DATA_FILE.read_text(encoding="utf-8")).get("data") or {}).keys())
    else:
        dates = [args.date] if args.date else [None]

    for d in dates:
        day, stocks = load_limit_up_stocks(d or "")
        if args.top:
            stocks = sorted(stocks, key=lambda s: s.get("seal_amount") or 0, reverse=True)[: args.top]
        print(f"\n▶ {day}：{len(stocks)} 只涨停股开始葛南维打分…")
        run_date(ak, day, stocks, out_dir)


if __name__ == "__main__":
    main()
