#!/usr/bin/env python3
"""
A股市场综合情绪数据采集脚本
采集最近N个交易日的涨跌停、指数、资金、连板进阶、权重板块等数据，输出JSON文件

用法:
    python fetch_limit_data.py [N] [output_dir]

参数:
    N          - 最近N个交易日，默认10
    output_dir - 输出目录，默认 ../concept/

依赖:
    pip install akshare pandas

数据来源:
    - 涨停板: ak.stock_zt_pool_em()           东方财富-涨停股池
    - 跌停板: ak.stock_zt_pool_dtgc_em()      东方财富-跌停股池
    - 炸板:   ak.stock_zt_pool_zbgc_em()      东方财富-炸板股池
    - 指数日线: ak.stock_zh_index_daily()      新浪-指数日K
    - 融资余额: ak.macro_china_market_margin_sh/sz()  上交所/深交所融资融券
    - 北向资金: ak.stock_hsgt_fund_flow_summary_em()  东方财富-沪深港通资金流向
    - 行业板块: ak.stock_board_industry_summary_ths() 同花顺-行业板块
    - 交易日:   ak.tool_trade_date_hist_sina()        新浪交易日历
"""

import akshare as ak
import pandas as pd
import numpy as np
import json
import sys
import os
import time
import argparse
import ast
import csv
import io
import subprocess
from datetime import datetime
from pathlib import Path
from collections import defaultdict


# ============================================================
# 工具函数
# ============================================================

def get_recent_trade_dates(n_days=10):
    """获取最近N个交易日日期列表"""
    df = ak.tool_trade_date_hist_sina()
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    today = pd.Timestamp.now().normalize()
    recent = df[df['trade_date'] <= today].tail(n_days)
    return recent['trade_date'].dt.strftime('%Y%m%d').tolist()


def safe_call(func, *args, **kwargs):
    """安全调用函数，失败返回None"""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        print(f"    [WARN] {func.__name__} 失败: {e}", file=sys.stderr)
        return None


def fmt_date(date_str):
    """YYYYMMDD -> YYYY-MM-DD"""
    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"


# ============================================================
# 指数数据（均线、涨跌幅、成交量）
# ============================================================

INDEX_MAP = {
    "sh000001": {"name": "上证指数", "code": "sh000001"},
    "sz399001": {"name": "深证成指", "code": "sz399001"},
    "sz399006": {"name": "创业板指", "code": "sz399006"},
}


def fetch_index_data(trade_dates):
    """获取三大指数的日线数据，计算均线、涨跌幅、成交量"""
    index_data = {}
    for symbol, info in INDEX_MAP.items():
        df = safe_call(ak.stock_zh_index_daily, symbol=symbol)
        if df is None:
            continue
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date').sort_index()

        # 计算5日、10日均线
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma10'] = df['close'].rolling(10).mean()

        # 计算单日涨跌幅
        df['pct_change'] = df['close'].pct_change() * 100

        for d in trade_dates:
            dt = pd.Timestamp(d)
            if dt not in df.index:
                continue
            row = df.loc[dt]
            if d not in index_data:
                index_data[d] = {}
            index_data[d][info['name']] = {
                "close": round(float(row['close']), 2),
                "pct_change": round(float(row.get('pct_change', np.nan)), 2) if pd.notna(row.get('pct_change')) else None,
                "volume": int(row['volume']) if pd.notna(row['volume']) else None,
                "ma5": round(float(row['ma5']), 2) if pd.notna(row.get('ma5')) else None,
                "ma10": round(float(row['ma10']), 2) if pd.notna(row.get('ma10')) else None,
            }
    return index_data


# ============================================================
# 融资余额
# ============================================================

