#!/usr/bin/env python3
"""
九方智投题材（概念/行业板块）数据采集脚本

采集九方智投（stock.9fzt.com）的题材板块行情及题材下个股明细数据，输出 JSON 文件。

用法:
    python fetch_jiufang_data.py <command> [options]

命令:
    boards   采集题材板块列表（行情排名）
    detail   采集指定题材下的个股明细（含连板数、关联理由等）

数据来源:
    九方智投公开网页接口（chongnengjihua.com 行情网关），无需登录、无需签名。

依赖:
    pip install requests

说明:
    - 数据为九方智投公开行情数据，仅供个人研究使用，请勿商用。
    - 题材分三类: GN=概念板块, HY=行业板块, DQ=地区板块。
    - 龙头股(人气/业绩/市值)、AI 解读等接口需要签名 header，本脚本暂不采集。
"""

import sys
import os
import json
import time
import argparse
from datetime import datetime

try:
    import requests
except ImportError:
    print("缺少依赖 requests，请先执行: pip install requests", file=sys.stderr)
    sys.exit(1)


# ============================================================
# 常量配置
# ============================================================

BASE_URL = "https://hq.chongnengjihua.com/rjhy-quote-sector/api/1/pc/plate/block"

# 板块类型映射
BOARD_TYPES = {
    "gn": "GN",  # 概念板块
    "hy": "HY",  # 行业板块
    "dq": "DQ",  # 地区板块
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Referer": "https://stock.9fzt.com/",
    "Accept": "application/json, text/plain, */*",
}


# ============================================================
# 工具函数
# ============================================================

def safe_get(url, params=None, retries=3):
    """带重试的 GET 请求，返回 JSON 或 None"""
    for i in range(retries):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == 1:
                return data.get("data")
            print(f"    [WARN] 接口返回异常 code={data.get('code')} "
                  f"msg={data.get('message')}", file=sys.stderr)
            return None
        except Exception as e:
            if i < retries - 1:
                time.sleep(1.0 * (i + 1))
                continue
            print(f"    [WARN] 请求失败: {e}", file=sys.stderr)
            return None
    return None


# ============================================================
# 板块列表
# ============================================================

def fetch_board_list(board_type="GN", sort_field="pxChangeRate",
                     page_size=100, max_pages=None):
    """
    获取题材板块列表行情。

    board_type: GN/HY/DQ
    sort_field: pxChangeRate(涨跌幅) / fundflow(主力净流入) /
                businessBalance(成交额) / upLimitNum(涨停家数) 等
    返回: 板块列表 dict 数组
    """
    url = f"{BASE_URL}/quote/list"
    all_boards = []
    page_num = 1

    while True:
        params = {
            "hqTypeCode": board_type,
            "sortFlag": "true",
            "sortFields": sort_field,
            "pageNum": page_num,
            "pageSize": page_size,
        }
        data = safe_get(url, params)
        if not data:
            break

        boards = data.get("plate", [])
        all_boards.extend(boards)

        total = data.get("counts", 0)
        fetched = page_num * page_size
        print(f"    已获取 {len(all_boards)}/{total} 个板块 (第{page_num}页)", file=sys.stderr)

        if fetched >= total or not boards:
            break
        if max_pages and page_num >= max_pages:
            break
        page_num += 1
        time.sleep(0.2)

    return all_boards


def parse_board(board):
    """解析板块列表项为简洁字段"""
    # 领涨股
    lead_stock = None
    rise_first = board.get("RiseFirstGrp") or []
    if rise_first:
        top = rise_first[0]
        lead_stock = {
            "code": top.get("ProdCode"),
            "name": top.get("ProdName"),
            "change_pct": _pct(top.get("PxChangeRate")),
            "board": top.get("countBoard", 0),  # 连板数
        }

    return {
        "code": board.get("ProdCode"),
        "name": board.get("ProdName"),
        "change_pct": _pct(board.get("PxChangeRate")),
        "main_net_inflow": board.get("Fundflow"),          # 主力净流入(元)
        "amount": board.get("BusinessBalance"),            # 成交额(元)
        "amplitude": _pct(board.get("Amplitude")),        # 振幅
        "member_count": board.get("MemberCount"),         # 成分股数量
        "rise_count": board.get("RiseCount"),             # 上涨家数
        "fall_count": board.get("FallCount"),             # 下跌家数
        "flat_count": board.get("FlatCount"),             # 平盘家数
        "limit_up_count": board.get("UpLimitNum"),        # 涨停家数
        "lead_stock": lead_stock,                          # 领涨股
    }


