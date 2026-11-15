#!/usr/bin/env python3
"""
A股全市场单日行情数据采集脚本

拉取指定日期所有A股股票的行情数据（涨跌幅、成交额、换手率等所有可获取字段），
支持任意历史日期，输出 JSON 文件。

用法:
    python fetch_market_data.py 20260820 [output_dir] [--workers 20]

参数:
    日期        - 目标日期，格式 YYYYMMDD（任意历史交易日）
    output_dir  - 输出目录，默认 ../concept/
    --workers   - 并发线程数，默认 20

数据源策略（多数据源互补）:
    主数据源: 腾讯历史日K  proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get
              - 支持任意历史日期
              - 字段: 开/高/低/收/量/换手率/成交额
              - 直接 HTTP 并发请求，全市场约 2-3 分钟
    增强数据源: 腾讯实时快照 ak.stock_zh_a_spot_tx()
              - 仅当目标日期 == 最新交易日时生效
              - 附加字段: 市盈率TTM/市净率/总市值/流通市值/量比/主力净流入/多周期涨跌幅/股票名称
    备选数据源: 新浪历史日K  ak.stock_zh_a_daily()
              - 腾讯日K失败时回退
              - 附加字段: 流通股本

衍生字段（由日K计算）:
    涨跌幅、涨跌额、振幅、前收盘

说明:
    - 目标日期将自动回看前14天以取得前一交易日收盘价，计算涨跌幅
    - 全市场约 5500 只，20 并发约 2-3 分钟
    - 输出为单日快照，文件名带日期，不覆盖历史
"""

import sys
import os
import json
import time
import argparse
import warnings
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import pandas as pd

warnings.filterwarnings("ignore")

try:
    import akshare as ak
except ImportError:
    print("缺少依赖 akshare，请先执行: pip install akshare", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
    "Referer": "https://gu.qq.com/",
}


# ============================================================
# 工具函数
# ============================================================

def _num(v, default=None, ndigits=2):
    """安全转 float"""
    try:
        x = float(v)
        if pd.isna(x):
            return default
        if ndigits is None:
            return x
        return round(x, ndigits)
    except (TypeError, ValueError):
        return default


def _norm_date(d):
    """统一日期为 YYYYMMDD 无连字符格式"""
    return str(d).replace('-', '').replace('/', '')[:8]


def _to_6digit(code):
    """统一代码为6位数字"""
    c = str(code).strip()
    if c.lower().startswith(('sh', 'sz', 'bj')) and len(c) >= 8:
        return c[-6:]
    return c[-6:] if len(c) >= 6 else c


def _to_tx_symbol(code):
    """6位代码 -> 腾讯格式 sh600519/sz000001/bj920000"""
    code = _to_6digit(code)
    if code.startswith(('60', '68', '90', '51', '58', '50')):
        return f"sh{code}"
    if code.startswith(('00', '30', '20', '15', '16')):
        return f"sz{code}"
    if code.startswith(('92', '83', '87', '43')):
        return f"bj{code}"
    return f"sh{code}"


def _to_sina_symbol(code):
    """6位代码 -> 新浪格式 sz000001/sh600519/bj920000"""
    return _to_tx_symbol(code)


# ============================================================
# 数据获取（腾讯日K - 主数据源，原始HTTP并发）
# ============================================================

def fetch_tx_kline_raw(symbol, start_date, end_date):
    """
    腾讯历史日K原始HTTP请求，返回 [(date, open, close, high, low, volume, turnover, amount), ...]
    使用 proxy.finance.qq.com 端点，一次请求可覆盖多年，支持任意历史日期。
    """
    start_year = int(start_date[:4])
    end_year = int(end_date[:4]) + 1
    url = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
    # 腾讯接口要求按年请求，这里请求从 start_year 到 end_year 的数据
    params = {
        "_var": f"kline_day{start_year}",
        "param": f"{symbol},day,{start_year}-01-01,{end_year}-12-31,640,",
        "r": "0.8205512681390605",
    }
    r = requests.get(url, params=params, headers=HEADERS, timeout=10)
    r.raise_for_status()
    text = r.text
    # 解析 JSON（去掉 "kline_day2026=" 前缀）
    if "=" in text:
        text = text[text.find("=") + 1:]
    data = json.loads(text)
    stock_data = data["data"][symbol]
    # day 或 qfqday/hfqday
    for key in ("day", "qfqday", "hfqday"):
        if key in stock_data:
            kline = stock_data[key]
            break
    else:
        return []
    # 每行: [date, open, close, high, low, volume, {}, turnover, amount, ...]
    # 索引:   0      1     2      3     4    5      6   7        8
    # amount 单位为万元
    rows = []
    for line in kline:
        if len(line) < 8:
            continue
        date = _norm_date(line[0])
        if start_date <= date <= end_date:
            open_ = _num(line[1], ndigits=None)
            close = _num(line[2], ndigits=None)
            high = _num(line[3], ndigits=None)
            low = _num(line[4], ndigits=None)
            volume = _num(line[5], ndigits=None)          # 手
            turnover = _num(line[7], ndigits=None)        # 换手率(%)
            amount_wan = _num(line[8], ndigits=None)      # 成交额(万元)
            amount = amount_wan * 10000 if amount_wan is not None else None  # 成交额(元)
            rows.append((date, open_, close, high, low, volume, turnover, amount))
    # 按日期排序
    rows.sort(key=lambda x: x[0])
    return rows