def fetch_margin_data(trade_dates):
    """获取两市融资余额"""
    margin_data = {}
    df_sh = safe_call(ak.macro_china_market_margin_sh)
    df_sz = safe_call(ak.macro_china_market_margin_sz)
    # 注意：akshare 日期列是 datetime.date 对象（非字符串），统一转字符串再比较
    if df_sh is not None:
        df_sh = df_sh.copy()
        df_sh['日期'] = df_sh['日期'].astype(str)
    if df_sz is not None:
        df_sz = df_sz.copy()
        df_sz['日期'] = df_sz['日期'].astype(str)

    for d in trade_dates:
        dt_str = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        entry = {"sh_margin_balance": None, "sz_margin_balance": None, "total_margin_balance": None}

        if df_sh is not None:
            row_sh = df_sh[df_sh['日期'] == dt_str]
            if len(row_sh) > 0:
                entry["sh_margin_balance"] = int(row_sh.iloc[0]['融资余额'])

        if df_sz is not None:
            row_sz = df_sz[df_sz['日期'] == dt_str]
            if len(row_sz) > 0:
                entry["sz_margin_balance"] = int(row_sz.iloc[0]['融资余额'])

        if entry["sh_margin_balance"] and entry["sz_margin_balance"]:
            entry["total_margin_balance"] = entry["sh_margin_balance"] + entry["sz_margin_balance"]

        margin_data[d] = entry
    return margin_data


# ============================================================
# 北向资金
# ============================================================

def fetch_north_flow_data(trade_dates):
    """获取北向资金（陆股通）净买额"""
    north_data = {}
    df = safe_call(ak.stock_hsgt_fund_flow_summary_em)
    if df is None:
        return north_data

    north_df = df[df['资金方向'] == '北向'].copy()
    # 交易日列可能是 datetime.date 对象，统一转字符串再比较
    north_df['交易日'] = north_df['交易日'].astype(str)
    for d in trade_dates:
        dt_str = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        day_data = north_df[north_df['交易日'] == dt_str]
        if len(day_data) == 0:
            continue
        sh_row = day_data[day_data['板块'] == '沪股通']
        sz_row = day_data[day_data['板块'] == '深股通']
        sh_net = float(sh_row.iloc[0]['成交净买额']) if len(sh_row) > 0 else 0
        sz_net = float(sz_row.iloc[0]['成交净买额']) if len(sz_row) > 0 else 0
        north_data[d] = {
            "sh_net_buy": round(sh_net, 2),
            "sz_net_buy": round(sz_net, 2),
            "total_net_buy": round(sh_net + sz_net, 2),
        }
    return north_data


# ============================================================
# 权重板块动向
# ============================================================

def fetch_sector_data(trade_dates):
    """
    获取每个交易日的行业板块涨跌幅排名（前5+后5）。
    通过同花顺行业板块指数日K线接口获取历史数据。
    """
    # 1. 获取所有同花顺行业板块列表
    print("    获取行业板块列表...")
    board_df = safe_call(ak.stock_board_industry_name_ths)
    if board_df is None or len(board_df) == 0:
        return {}

    boards = [(row['name'], row['code']) for _, row in board_df.iterrows()]
    print(f"    共 {len(boards)} 个行业板块，正在获取历史行情...")

    # 2. 对每个板块获取日K线，收集每日涨跌幅
    # daily_changes: {date_str: [{name, change_pct, net_inflow}, ...]}
    daily_changes = defaultdict(list)
    start_date = trade_dates[0]
    end_date = trade_dates[-1]

    for idx, (name, code) in enumerate(boards):
        df = safe_call(ak.stock_board_industry_index_ths,
                       symbol=name,
                       start_date=fmt_date(start_date),
                       end_date=fmt_date(end_date))
        if df is None or len(df) == 0:
            continue

        for _, row in df.iterrows():
            date_str = str(row['日期']).replace('-', '')[:8]
            if date_str not in trade_dates:
                continue
            # 接口不返回涨跌幅，用 (close - open) / open 近似计算
            open_price = row.get('开盘价')
            close_price = row.get('收盘价')
            if open_price is None or close_price is None or pd.isna(open_price) or pd.isna(close_price):
                continue
            change_pct = round(float((close_price - open_price) / open_price * 100), 2)
            daily_changes[date_str].append({
                "name": name,
                "change_pct": change_pct,
            })

        if (idx + 1) % 20 == 0:
            print(f"      进度: {idx+1}/{len(boards)}", file=sys.stderr)

    # 3. 对每个交易日，按涨跌幅排序取 top5 + bottom5
    result = {}
    for date_str in trade_dates:
        sectors = daily_changes.get(date_str, [])
        if not sectors:
            continue
        sectors_sorted = sorted(sectors, key=lambda x: x['change_pct'], reverse=True)
        result[date_str] = {
            "top5": sectors_sorted[:5],
            "bottom5": sectors_sorted[-5:][::-1],  # 跌幅最大的5个，按跌幅从大到小
        }

    return result