# ============================================================
# 题材个股明细
# ============================================================

def fetch_board_stocks(board_code, board_type="GN", sort_field="countBoard",
                       page_size=100):
    """
    获取指定题材板块的成分股明细。

    board_code: 板块代码，如 GN886033
    sort_field: countBoard(连板数) / pxChangeRate(涨跌幅) /
                fundFlow(主力净流入) / businessAmount(成交额) 等
    返回: 个股 dict 数组
    """
    url = f"{BASE_URL}/stock/group"
    all_stocks = []
    page_num = 1

    while True:
        params = {
            "hqTypeCode": board_type,
            "prodCode": board_code,
            "sortFlag": "true",
            "sortFields": sort_field,
            "simPageSize": "yes",
            "pageSize": page_size,
            "pageNum": page_num,
        }
        data = safe_get(url, params)
        if not data:
            break

        stocks = data.get("sortProdGrp", [])
        all_stocks.extend(stocks)

        plate = data.get("plate", {})
        total = plate.get("MemberCount", 0)
        if not stocks or len(all_stocks) >= total:
            break
        page_num += 1
        time.sleep(0.2)

    return all_stocks


def parse_stock(stock):
    """解析成分股为简洁字段"""
    # 特殊标签: 如 "最先涨停"、"最高封单"、"最大换手"、"最大成交"、"最大流入"
    special_labels = [
        s.get("desc") for s in (stock.get("specialLabels") or [])
        if s.get("desc")
    ]

    return {
        "code": stock.get("prodCode"),
        "name": stock.get("prodName"),
        "last_price": _div(stock.get("lastPx"), 1000),       # 最新价
        "change_pct": _pct(stock.get("pxChangeRate")),       # 涨跌幅
        "board": stock.get("countBoard", 0),                  # 连板数
        "board_type": stock.get("boardType"),                 # 板类型
        "first_limit_time": _ts_to_hhmm(stock.get("firstUpTime")),  # 首次涨停时间
        "limit_amount": stock.get("limitAmount"),            # 封单金额(元)
        "main_net_inflow": stock.get("fundFlow"),            # 主力净流入(元)
        "amount": stock.get("businessBalance"),              # 成交额(元)
        "turnover_rate": _pct(stock.get("turnoverRatio")),   # 换手率
        "volume_ratio": _div(stock.get("volRatio"), 1000),   # 量比
        "amplitude": _pct(stock.get("amplitude")),           # 振幅
        "five_day_change": _pct(stock.get("fivePct")),       # 5日涨幅
        "pe_ratio": _div(stock.get("peRate"), 1000),         # 市盈率(动)
        "pb_ratio": _div(stock.get("dynPbRate"), 1000),      # 市净率
        "special_labels": special_labels,                     # 特殊标签
        "relation_reason": stock.get("relationSeason"),       # 关联理由(题材归属依据)
    }


# ============================================================
# 数值格式转换工具
# ============================================================

def _pct(v):
    """整数万分比/百分比 -> 浮点百分比"""
    if v is None:
        return None
    return round(float(v) / 100, 2)


def _div(v, d):
    """数值除以 d，保留2位"""
    if v is None:
        return None
    return round(float(v) / d, 2)


def _ts_to_hhmm(ts):
    """毫秒时间戳 -> HH:MM"""
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(ts / 1000).strftime("%H:%M")
    except Exception:
        return None


# ============================================================
# 主流程
# ============================================================