def get_all_codes():
    """获取全市场A股代码列表（东财→新浪→本地 ths_stock_info.json 兜底）"""
    # 1. 东方财富实时快照（快且全）
    try:
        df = ak.stock_zh_a_spot_em()
        codes = [_to_6digit(c) for c in df['代码'].tolist()]
        if codes:
            return codes
    except Exception as e:
        print(f"  [WARN] 东财代码列表获取失败: {e}", file=sys.stderr)
    # 2. 新浪实时快照
    try:
        df = ak.stock_zh_a_spot()
        codes = [_to_6digit(c) for c in df['代码'].tolist()]
        if codes:
            return codes
    except Exception as e:
        print(f"  [WARN] 新浪代码列表获取失败: {e}", file=sys.stderr)
    # 3. 本地个股信息表兜底（data/meta/ths_stock_info.json，约 5500 只）
    try:
        info_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "data", "meta", "ths_stock_info.json")
        with open(info_path, encoding="utf-8") as f:
            info = json.load(f)
        codes = [_to_6digit(c) for c in (info.get("stocks") or {}).keys()]
        if codes:
            print(f"  [INFO] 使用本地 ths_stock_info.json 作为代码列表 (共 {len(codes)} 只)", file=sys.stderr)
            return codes
    except Exception as e:
        print(f"  [WARN] 本地代码列表兜底失败: {e}", file=sys.stderr)
    return []


def build_item(date, row, prev_row, code):
    """由日K行构建个股 dict（含涨跌幅/成交额/换手率）"""
    open_, close, high, low = row[1], row[2], row[3], row[4]
    volume, turnover, amount = row[5], row[6], row[7]
    prev_close = prev_row[2] if prev_row else None

    item = {
        "code": code,
        "date": f"{date[:4]}-{date[4:6]}-{date[6:]}",
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,          # 成交量(手)
        "amount": amount,          # 成交额(元)
        "turnover": turnover,       # 换手率
    }
    # 衍生字段
    if prev_close and prev_close != 0:
        item["prev_close"] = round(prev_close, 2)
        item["change"] = round((close - prev_close), 2) if close is not None else None
        item["change_pct"] = round((close - prev_close) / prev_close * 100, 2)
        if high is not None and low is not None:
            item["amplitude"] = round((high - low) / prev_close * 100, 2)
    return item


