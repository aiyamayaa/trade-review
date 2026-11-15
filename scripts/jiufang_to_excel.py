#!/usr/bin/env python3
"""
将九方智投 boards --with-stocks 输出的 JSON 转为 Excel，并计算衍生指标。

用法:
    python jiufang_to_excel.py <input_json> [output_xlsx]

衍生指标:
    - 板块成交额/流通市值 (amount_to_mcap): 成交额 / 成分股流通市值合计
    - 板块净流入/流通市值 (inflow_to_mcap): 主力净流入 / 成分股流通市值合计
    - 个股市值通过 成交额 / (换手率/100) 反推

依赖:
    pip install openpyxl
"""

import sys
import os
import json
from datetime import datetime

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
    from openpyxl.utils import get_column_letter
except ImportError:
    print("缺少依赖 openpyxl，请先执行: pip install openpyxl", file=sys.stderr)
    sys.exit(1)


# ============================================================
# 样式定义
# ============================================================

HEADER_FONT = Font(name="微软雅黑", bold=True, size=11, color="FFFFFF")
HEADER_FILL = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)

DATA_FONT = Font(name="微软雅黑", size=10)
DATA_ALIGN = Alignment(horizontal="center", vertical="center")
LEFT_ALIGN = Alignment(horizontal="left", vertical="center")

RED_FONT = Font(name="微软雅黑", size=10, color="CC0000")
GREEN_FONT = Font(name="微软雅黑", size=10, color="008000")

THIN_BORDER = Border(
    left=Side(style="thin", color="D9D9D9"),
    right=Side(style="thin", color="D9D9D9"),
    top=Side(style="thin", color="D9D9D9"),
    bottom=Side(style="thin", color="D9D9D9"),
)

# 涨跌幅条件格式颜色
def pct_font(val):
    if val is None:
        return DATA_FONT
    if val > 0:
        return RED_FONT
    elif val < 0:
        return GREEN_FONT
    return DATA_FONT


# ============================================================
# 计算函数
# ============================================================

def calc_stock_mcap(stock):
    """通过成交额/换手率反推流通市值"""
    amount = stock.get("amount")
    turnover = stock.get("turnover_rate")
    if amount and turnover and turnover > 0:
        return amount / (turnover / 100)
    return None


def calc_board_metrics(board):
    """计算板块级别衍生指标"""
    stocks = board.get("stocks", [])
    total_mcap = 0
    for s in stocks:
        mcap = calc_stock_mcap(s)
        if mcap:
            total_mcap += mcap

    board_amount = board.get("amount") or 0
    board_inflow = board.get("main_net_inflow") or 0

    amount_to_mcap = (board_amount / total_mcap * 100) if total_mcap > 0 else None
    inflow_to_mcap = (board_inflow / total_mcap * 100) if total_mcap > 0 else None

    return {
        "total_mcap": total_mcap,
        "amount_to_mcap": round(amount_to_mcap, 2) if amount_to_mcap else None,
        "inflow_to_mcap": round(inflow_to_mcap, 2) if inflow_to_mcap else None,
    }


# ============================================================
# Excel 写入
# ============================================================