def cmd_boards(args):
    """采集题材板块列表（可选：一并采集每个板块的全部成分股）"""
    board_type = BOARD_TYPES.get(args.type.lower(), "GN")
    print(f"📊 采集题材板块列表 (类型: {board_type}, 排序: {args.sort})")
    boards = fetch_board_list(board_type, sort_field=args.sort,
                              max_pages=args.max_pages)
    if not boards:
        print("❌ 未获取到板块数据")
        return

    # 可选：限制板块数量
    if args.limit and args.limit > 0:
        boards = boards[:args.limit]
        print(f"  已限制为前 {len(boards)} 个板块")

    parsed = [parse_board(b) for b in boards]

    # 可选：采集每个板块的全部成分股
    if args.with_stocks:
        print(f"\n📈 采集各板块成分股 (共 {len(parsed)} 个板块)...")
        for i, (raw_board, p) in enumerate(zip(boards, parsed)):
            code = raw_board.get("ProdCode")
            if not code:
                continue
            stocks = fetch_board_stocks(code, board_type=board_type,
                                        sort_field="countBoard")
            if stocks:
                p["stocks"] = [parse_stock(s) for s in stocks]
            else:
                p["stocks"] = []
            if (i + 1) % 10 == 0 or (i + 1) == len(parsed):
                print(f"    进度: {i+1}/{len(parsed)}", file=sys.stderr)

    output = {
        "meta": {
            "source": "九方智投 (stock.9fzt.com)",
            "board_type": board_type,
            "sort_field": args.sort,
            "total": len(parsed),
            "with_stocks": bool(args.with_stocks),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "boards": parsed,
    }

    date_str = datetime.now().strftime("%Y%m%d")
    path = os.path.join(args.output_dir,
                        f"jiufang_boards_{board_type.lower()}_{date_str}.json")
    _write_json(output, path)
    print(f"✅ 已保存 {len(parsed)} 个板块到: {path}")


def cmd_detail(args):
    """采集指定题材下的个股明细"""
    print(f"📈 采集题材个股明细 (板块: {args.code})")
    stocks = fetch_board_stocks(args.code, board_type=args.type.upper(),
                                sort_field=args.sort)
    if not stocks:
        print("❌ 未获取到个股数据，请确认板块代码正确 (如 GN886033)")
        return

    parsed = [parse_stock(s) for s in stocks]

    # 板块代码作为题材名（如需名称可结合 boards 数据）
    output = {
        "meta": {
            "source": "九方智投 (stock.9fzt.com)",
            "board_code": args.code,
            "board_type": args.type.upper(),
            "sort_field": args.sort,
            "total": len(parsed),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "stocks": parsed,
    }

    date_str = datetime.now().strftime("%Y%m%d")
    path = os.path.join(args.output_dir, f"jiufang_detail_{args.code}_{date_str}.json")
    _write_json(output, path)
    print(f"✅ 已保存 {len(parsed)} 只个股到: {path}")


def _write_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="九方智投题材数据采集脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 采集概念板块列表(按涨跌幅排序)
  python fetch_jiufang_data.py boards --type gn

  # 采集行业板块列表(按主力净流入排序)
  python fetch_jiufang_data.py boards --type hy --sort fundflow

  # 采集概念板块列表 + 每个板块的全部成分股(个股明细)
  python fetch_jiufang_data.py boards --type gn --with-stocks

  # 仅采集前 10 个板块的全部成分股(快速测试)
  python fetch_jiufang_data.py boards --type gn --with-stocks --limit 10

  # 采集指定题材的个股明细(如共封装光学CPO, 代码GN886033)
  python fetch_jiufang_data.py detail --code GN886033
        """,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # boards 子命令
    p_boards = sub.add_parser("boards", help="采集题材板块列表")
    p_boards.add_argument("--type", default="gn", choices=["gn", "hy", "dq"],
                          help="板块类型: gn=概念, hy=行业, dq=地区 (默认 gn)")
    p_boards.add_argument("--sort", default="pxChangeRate",
                          help="排序字段 (默认 pxChangeRate 涨跌幅)")
    p_boards.add_argument("--max-pages", type=int, default=None,
                          help="最大分页数(默认全量)")
    p_boards.add_argument("--with-stocks", action="store_true",
                          help="一并采集每个板块的全部成分股(个股明细)")
    p_boards.add_argument("--limit", type=int, default=None,
                          help="仅采集前 N 个板块(配合 --with-stocks 使用)")
    p_boards.add_argument("--output-dir", default=None,
                          help="输出目录")

    # detail 子命令
    p_detail = sub.add_parser("detail", help="采集题材下个股明细")
    p_detail.add_argument("--code", required=True,
                          help="板块代码，如 GN886033")
    p_detail.add_argument("--type", default="gn", choices=["gn", "hy", "dq"],
                          help="板块类型 (默认 gn)")
    p_detail.add_argument("--sort", default="countBoard",
                          help="排序字段 (默认 countBoard 连板数)")
    p_detail.add_argument("--output-dir", default=None,
                          help="输出目录")

    args = parser.parse_args()

    # 默认输出目录: 项目 concept 目录
    if args.output_dir is None:
        args.output_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "concept")
    args.output_dir = os.path.abspath(args.output_dir)

    if args.command == "boards":
        cmd_boards(args)
    elif args.command == "detail":
        cmd_detail(args)


if __name__ == "__main__":
    main()