def enrich_with_spot(item, spot_map):
    """用腾讯实时快照增强字段（市盈率/市净率/市值/量比/主力净流入/多周期涨跌幅）"""
    s = spot_map.get(item["code"])
    if not s:
        return item
    item["name"] = s.get("name")
    item["pe_ttm"] = s.get("pe_ttm")
    item["pb"] = s.get("pb")
    item["total_mv"] = s.get("total_mv")      # 总市值(亿元)
    item["float_mv"] = s.get("float_mv")      # 流通市值(亿元)
    item["volume_ratio"] = s.get("volume_ratio")  # 量比
    item["speed"] = s.get("speed")                # 涨速(%)
    item["main_net_inflow"] = s.get("main_net_inflow")  # 主力净流入(万元)
    item["pct_5d"] = s.get("pct_5d")
    item["pct_10d"] = s.get("pct_10d")
    item["pct_20d"] = s.get("pct_20d")
    item["pct_60d"] = s.get("pct_60d")
    item["pct_ytd"] = s.get("pct_ytd")
    item["pct_52w"] = s.get("pct_52w")
    item["stock_type"] = s.get("stock_type")
    return item


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="A股全市场单日行情数据采集")
    parser.add_argument("date", help="目标日期 YYYYMMDD")
    parser.add_argument("output_dir", nargs="?", default=None, help="输出目录")
    parser.add_argument("--workers", type=int, default=20, help="并发线程数")
    args = parser.parse_args()

    date_str = args.date
    output_dir = (
        args.output_dir
        or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "concept")
    )
    workers = args.workers

    # 回看前14天以取得前一交易日昨收
    target_dt = datetime.strptime(date_str, "%Y%m%d")
    start_date = (target_dt - timedelta(days=14)).strftime("%Y%m%d")
    end_date = date_str

    print(f"🎯 目标日期: {date_str} (并发 {workers} 线程)")
    print("📋 获取全市场股票代码列表...")
    codes = get_all_codes()
    if not codes:
        print("❌ 无法获取股票代码列表", file=sys.stderr)
        sys.exit(1)
    print(f"    共 {len(codes)} 只A股")

    # 判断目标日期是否为最新交易日（用于附加实时全字段增强）
    is_latest = (date_str == datetime.now().strftime("%Y%m%d"))
    spot_map = {}
    if is_latest:
        try:
            spot_df = ak.stock_zh_a_spot_em()
            for _, r in spot_df.iterrows():
                c = _to_6digit(r.get('代码'))
                spot_map[c] = {
                    "name": str(r.get('名称', '')).strip(),
                    "pe_ttm": _num(r.get('市盈率-动态')),
                    "pb": _num(r.get('市净率')),
                    "total_mv": _num(r.get('总市值'), ndigits=None),
                    "float_mv": _num(r.get('流通市值'), ndigits=None),
                    "volume_ratio": _num(r.get('量比')),
                    "speed": _num(r.get('涨速')),
                    "main_net_inflow": None,
                    "pct_5d": None,
                    "pct_10d": None,
                    "pct_20d": None,
                    "pct_60d": _num(r.get('60日涨跌幅')),
                    "pct_ytd": _num(r.get('年初至今涨跌幅')),
                    "pct_52w": None,
                    "stock_type": '',
                }
            print(f"    ⚡ 目标日期为最新交易日，将附加实时全字段增强")
        except Exception as e:
            print(f"  [WARN] 东财实时快照获取失败(不影响历史日K): {e}", file=sys.stderr)

    print(f"⏳ 开始逐股拉取腾讯历史日K（{len(codes)} 只）...")
    t0 = time.time()

    results = []
    failed = []
    succeed = 0

    def worker(code):
        symbol = _to_tx_symbol(code)
        try:
            rows = fetch_tx_kline_raw(symbol, start_date, end_date)
            if not rows:
                return (None, None)
            # 找到目标日期及其前一交易日
            dates = [r[0] for r in rows]
            if date_str in dates:
                idx = dates.index(date_str)
                row = rows[idx]
                prev_row = rows[idx - 1] if idx > 0 else None
                return (row, prev_row)
            return (None, None)
        except Exception:
            return (None, None)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(worker, c): c for c in codes}
        done = 0
        for future in as_completed(futures):
            done += 1
            code = futures[future]
            try:
                row, prev_row = future.result()
                if row is None:
                    failed.append(code)
                    continue
                item = build_item(date_str, row, prev_row, code)
                if is_latest and code in spot_map:
                    item = enrich_with_spot(item, spot_map)
                results.append(item)
                succeed += 1
            except Exception:
                failed.append(code)
            if done % 500 == 0 or done == len(codes):
                el = time.time() - t0
                print(f"    进度 {done}/{len(codes)} | 成功 {len(results)} | 失败 {len(failed)} | 用时 {el:.0f}s")

    elapsed = time.time() - t0
    print(f"\n✅ 拉取完成: 成功 {len(results)} 只 | 失败 {len(failed)} 只 | 用时 {elapsed:.0f}s")

    # 构建输出
    output = {
        "meta": {
            "description": "A股全市场单日行情数据快照",
            "trade_date": date_str,
            "total": len(results),
            "failed": len(failed),
            "failed_codes": failed[:100],
            "sources": {
                "tx_hist": succeed,
                "tx_spot_enhance": len(spot_map) if is_latest else 0,
            },
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "stocks": results,
    }

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"market_data_{date_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"✅ 数据已保存到: {path}")

    # 输出样例
    if results:
        print("\n=== 样例（第1只）===")
        print(json.dumps(results[0], ensure_ascii=False, indent=2))

    return path


if __name__ == "__main__":
    main()