# ============================================================
# Wind 选股 + iFinD：涨停股名单及基础信息（可选，需插件环境）
# ============================================================

# 插件脚本位置（有 Wind/iFinD 插件的环境启用，按需修改）
WIND_SKILL_DIR = Path("/app/.agents/plugins/wind-allskill/skills/wind-mcp-skill")
IFIND_TOOL = Path("/app/.agents/plugins/ifind/scripts/ifind_tool.py")


def _run_cmd(cmd, cwd=None, timeout=120):
    """执行外部命令，返回 (returncode, stdout, stderr)。"""
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def _wind_available():
    return WIND_SKILL_DIR.exists() and (WIND_SKILL_DIR / "scripts" / "cli.mjs").exists()


def _ifind_available():
    return IFIND_TOOL.exists()


def fetch_limit_up_list_wind(trade_date):
    """调用 Wind 选股，返回 [{'code','name','limit_status','date','limit_time'}]。"""
    if not _wind_available():
        return []
    question = f"{trade_date}收盘涨停的A股股票"
    params = json.dumps({"question": question}, ensure_ascii=False)
    code, out, err = _run_cmd(
        ["node", "scripts/cli.mjs", "call", "stock_data", "search_stocks", params],
        cwd=str(WIND_SKILL_DIR), timeout=180,
    )
    if code != 0:
        print(f"  [warn] Wind 选股失败: {(err or out).strip()[:200]}", file=sys.stderr)
        return []

    try:
        outer = json.loads(out)
        text1 = outer["content"][0]["text"]
        inner_text = ast.literal_eval(text1)["text"]
        payload = json.loads(inner_text)
        preview = payload.get("data_preview", "")
    except Exception as e:
        print(f"  [warn] Wind 选股结果解析失败: {e}", file=sys.stderr)
        return []

    rows = []
    reader = csv.DictReader(io.StringIO(preview))
    for r in reader:
        status = ""
        for k, v in r.items():
            if k and "涨跌停状态" in k:
                status = (v or "").strip()
        rows.append({
            "code": (r.get("Wind代码") or "").strip(),
            "name": (r.get("证券简称") or "").strip(),
            "limit_status": status,
            "date": (r.get("日期") or "").strip(),
            "limit_time": (r.get("涨跌停时间") or "").strip(),
        })
    return [r for r in rows if r["code"]]


def _ifind_call(api_name, params, timeout=120):
    code, out, err = _run_cmd(
        ["python3", str(IFIND_TOOL), "call", "--api-name", api_name,
         "--params-json", json.dumps(params, ensure_ascii=False)],
        timeout=timeout,
    )
    if code != 0:
        print(f"  [warn] iFinD {api_name} 失败: {(err or out).strip()[:200]}", file=sys.stderr)
        return False
    return True