def write_sheet(ws, headers, rows, col_widths=None):
    """通用写入 sheet"""
    # 表头
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGN
        cell.border = THIN_BORDER

    # 数据行
    for row_idx, row_data in enumerate(rows, 2):
        for col_idx, val in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = DATA_FONT
            cell.alignment = DATA_ALIGN
            cell.border = THIN_BORDER

    # 列宽
    if col_widths:
        for col_idx, w in enumerate(col_widths, 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = w

    # 冻结首行
    ws.freeze_panes = "A2"
    # 自动筛选
    ws.auto_filter.ref = ws.dimensions


def build_board_rows(boards):
    """构建板块汇总行"""
    rows = []
    for b in boards:
        metrics = calc_board_metrics(b)
        lead = b.get("lead_stock") or {}
        rows.append([
            b.get("code"),
            b.get("name"),
            b.get("change_pct"),
            b.get("amplitude"),
            b.get("limit_up_count"),
            b.get("rise_count"),
            b.get("fall_count"),
            b.get("flat_count"),
            b.get("member_count"),
            _fmt_amount(b.get("amount")),
            _fmt_amount(b.get("main_net_inflow")),
            _fmt_amount(metrics["total_mcap"]),
            metrics["amount_to_mcap"],
            metrics["inflow_to_mcap"],
            lead.get("name"),
            lead.get("change_pct"),
            lead.get("board"),
        ])
    return rows


def _clean_text(v):
    """清理字符串中的非法控制字符"""
    if not isinstance(v, str):
        return v
    import re
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', v)


def build_stock_rows(boards):
    """构建成分股明细行"""
    rows = []
    for b in boards:
        board_name = b.get("name")
        board_code = b.get("code")
        for s in b.get("stocks", []):
            mcap = calc_stock_mcap(s)
            rows.append([
                board_code,
                board_name,
                s.get("code"),
                s.get("name"),
                s.get("last_price"),
                s.get("change_pct"),
                s.get("board"),
                s.get("board_type"),
                s.get("first_limit_time"),
                _fmt_amount(s.get("limit_amount")),
                _fmt_amount(s.get("amount")),
                s.get("turnover_rate"),
                s.get("volume_ratio"),
                s.get("amplitude"),
                s.get("five_day_change"),
                _fmt_amount(s.get("main_net_inflow")),
                _fmt_amount(mcap),
                s.get("pe_ratio"),
                s.get("pb_ratio"),
                ", ".join(s.get("special_labels") or []),
                _clean_text(s.get("relation_reason")),
            ])
    return rows


def _fmt_amount(v):
    """金额转为亿元"""
    if v is None:
        return None
    return round(v / 1e8, 2)


# ============================================================
# 主流程
# ============================================================

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else input_path.replace(".json", ".xlsx")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    boards = data.get("boards", [])
    meta = data.get("meta", {})
    print(f"读取 {len(boards)} 个板块")

    wb = Workbook()

    # ---- Sheet 1: 板块汇总 ----
    ws1 = wb.active
    ws1.title = "板块汇总"
    board_headers = [
        "板块代码", "板块名称", "涨跌幅(%)", "振幅(%)",
        "涨停家数", "上涨家数", "下跌家数", "平盘家数", "成分股数量",
        "成交额(亿)", "主力净流入(亿)", "流通市值合计(亿)",
        "成交额/市值(%)", "净流入/市值(%)",
        "领涨股", "领涨股涨跌幅(%)", "领涨股连板",
    ]
    board_rows = build_board_rows(boards)
    write_sheet(ws1, board_headers, board_rows, col_widths=[14, 22, 10, 10, 10, 10, 10, 10, 12, 14, 14, 16, 14, 14, 14, 14, 12])

    # ---- Sheet 2: 成分股明细 ----
    ws2 = wb.create_sheet("成分股明细")
    stock_headers = [
        "板块代码", "板块名称",
        "股票代码", "股票名称", "最新价", "涨跌幅(%)",
        "连板数", "板类型", "首次涨停",
        "封单金额(亿)", "成交额(亿)", "换手率(%)", "量比", "振幅(%)",
        "5日涨幅(%)", "主力净流入(亿)", "流通市值(亿)",
        "市盈率", "市净率",
        "特殊标签", "关联理由",
    ]
    stock_rows = build_stock_rows(boards)
    write_sheet(ws2, stock_headers, stock_rows, col_widths=[14, 22, 12, 12, 10, 10, 8, 8, 10, 14, 14, 10, 8, 10, 10, 14, 14, 10, 10, 20, 40])

    # ---- Sheet 3: 说明 ----
    ws3 = wb.create_sheet("说明")
    info_lines = [
        ["数据来源", meta.get("source", "九方智投")],
        ["板块类型", meta.get("board_type", "")],
        ["板块数量", len(boards)],
        ["生成时间", meta.get("generated_at", "")],
        ["导出时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ["", ""],
        ["指标说明", ""],
        ["成交额/市值(%)", "板块总成交额 / 成分股流通市值合计 × 100，反映板块换手活跃度"],
        ["净流入/市值(%)", "板块主力净流入 / 成分股流通市值合计 × 100，反映资金相对强度"],
        ["流通市值", "通过 成交额 / (换手率/100) 反推，为近似值"],
        ["", ""],
        ["注意", "个股市值通过换手率反推，停牌股或无换手率数据的股票无法计算市值，会被跳过"],
    ]
    for row_idx, (k, v) in enumerate(info_lines, 1):
        ws3.cell(row=row_idx, column=1, value=k).font = Font(name="微软雅黑", bold=True, size=10)
        ws3.cell(row=row_idx, column=2, value=v).font = Font(name="微软雅黑", size=10)
    ws3.column_dimensions["A"].width = 20
    ws3.column_dimensions["B"].width = 60

    wb.save(output_path)
    print(f"✅ 已保存到: {output_path}")


if __name__ == "__main__":
    main()