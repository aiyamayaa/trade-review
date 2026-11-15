#!/usr/bin/env python3
"""
A股个股基础信息采集脚本

获取全市场所有A股个股的基础信息（代码、名称、最新价、涨跌幅、市盈率、市净率、
总市值、流通市值、换手率、量比、成交额、多周期涨跌幅、主力净流入等），输出 JSON 文件。

用法:
    python fetch_stock_info.py [output_dir]

参数:
    output_dir - 输出目录，默认 ../concept/

依赖:
    pip install akshare pandas

数据来源:
    腾讯行情接口 ak.stock_zh_a_spot_tx()  全市场A股实时行情（默认，稳定）
    东财行情接口 ak.stock_zh_a_spot_em()  全市场A股实时行情（回退，网络不稳定）

说明:
    - 输出为单日快照，文件名带日期（YYYYMMDD），不覆盖历史
    - 腾讯接口字段丰富且稳定，含 5/10/20/60 日涨跌幅、年初至今、52周涨跌幅等
    - 数据仅供个人研究使用，请勿商用
"""

import sys
import os
import json
import warnings
from datetime import datetime

import pandas as pd

warnings.filterwarnings("ignore")

try:
    import akshare as ak
except ImportError:
    print("缺少依赖 akshare，请先执行: pip install akshare", file=sys.stderr)
    sys.exit(1)


# ============================================================
# 工具函数
# ============================================================

def _num(v, default=None, ndigits=2):
    """安全转 float，NaN/空返回 default"""
    try:
        x = float(v)
        if pd.isna(x):
            return default
        if ndigits is None:
            return x
        return round(x, ndigits)
    except (TypeError, ValueError):
        return default


def _fmt_code(code):
    """腾讯代码格式 sh600519/sz000001 -> 6位数字代码"""
    if isinstance(code, str) and len(code) >= 6:
        return code[-6:]
    return str(code).strip()


# ============================================================
# 数据解析
# ============================================================

def parse_tx_row(row):
    """
    解析腾讯全市场行情一行数据。
    单位说明:
        ltsz/zsz 市值    单位: 亿元
        turnover 成交额  单位: 万元
        volume   成交量  单位: 手
        zljlr    主力净流入 单位: 万元
        其余百分比/比值字段直接为原值
    """
    return {
        "code": _fmt_code(row.get('code')),
        "name": str(row.get('name', '')).strip(),
        "last_price": _num(row.get('zxj')),                    # 最新价(元)
        "change": _num(row.get('zd')),                          # 涨跌额(元)
        "change_pct": _num(row.get('zdf')),                     # 涨跌幅(%)
        "amplitude": _num(row.get('zf')),                       # 振幅(%)
        "speed": _num(row.get('speed')),                        # 涨速(%)
        "turnover_rate": _num(row.get('hsl')),                  # 换手率(%)
        "volume_ratio": _num(row.get('lb')),                    # 量比
        "pe_ttm": _num(row.get('pe_ttm')),                      # 市盈率(TTM)
        "pb": _num(row.get('pn')),                              # 市净率
        "total_mv": _num(row.get('zsz'), ndigits=None),         # 总市值(亿元)
        "float_mv": _num(row.get('ltsz'), ndigits=None),        # 流通市值(亿元)
        "turnover": _num(row.get('turnover'), ndigits=None),   # 成交额(万元)
        "volume": _num(row.get('volume'), ndigits=None),        # 成交量(手)
        "main_net_inflow": _num(row.get('zljlr')),              # 主力净流入(万元)
        # 多周期涨跌幅(%)
        "pct_5d": _num(row.get('zdf_d5')),
        "pct_10d": _num(row.get('zdf_d10')),
        "pct_20d": _num(row.get('zdf_d20')),
        "pct_60d": _num(row.get('zdf_d60')),
        "pct_ytd": _num(row.get('zdf_y')),                      # 年初至今
        "pct_52w": _num(row.get('zdf_w52')),                    # 52周涨跌幅
        "stock_type": str(row.get('stock_type', '')).strip(),  # 证券类别(如 GP-A)
    }


# ============================================================
# 主流程
# ============================================================

def main():
    output_dir = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "concept")
    )

    print("📈 获取A股全市场个股基础信息...")

    df = None
    source = None
    err = None

    # 优先使用腾讯接口（稳定）
    try:
        print("    尝试腾讯接口 stock_zh_a_spot_tx ...")
        df = ak.stock_zh_a_spot_tx()
        source = "腾讯行情 (stock_zh_a_spot_tx)"
    except Exception as e:
        err = e
        print(f"    腾讯接口失败: {e}", file=sys.stderr)

    # 回退到东财接口
    if df is None or len(df) == 0:
        try:
            print("    回退到东财接口 stock_zh_a_spot_em ...")
            df = ak.stock_zh_a_spot_em()
            source = "东方财富行情 (stock_zh_a_spot_em)"
        except Exception as e2:
            print(f"    东财接口也失败: {e2}", file=sys.stderr)
            print(f"❌ 全部数据源失败，原始错误: {err}", file=sys.stderr)
            sys.exit(1)

    if df is None or len(df) == 0:
        print("❌ 未获取到任何个股数据")
        sys.exit(1)

    print(f"    共获取 {len(df)} 只个股 (来源: {source})")

    # 解析
    stocks = [parse_tx_row(row) for _, row in df.iterrows()]

    date_str = datetime.now().strftime("%Y%m%d")
    output = {
        "meta": {
            "description": "A股全市场个股基础信息快照",
            "source": source,
            "total": len(stocks),
            "trade_date": datetime.now().strftime("%Y-%m-%d"),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "stocks": stocks,
    }

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"stock_info_{date_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"✅ 已保存 {len(stocks)} 只个股基础信息到: {path}")
    return path


if __name__ == "__main__":
    main()