def _read_csv_flex(path):
    p = Path(path)
    if not p.exists():
        return []
    text = p.read_text(encoding="utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def _batched(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _row_code(row):
    for k in row:
        lk = k.lower()
        if lk in ("ticker", "windcode", "code", "thscode", "股票代码", "证券代码"):
            return (row[k] or "").strip()
    first = next(iter(row.values()), "")
    if isinstance(first, str) and first.strip()[-3:] in (".SH", ".SZ", ".BJ"):
        return first.strip()
    return ""


def fetch_ifind_data(codes, work_dir, with_info=True):
    """按每 3 只一批调用 iFinD 行情与基础信息，返回 {code: {...}}。"""
    if not _ifind_available() or not codes:
        return {}
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    merged = {}

    batches = list(_batched(codes, 3))
    for idx, batch in enumerate(batches, 1):
        tickers = ",".join(batch)
        print(f"  iFinD 批次 {idx}/{len(batches)}: {tickers}")

        price_file = work_dir / f"price_{idx}.csv"
        if _ifind_call("ifind_get_stock_realtime_price",
                       {"ticker": tickers, "file_path": str(price_file)}):
            for row in _read_csv_flex(price_file):
                key = _row_code(row)
                if key:
                    merged.setdefault(key, {}).update(
                        {f"行情_{k}": v for k, v in row.items()})

        if with_info:
            info_file = work_dir / f"info_{idx}.csv"
            if _ifind_call("ifind_get_stock_info",
                           {"ticker": tickers, "file_path": str(info_file)}):
                for row in _read_csv_flex(info_file):
                    key = _row_code(row)
                    if key:
                        merged.setdefault(key, {}).update(
                            {f"信息_{k}": v for k, v in row.items()})
        time.sleep(0.3)
    return merged


def fetch_limit_up_stock_info(date_str, work_dir, with_info=True):
    """
    用 Wind 选股 + iFinD 获取涨停股名单及基础信息（可选功能）。
    返回 list[dict]，插件不存在时返回空列表。
    """
    if not (_wind_available() or _ifind_available()):
        return []

    print(f"  [Wind+iFinD] 采集 {date_str} 涨停股基础信息 ...")
    stocks = fetch_limit_up_list_wind(date_str)
    if not stocks:
        print(f"  [Wind+iFinD] Wind 未返回涨停名单，跳过")
        return []

    info_map = fetch_ifind_data([s["code"] for s in stocks], work_dir, with_info=with_info)

    rows = []
    for s in stocks:
        row = {"代码": s["code"], "名称": s["name"], "日期": s["date"],
               "涨停状态(1=涨停)": s["limit_status"], "涨停时间": s["limit_time"]}
        row.update(info_map.get(s["code"], {}))
        rows.append(row)
    return rows


# ============================================================
# 涨停/跌停/炸板/连板数据
# ============================================================

def _num(v, default=0):
    """安全转 float，NaN/空返回 default"""
    try:
        x = float(v)
        if pd.isna(x):
            return default
        return x
    except (TypeError, ValueError):
        return default


def parse_limit_stock_pool(df):
    """
    将涨停/跌停/炸板股池 DataFrame 解析为简洁的个股明细 dict 数组。
    涨停股池字段: 序号/代码/名称/涨跌幅/最新价/成交额/流通市值/总市值/换手率/
                 封板资金/首次封板时间/最后封板时间/炸板次数/涨停统计/连板数/所属行业
    """
    stocks = []
    if df is None or len(df) == 0:
        return stocks
    for _, row in df.iterrows():
        item = {
            "code": str(row.get('代码', '')).strip(),
            "name": str(row.get('名称', '')).strip(),
            "change_pct": round(_num(row.get('涨跌幅'), 0.0), 2),
            "last_price": round(_num(row.get('最新价'), 0.0), 2),
            "amount": round(_num(row.get('成交额'), 0.0), 0),            # 成交额(元)
            "float_mv": round(_num(row.get('流通市值'), 0.0), 0),        # 流通市值(元)
            "total_mv": round(_num(row.get('总市值'), 0.0), 0),          # 总市值(元)
            "turnover_rate": round(_num(row.get('换手率'), 0.0), 2),     # 换手率(%)
            "board": int(_num(row.get('连板数'), 0)),                    # 连板数
            "industry": str(row.get('所属行业', '')).strip(),            # 所属行业(申万)
        }
        # 涨停股池专属字段（炸板/跌停股池可能没有）
        if '封板资金' in row.index:
            item["seal_amount"] = round(_num(row.get('封板资金'), 0.0), 0)   # 封板资金(元)
        if '首次封板时间' in row.index:
            item["first_limit_time"] = str(row.get('首次封板时间', '')).strip()
        if '炸板次数' in row.index:
            item["blow_times"] = int(_num(row.get('炸板次数'), 0))
        if '涨停统计' in row.index:
            item["limit_stat"] = str(row.get('涨停统计', '')).strip()        # 如 "1/1"
        stocks.append(item)
    return stocks


def fetch_limit_data(date_str):
    """获取单日涨停/跌停/炸板数据（含个股明细）"""
    result = {
        "limit_up_count": 0,
        "limit_down_count": 0,
        "blow_up_count": 0,
        "blow_up_rate": 0.0,
        "max_consecutive_board": 0,
        "max_consecutive_stocks": [],
        "board_distribution": {},  # 连板数分布: {"1": 76, "2": 7, ...}
        "limit_up_stocks": [],     # 涨停个股明细
        "limit_down_stocks": [],   # 跌停个股明细
        "blow_up_stocks": [],      # 炸板个股明细
    }

    try:
        # 涨停板
        zt_df = ak.stock_zt_pool_em(date=date_str)
        result["limit_up_count"] = len(zt_df)
        result["limit_up_stocks"] = parse_limit_stock_pool(zt_df)

        if '连板数' in zt_df.columns and len(zt_df) > 0:
            zt_df['连板数'] = pd.to_numeric(zt_df['连板数'], errors='coerce')
            # 连板数分布
            dist = zt_df['连板数'].value_counts().to_dict()
            result["board_distribution"] = {str(int(k)): int(v) for k, v in dist.items() if pd.notna(k)}

            # 最大连板
            max_board = int(zt_df['连板数'].max())
            if pd.notna(max_board):
                result["max_consecutive_board"] = max_board
                top_stocks = zt_df[zt_df['连板数'] == max_board]
                result["max_consecutive_stocks"] = [
                    f"{row['代码']} {row['名称']}"
                    for _, row in top_stocks.iterrows()
                ]

        # 跌停板
        try:
            dt_df = ak.stock_zt_pool_dtgc_em(date=date_str)
            result["limit_down_count"] = len(dt_df)
            result["limit_down_stocks"] = parse_limit_stock_pool(dt_df)
        except Exception:
            pass

        # 炸板
        try:
            zb_df = ak.stock_zt_pool_zbgc_em(date=date_str)
            result["blow_up_count"] = len(zb_df)
            result["blow_up_stocks"] = parse_limit_stock_pool(zb_df)
            total_attempt = result["limit_up_count"] + result["blow_up_count"]
            if total_attempt > 0:
                result["blow_up_rate"] = round(result["blow_up_count"] / total_attempt * 100, 2)
        except Exception:
            pass

        return result

    except Exception as e:
        print(f"  [WARN] {date_str} 涨跌停数据获取异常: {e}", file=sys.stderr)
        return None


# ============================================================
# 连板进阶统计（1进2、2进3、3进4、4进5）
# ============================================================

def calc_board_progression(prev_date, curr_date):
    """
    计算连板进阶数量。
    思路：获取相邻两天的涨停股池，对比同一只股票在prev_date的连板数N，
    在curr_date的连板数N+1，即为"N进N+1"成功。
    """
    progression = {
        "1to2": 0,
        "2to3": 0,
        "3to4": 0,
        "4to5": 0,
    }

    try:
        prev_df = ak.stock_zt_pool_em(date=prev_date)
        curr_df = ak.stock_zt_pool_em(date=curr_date)
    except Exception:
        return progression

    if '连板数' not in prev_df.columns or '连板数' not in curr_df.columns:
        return progression

    prev_df['连板数'] = pd.to_numeric(prev_df['连板数'], errors='coerce')
    curr_df['连板数'] = pd.to_numeric(curr_df['连板数'], errors='coerce')

    # 构建 prev: {代码: 连板数}
    prev_map = dict(zip(prev_df['代码'], prev_df['连板数']))
    curr_map = dict(zip(curr_df['代码'], curr_df['连板数']))

    for code, prev_board in prev_map.items():
        if pd.isna(prev_board):
            continue
        curr_board = curr_map.get(code)
        if curr_board is None or pd.isna(curr_board):
            continue
        if curr_board == prev_board + 1:
            key = f"{int(prev_board)}to{int(curr_board)}"
            if key in progression:
                progression[key] += 1

    return progression


# ============================================================
# 主流程
# ============================================================

def main():
    ap = argparse.ArgumentParser(description="A股市场综合情绪数据采集")
    ap.add_argument("n_days", nargs="?", type=int, default=10, help="最近N个交易日")
    ap.add_argument("output_dir", nargs="?", default=None, help="输出目录")
    ap.add_argument("--with-stock-info", action="store_true",
                    help="用 Wind+iFinD 采集最新交易日涨停股基础信息")
    ap.add_argument("--no-info", action="store_true",
                    help="跳过 iFinD 个股基础信息，只保留名单+行情")
    ap.add_argument("--work-dir", default="./_ifind_cache",
                    help="iFinD 原始 CSV 缓存目录")
    args = ap.parse_args()

    n_days = args.n_days
    output_dir = args.output_dir or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "concept")

    print(f"正在获取最近 {n_days} 个交易日的A股综合数据...")

    trade_dates = get_recent_trade_dates(n_days)
    print(f"交易日列表: {trade_dates}")

    # 读取已有数据（增量更新）
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "limit_up_down_data.json")
    existing_data = {}
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                old = json.load(f)
                old_data = old.get("data", {})
                if isinstance(old_data, list):
                    for item in old_data:
                        if "date" in item:
                            date_key = item.pop("date")
                            existing_data[date_key] = item
                else:
                    existing_data = old_data
            print(f"已加载 {len(existing_data)} 条历史数据")
        except Exception:
            pass

    # ---- 批量获取指数数据 ----
    print("\n📊 获取三大指数数据...")
    index_data = fetch_index_data(trade_dates)

    # ---- 批量获取融资余额 ----
    print("💰 获取融资余额数据...")
    margin_data = fetch_margin_data(trade_dates)

    # ---- 批量获取北向资金 ----
    print("🌏 获取北向资金数据...")
    north_data = fetch_north_flow_data(trade_dates)

    # ---- 获取行业板块动向（所有交易日） ----
    print("🏭 获取行业板块动向...")
    sector_data = fetch_sector_data(trade_dates)

    # ---- 逐日采集涨跌停 + 连板进阶 ----
    print(f"\n📈 逐日采集涨跌停数据（共 {len(trade_dates)} 天）...")
    new_count = 0
    skip_count = 0

    for i, date_str in enumerate(trade_dates):
        print(f"  [{i+1}/{len(trade_dates)}] {date_str} ...", end=" ")
        daily = fetch_limit_data(date_str)
        if daily is None:
            skip_count += 1
            print("⏭ 跳过")
            continue

        # 合并指数数据
        if date_str in index_data:
            daily["indices"] = index_data[date_str]

        # 合并融资余额
        if date_str in margin_data:
            daily["margin"] = margin_data[date_str]

        # 合并北向资金
        if date_str in north_data:
            daily["north_flow"] = north_data[date_str]

        # 合并权重板块（每一天）
        if date_str in sector_data:
            daily["sectors"] = sector_data[date_str]

        # 连板进阶（需要前一天数据）
        if i > 0:
            prev_date = trade_dates[i - 1]
            daily["board_progression"] = calc_board_progression(prev_date, date_str)

        existing_data[date_str] = daily
        new_count += 1

        print(f"涨停:{daily['limit_up_count']} 跌停:{daily['limit_down_count']} "
              f"炸板率:{daily['blow_up_rate']}% 连板:{daily['max_consecutive_board']}")

    # ---- 涨停股基础信息（可选，Wind + iFinD）----
    if args.with_stock_info and trade_dates:
        latest = trade_dates[-1]
        info_rows = fetch_limit_up_stock_info(
            latest, args.work_dir, with_info=not args.no_info)
        if info_rows:
            existing_data.setdefault(latest, {})
            existing_data[latest]["limit_up_stock_info"] = info_rows
            print(f"  ✅ 已写入 {latest} 涨停股信息 {len(info_rows)} 只")
        else:
            print(f"  [INFO] {latest} 涨停股信息为空（插件缺失或非交易日）")

    # 按日期排序
    sorted_data = dict(sorted(existing_data.items()))

    output = {
        "meta": {
            "description": "A股市场综合情绪数据（含指数、资金、连板进阶、权重板块、周期判断）",
            "data_range": f"{trade_dates[0]} ~ {trade_dates[-1]}",
            "total_trading_days": len(sorted_data),
            "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        },
        "data": sorted_data,
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 本次新增/更新 {new_count} 条，跳过 {skip_count} 条，共 {len(sorted_data)} 条")
    print(f"   数据已保存到: {output_path}")
    return output_path


if __name__ == "__main__":
    main()