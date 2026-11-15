#!/usr/bin/env python3
"""
A股同花顺概念板块综合数据采集脚本（高效版 v2）
采集指定时间范围内每日所有概念板块的详细数据，输出JSON文件

用法:
    python fetch_sector_data.py <start_date> <end_date> [output_dir]

参数:
    start_date - 起始日期，格式 YYYYMMDD，如 20260801
    end_date   - 结束日期，格式 YYYYMMDD，如 20260812
    output_dir - 输出目录，默认 ../concept/

依赖:
    pip install akshare pandas

数据来源:
    - 概念板块列表:   ak.stock_board_concept_name_ths()      同花顺-概念板块名称
    - 行业板块指数:   ak.stock_board_industry_index_ths()     同花顺-行业板块指数日线
    - 涨停股池:       ak.stock_zt_pool_em()                   东方财富-涨停股池
    - 炸板股池:       ak.stock_zt_pool_zbgc_em()              东方财富-炸板股池
    - 龙虎榜:         ak.stock_lhb_detail_em()                东方财富-龙虎榜每日详情
    - 个股历史行情:   ak.stock_zh_a_hist()                    东方财富-A股历史日线
    - 交易日历:       ak.tool_trade_date_hist_sina()          新浪-交易日历

优化策略:
    - 先获取涨停股池，提取涉及的板块名称
    - 涨停股池"所属行业"是申万行业分类，通过映射表转为同花顺行业板块名称
    - 使用 stock_board_industry_index_ths 获取行业板块指数行情
    - 龙虎榜数据按日期范围查询
"""

import akshare as ak
import pandas as pd
import numpy as np
import json
import sys
import os
import time
from datetime import datetime
from collections import defaultdict


# ============================================================
# 申万行业 → 同花顺行业板块 映射表
# 涨停股池的"所属行业"字段使用申万行业分类（如"半导体"、"白酒Ⅱ"）
# 同花顺行业板块指数接口使用同花顺行业名称（如"半导体"、"白酒"）
# ============================================================

SW_TO_THS_INDUSTRY = {
    "IT服务Ⅱ": "IT服务",
    "一般零售": "零售",
    "专业工程": "建筑装饰",
    "中药Ⅱ": "中药",
    "休闲食品": "食品加工制造",
    "基础建设": "建筑装饰",
    "塑料": "塑料制品",
    "房地产开": "房地产",
    "房地产服": "房地产",
    "数字媒体": "文化传媒",
    "汽车零部": "汽车零部件",
    "燃气Ⅱ": "燃气",
    "电视广播": "文化传媒",
    "白酒Ⅱ": "白酒",
    "综合Ⅱ": "综合",
    "装修装饰": "建筑装饰",
    "调味发酵": "食品加工制造",
    "铁路公路": "公路铁路运输",
    "食品加工": "食品加工制造",
    "饮料乳品": "饮料制造",
    "饲料": "农产品加工",
    "其他电子": "其他电子",
    "服装家纺": "服装家纺",
    "游戏Ⅱ": "游戏",
    "自动化设": "自动化设备",
    "计算机设": "计算机设备",
    "造纸": "造纸",
    "饰品": "服装家纺",
    "普钢": "钢铁",
    "工程机械": "工程机械",
    "工程咨询": "建筑装饰",
    "生物制品": "生物制品",
    "能源金属": "能源金属",
    "电池": "电池",
    "电机": "电机",
    "电子化学品": "电子化学品",
    "石油加工": "石油加工贸易",
    "种植业": "种植业与林业",
    "纺织制造": "纺织制造",
    "美容护理": "美容护理",
    "航空装备": "军工装备",
    "证券Ⅱ": "证券",
    "贵金属": "贵金属",
    "贸易Ⅱ": "贸易",
    "轨交设备": "轨交设备",
    "通信服务": "通信服务",
    "金属新材料": "金属新材料",
    "非金属材料": "非金属材料",
    "风电设备": "风电设备",
    "黑色家电": "黑色家电",
    "厨卫电器": "厨卫电器",
    "多元金融": "多元金融",
    "小金属": "小金属",
    "建筑材料": "建筑材料",
    "旅游及景区": "旅游及酒店",
    "机场航运": "机场航运",
    "橡胶": "橡胶制品",
    "汽车整车": "汽车整车",
    "汽车服务": "汽车服务及其他",
    "油气开采": "油气开采及服务",
    "港口航运": "港口航运",
    "煤炭开采": "煤炭开采加工",
    "环保设备": "环保设备",
    "白色家电": "白色家电",
    "光学光电子": "光学光电子",
    "其他电源设备": "其他电源设备",
    "其他社会服务": "其他社会服务",
    "军工电子": "军工电子",
    "军工装备": "军工装备",
    "农化制品": "农化制品",
    "包装印刷": "包装印刷",
    "化学原料": "化学原料",
    "互联网电商": "互联网电商",
    "保险": "保险",
}


def map_sw_to_ths(sw_name):
    """将申万行业名称映射为同花顺行业板块名称"""
    if sw_name in SW_TO_THS_INDUSTRY:
        return SW_TO_THS_INDUSTRY[sw_name]
    return sw_name  # 直接匹配的返回原名


# ============================================================
# 工具函数
# ============================================================

def safe_call(func, *args, **kwargs):
    """安全调用函数，失败返回None"""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        print(f"    [WARN] {func.__name__} 失败: {e}", file=sys.stderr)
        return None


def get_trade_dates_in_range(start_date, end_date):
    """获取指定日期范围内的交易日列表"""
    df = ak.tool_trade_date_hist_sina()
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    mask = (df['trade_date'] >= start) & (df['trade_date'] <= end)
    return df[mask]['trade_date'].dt.strftime('%Y%m%d').tolist()


def fmt_date(date_str):
    """YYYYMMDD -> YYYY-MM-DD"""
    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"


# ============================================================
# 概念板块列表
# ============================================================

def fetch_concept_board_list():
    """获取同花顺所有概念板块名称和代码"""
    df = safe_call(ak.stock_board_concept_name_ths)
    if df is None:
        return []
    return [{"name": row['name'], "code": row['code']} for _, row in df.iterrows()]


# ============================================================
# 行业板块指数历史行情
# ============================================================

def fetch_industry_index_history(industry_name, start_date, end_date):
    """
    获取同花顺行业板块指数历史行情
    返回 dict: {date_str: {open, high, low, close, volume, amount}}
    """
    df = safe_call(ak.stock_board_industry_index_ths,
                   symbol=industry_name,
                   start_date=fmt_date(start_date),
                   end_date=fmt_date(end_date))
    if df is None or len(df) == 0:
        return {}

    result = {}
    for _, row in df.iterrows():
        date_str = str(row['日期']).replace('-', '')[:8]
        result[date_str] = {
            "open": round(float(row['开盘价']), 2),
            "high": round(float(row['最高价']), 2),
            "low": round(float(row['最低价']), 2),
            "close": round(float(row['收盘价']), 2),
            "volume": int(row['成交量']),
            "amount": round(float(row['成交额']), 2),
        }
    return result


# ============================================================
# 涨停/炸板股池
# ============================================================

def fetch_limit_up_pool(date_str):
    """获取某日涨停股池"""
    try:
        return ak.stock_zt_pool_em(date=date_str)
    except Exception as e:
        print(f"    [WARN] {date_str} 涨停股池获取失败: {e}", file=sys.stderr)
        return pd.DataFrame()


def fetch_blow_up_pool(date_str):
    """获取某日炸板股池"""
    try:
        return ak.stock_zt_pool_zbgc_em(date=date_str)
    except Exception:
        return pd.DataFrame()


def fetch_spot_spot_sina():
    """
    获取新浪全市场实时行情（含涨跌幅），用于筛选涨幅>5%的股票。
    注意: 该接口为实时快照，仅对"最近交易日"有效；历史日期无法回溯。
    返回 DataFrame 或 None
    """
    try:
        df = ak.stock_zh_a_spot()
        if df is not None and len(df) > 0:
            return df
    except Exception as e:
        print(f"    [WARN] 新浪全市场行情获取失败: {e}", file=sys.stderr)
    return None


def build_code_industry_map(limit_up_df, blow_up_df):
    """
    从涨停股池和炸板股池的"所属行业"字段，构建 {6位代码: 申万行业} 映射。
    用于将全市场行情中的股票归入对应申万行业板块。
    """
    code_map = {}
    for df in (limit_up_df, blow_up_df):
        if df is None or len(df) == 0:
            continue
        if '代码' not in df.columns or '所属行业' not in df.columns:
            continue
        for _, row in df.iterrows():
            code = str(row['代码']).zfill(6)
            ind = str(row['所属行业'])
            if code and ind and ind != 'nan':
                code_map[code] = ind
    return code_map


# ============================================================
# 龙虎榜数据
# ============================================================

def fetch_lhb_data(start_date, end_date):
    """获取指定日期范围的龙虎榜数据"""
    s = fmt_date(start_date)
    e = fmt_date(end_date)
    df = safe_call(ak.stock_lhb_detail_em, start_date=s, end_date=e)
    return df if df is not None else pd.DataFrame()


# ============================================================
# 板块分析计算
# ============================================================

def analyze_board_on_date(sw_name, date_str, limit_up_df, prev_limit_up_df,
                          industry_index_history, lhb_df,
                          blow_up_df=None, spot_df=None, code_industry_map=None):
    """
    对单个板块在指定日期进行综合分析
    sw_name: 申万行业名称（涨停股池中的"所属行业"）
    blow_up_df: 炸板股池（含"所属行业"、"涨跌幅"），用于炸板率和涨幅>5%统计
    spot_df: 新浪全市场实时行情（含涨跌幅、代码），用于筛选涨幅>5%的股票，可为 None
    code_industry_map: {6位代码: 申万行业} 映射，用于 spot_df 行业归属判断
    """
    ths_name = map_sw_to_ths(sw_name)

    result = {
        "stock_count": None,
        "board_1": 0,
        "board_2": 0,
        "board_3": 0,
        "board_4": 0,
        "board_1_stocks": [],
        "board_2_stocks": [],
        "board_3_stocks": [],
        "board_4_stocks": [],
        "board_5_plus_stocks": [],
        "gain_5_stocks": [],
        "max_board_height": 0,
        "max_board_stocks": [],
        "red_count": None,
        "green_count": None,
        "blow_up_rate": None,
        "prev_board_premium": None,
        "total_amount": None,
        "index_change_pct": None,
        "volume_ratio": None,
        "lhb_net_buy": None,
        "lhb_stock_count": 0,
    }

    idx_hist = industry_index_history.get(ths_name, {})

    # ---- 1. 行业板块指数行情 ----
    if date_str in idx_hist:
        idx = idx_hist[date_str]
        result["total_amount"] = idx["amount"]

        prev_date = _get_prev_trade_date(date_str, idx_hist)
        if prev_date and prev_date in idx_hist:
            prev_close = idx_hist[prev_date]["close"]
            if prev_close > 0:
                result["index_change_pct"] = round(
                    (idx["close"] - prev_close) / prev_close * 100, 2
                )

        sorted_dates = sorted(idx_hist.keys())
        if date_str in sorted_dates:
            idx_pos = sorted_dates.index(date_str)
            start_pos = max(0, idx_pos - 4)
            volumes = [idx_hist[d]["volume"] for d in sorted_dates[start_pos:idx_pos + 1]]
            if len(volumes) >= 2:
                avg_vol = sum(volumes) / len(volumes)
                if avg_vol > 0:
                    result["volume_ratio"] = round(volumes[-1] / avg_vol, 2)

        if result["index_change_pct"] is not None:
            if result["index_change_pct"] > 0:
                result["red_count"] = 1
                result["green_count"] = 0
            elif result["index_change_pct"] < 0:
                result["red_count"] = 0
                result["green_count"] = 1
            else:
                result["red_count"] = 0
                result["green_count"] = 0

    # ---- 2. 涨停板分析（通过涨停股池"所属行业"字段匹配） ----
    board_zt = pd.DataFrame()
    if len(limit_up_df) > 0 and '所属行业' in limit_up_df.columns:
        board_zt = limit_up_df[limit_up_df['所属行业'].astype(str) == sw_name]

    if len(board_zt) > 0:
        if '连板数' in board_zt.columns:
            board_zt = board_zt.copy()
            board_zt['连板数'] = pd.to_numeric(board_zt['连板数'], errors='coerce')
            dist = board_zt['连板数'].value_counts().to_dict()
            result["board_1"] = int(dist.get(1, 0))
            result["board_2"] = int(dist.get(2, 0))
            result["board_3"] = int(dist.get(3, 0))
            result["board_4"] = int(dist.get(4, 0))

            # ---- 各连板股票明细 ----
            for _, row in board_zt.iterrows():
                stock_info = _build_limit_stock_info(row)
                board_num = row['连板数']
                if pd.isna(board_num):
                    continue
                board_num = int(board_num)
                if board_num <= 0:
                    continue
                if board_num == 1:
                    result["board_1_stocks"].append(stock_info)
                elif board_num == 2:
                    result["board_2_stocks"].append(stock_info)
                elif board_num == 3:
                    result["board_3_stocks"].append(stock_info)
                elif board_num == 4:
                    result["board_4_stocks"].append(stock_info)
                else:
                    result["board_5_plus_stocks"].append(stock_info)

            max_board = int(board_zt['连板数'].max())
            if pd.notna(max_board) and max_board > 0:
                result["max_board_height"] = max_board
                top = board_zt[board_zt['连板数'] == max_board]
                result["max_board_stocks"] = [
                    f"{row['代码']} {row['名称']}"
                    for _, row in top.iterrows()
                ]

    # ---- 3. 板块炸板率（复用传入的炸板股池） ----
    board_zb = pd.DataFrame()
    if blow_up_df is not None and len(blow_up_df) > 0 and '所属行业' in blow_up_df.columns:
        board_zb = blow_up_df[blow_up_df['所属行业'].astype(str) == sw_name]
        board_zt_count = len(board_zt)
        zb_count = len(board_zb)
        total_attempt = board_zt_count + zb_count
        if total_attempt > 0:
            result["blow_up_rate"] = round(zb_count / total_attempt * 100, 2)

    # ---- 6. 涨幅>5%的股票列表 ----
    # 来源1: 涨停股池（涨幅均>9%，天然满足）
    # 来源2: 炸板股池中涨幅>5%的股票
    # 来源3: 新浪全市场行情，通过 code_industry_map 归入板块
    gain_map = {}  # code -> {name, change_pct, price}

    # 来源1: 涨停股池
    if len(board_zt) > 0:
        for _, row in board_zt.iterrows():
            code = str(row['代码'])
            gain_map[code] = {
                "code": code,
                "name": str(row['名称']),
                "change_pct": round(float(row['涨跌幅']), 2) if pd.notna(row.get('涨跌幅')) else None,
                "price": round(float(row['最新价']), 2) if pd.notna(row.get('最新价')) else None,
            }

    # 来源2: 炸板股池涨幅>5%
    if len(board_zb) > 0 and '涨跌幅' in board_zb.columns:
        for _, row in board_zb.iterrows():
            try:
                if float(row['涨跌幅']) > 5:
                    code = str(row['代码'])
                    gain_map[code] = {
                        "code": code,
                        "name": str(row['名称']),
                        "change_pct": round(float(row['涨跌幅']), 2),
                        "price": round(float(row['最新价']), 2) if pd.notna(row.get('最新价')) else None,
                    }
            except (ValueError, TypeError):
                continue

    # 来源3: 新浪全市场行情（覆盖 5%~9.9% 未涨停/未炸板的股票）
    if spot_df is not None and len(spot_df) > 0 and code_industry_map:
        for _, row in spot_df.iterrows():
            try:
                change_pct = float(row['涨跌幅'])
                if change_pct <= 5:
                    continue
            except (ValueError, TypeError):
                continue
            code = _normalize_stock_code(str(row['代码']))
            if code_industry_map.get(code) == sw_name:
                gain_map[code] = {
                    "code": code,
                    "name": str(row['名称']),
                    "change_pct": round(change_pct, 2),
                    "price": round(float(row['最新价']), 2) if pd.notna(row.get('最新价')) else None,
                }

    if gain_map:
        result["gain_5_stocks"] = sorted(
            gain_map.values(),
            key=lambda x: (x["change_pct"] if x["change_pct"] is not None else -999),
            reverse=True,
        )

    # ---- 4. 昨日涨停板块溢价 ----
    if len(prev_limit_up_df) > 0 and '所属行业' in prev_limit_up_df.columns:
        prev_board_zt = prev_limit_up_df[prev_limit_up_df['所属行业'].astype(str) == sw_name]

        if len(prev_board_zt) > 0:
            premiums = []
            for _, row in prev_board_zt.iterrows():
                code = row['代码']
                try:
                    hist = ak.stock_zh_a_hist(symbol=code, period='daily',
                                               start_date=fmt_date(date_str),
                                               end_date=fmt_date(date_str),
                                               adjust='')
                    if hist is not None and len(hist) > 0:
                        open_price = float(hist.iloc[0]['开盘'])
                        prev_close_val = None
                        if '昨收' in hist.columns:
                            prev_close_val = float(hist.iloc[0]['昨收'])
                        if (prev_close_val is None or prev_close_val == 0) and '收盘' in hist.columns:
                            prev_close_val = float(hist.iloc[0]['收盘'])
                        if prev_close_val and prev_close_val > 0:
                            premium = (open_price - prev_close_val) / prev_close_val * 100
                            premiums.append(premium)
                except Exception:
                    pass
            if premiums:
                result["prev_board_premium"] = round(sum(premiums) / len(premiums), 2)

    # ---- 5. 龙虎榜资金偏好 ----
    if len(lhb_df) > 0 and len(board_zt) > 0:
        dt_str = fmt_date(date_str)
        day_lhb = lhb_df[lhb_df['上榜日'] == dt_str]
        if len(day_lhb) > 0:
            board_zt_codes = set(board_zt['代码'].astype(str))
            board_lhb = day_lhb[day_lhb['代码'].astype(str).isin(board_zt_codes)]
            if len(board_lhb) > 0:
                result["lhb_stock_count"] = len(board_lhb)
                net_buy = pd.to_numeric(board_lhb['龙虎榜净买额'], errors='coerce').sum()
                if pd.notna(net_buy):
                    result["lhb_net_buy"] = round(float(net_buy), 2)

    return result


def _build_limit_stock_info(row):
    """从涨停股池的一行构建涨停股票明细信息"""
    info = {
        "code": str(row.get('代码', '')),
        "name": str(row.get('名称', '')),
    }
    # 涨跌幅
    if '涨跌幅' in row and pd.notna(row['涨跌幅']):
        info["change_pct"] = round(float(row['涨跌幅']), 2)
    # 最新价
    if '最新价' in row and pd.notna(row['最新价']):
        info["price"] = round(float(row['最新价']), 2)
    # 成交额
    if '成交额' in row and pd.notna(row['成交额']):
        info["amount"] = round(float(row['成交额']), 2)
    # 封板资金
    if '封板资金' in row and pd.notna(row['封板资金']):
        info["seal_amount"] = round(float(row['封板资金']), 2)
    # 首次封板时间
    if '首次封板时间' in row and pd.notna(row['首次封板时间']):
        info["first_seal_time"] = str(row['首次封板时间'])
    # 最后封板时间
    if '最后封板时间' in row and pd.notna(row['最后封板时间']):
        info["last_seal_time"] = str(row['最后封板时间'])
    # 炸板次数
    if '炸板次数' in row and pd.notna(row['炸板次数']):
        info["blow_up_count"] = int(row['炸板次数'])
    # 涨停统计 (N天M板)
    if '涨停统计' in row and pd.notna(row['涨停统计']):
        info["limit_stat"] = str(row['涨停统计'])
    # 换手率
    if '换手率' in row and pd.notna(row['换手率']):
        info["turnover_rate"] = round(float(row['换手率']), 2)
    return info


def _normalize_stock_code(code):
    """将带交易所前缀的代码(如 sh600000/sz000001/bj920000)转为6位纯数字代码"""
    if not code:
        return ""
    code = str(code).strip()
    if code.startswith(("sh", "sz", "bj", "SH", "SZ", "BJ")):
        return code[2:]
    return code


def _get_prev_trade_date(date_str, index_history):
    """从指数历史中获取前一个交易日"""
    sorted_dates = sorted(index_history.keys())
    if date_str in sorted_dates:
        idx = sorted_dates.index(date_str)
        if idx > 0:
            return sorted_dates[idx - 1]
    return None


# ============================================================
# 主流程
# ============================================================

def main():
    if len(sys.argv) < 3:
        print("用法: python fetch_sector_data.py <start_date> <end_date> [output_dir]")
        print("示例: python fetch_sector_data.py 20260801 20260812")
        sys.exit(1)

    start_date = sys.argv[1]
    end_date = sys.argv[2]
    output_dir = (
        sys.argv[3]
        if len(sys.argv) > 3
        else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "concept")
    )

    print(f"📊 A股同花顺概念板块数据采集")
    print(f"   日期范围: {start_date} ~ {end_date}")
    print()

    # ---- Step 1: 获取交易日列表 ----
    print("📅 获取交易日列表...")
    trade_dates = get_trade_dates_in_range(start_date, end_date)
    print(f"   共 {len(trade_dates)} 个交易日: {trade_dates}")

    if not trade_dates:
        print("❌ 指定日期范围内无交易日")
        sys.exit(1)

    # ---- Step 2: 获取概念板块列表 ----
    print("\n📋 获取同花顺概念板块列表...")
    boards = fetch_concept_board_list()
    print(f"   共 {len(boards)} 个概念板块")

    # ---- Step 3: 先获取所有日期的涨停股池 + 炸板股池，提取活跃板块 ----
    print("\n📊 获取涨停股池和炸板股池，提取活跃板块...")
    all_limit_up = {}
    all_blow_up = {}
    active_sw_industries = set()

    for date_str in trade_dates:
        df = fetch_limit_up_pool(date_str)
        all_limit_up[date_str] = df
        if len(df) > 0 and '所属行业' in df.columns:
            industries = set(df['所属行业'].dropna().unique())
            active_sw_industries.update(industries)

        zb_df = fetch_blow_up_pool(date_str)
        all_blow_up[date_str] = zb_df
        if len(zb_df) > 0 and '所属行业' in zb_df.columns:
            industries = set(zb_df['所属行业'].dropna().unique())
            active_sw_industries.update(industries)
        time.sleep(0.1)

    print(f"   涨停/炸板股池涉及的申万行业: {len(active_sw_industries)} 个")

    # ---- Step 3.5: 获取新浪全市场实时行情（仅对最近交易日有效） ----
    spot_df = fetch_spot_spot_sina()
    if spot_df is not None:
        print(f"   新浪全市场行情: {len(spot_df)} 只（仅最近交易日有效）")
    else:
        print("   新浪全市场行情不可用，涨幅>5%统计仅覆盖涨停/炸板股")

    # 映射为同花顺行业板块名称
    active_ths_industries = set()
    for sw_name in active_sw_industries:
        active_ths_industries.add(map_sw_to_ths(sw_name))
    print(f"   映射为同花顺行业板块: {len(active_ths_industries)} 个")

    # ---- Step 4: 获取活跃行业板块的指数历史行情 ----
    print("\n📈 获取行业板块指数历史行情...")
    industry_index_data = {}
    active_list = sorted(active_ths_industries)
    success_count = 0

    for i, name in enumerate(active_list):
        if (i + 1) % 10 == 0:
            print(f"   进度: {i+1}/{len(active_list)} (成功: {success_count})")
        hist = fetch_industry_index_history(name, start_date, end_date)
        if hist:
            industry_index_data[name] = hist
            success_count += 1
        time.sleep(0.05)

    print(f"   成功: {success_count}/{len(active_list)}")

    # ---- Step 5: 获取龙虎榜数据 ----
    print("\n💰 获取龙虎榜数据...")
    lhb_df = fetch_lhb_data(start_date, end_date)
    if len(lhb_df) > 0:
        print(f"   共 {len(lhb_df)} 条龙虎榜记录")
    else:
        print("   无龙虎榜数据")

    # ---- Step 6: 读取已有数据（增量更新） ----
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "sector_data.json")
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
            print(f"   已加载 {len(existing_data)} 条历史数据")
        except Exception:
            pass

    # ---- Step 7: 逐日分析 ----
    print(f"\n🔍 逐日分析板块数据（共 {len(trade_dates)} 天）...")

    prev_limit_up_df = pd.DataFrame()

    for di, date_str in enumerate(trade_dates):
        print(f"\n  [{di+1}/{len(trade_dates)}] 📅 {date_str}")

        limit_up_df = all_limit_up[date_str]
        blow_up_df = all_blow_up.get(date_str, pd.DataFrame())
        zt_count = len(limit_up_df) if limit_up_df is not None else 0
        print(f"    涨停 {zt_count} 只, 分析 {len(active_sw_industries)} 个板块...")

        # 构建代码→申万行业映射（用于全市场行情行业归属）
        code_industry_map = build_code_industry_map(limit_up_df, blow_up_df)

        # 新浪全市场行情仅对最近交易日有效，其余日期传 None
        is_latest = (di == len(trade_dates) - 1)
        cur_spot_df = spot_df if (is_latest and spot_df is not None) else None

        date_result = {}
        board_count = 0

        for sw_name in sorted(active_sw_industries):
            analysis = analyze_board_on_date(
                sw_name=sw_name,
                date_str=date_str,
                limit_up_df=limit_up_df,
                prev_limit_up_df=prev_limit_up_df,
                industry_index_history=industry_index_data,
                lhb_df=lhb_df,
                blow_up_df=blow_up_df,
                spot_df=cur_spot_df,
                code_industry_map=code_industry_map,
            )

            has_data = (
                analysis["board_1"] > 0 or
                analysis["board_2"] > 0 or
                analysis["board_3"] > 0 or
                analysis["board_4"] > 0 or
                len(analysis["board_5_plus_stocks"]) > 0 or
                len(analysis["gain_5_stocks"]) > 0 or
                analysis["total_amount"] is not None or
                analysis["lhb_stock_count"] > 0
            )

            if has_data:
                date_result[sw_name] = analysis
                board_count += 1

        print(f"    有效板块: {board_count}")

        existing_data[date_str] = date_result
        prev_limit_up_df = limit_up_df

    # ---- Step 8: 输出 ----
    sorted_data = dict(sorted(existing_data.items()))

    output = {
        "meta": {
            "description": "A股同花顺概念板块综合数据（含连板股票明细、涨幅>5%股票、行业指数行情、龙虎榜资金偏好）",
            "data_range": f"{trade_dates[0]} ~ {trade_dates[-1]}",
            "total_trading_days": len(sorted_data),
            "total_concept_boards": len(boards),
            "active_sw_industries": len(active_sw_industries),
            "active_ths_industries": len(active_ths_industries),
            "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        },
        "data": sorted_data,
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 数据已保存到: {output_path}")
    print(f"   交易日: {len(sorted_data)} 天, 活跃板块: {len(active_sw_industries)} 个")
    return output_path


if __name__ == "__main__":
    main()