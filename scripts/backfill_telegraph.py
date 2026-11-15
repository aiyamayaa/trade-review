#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电报历史补齐：按天拉取财联社电报（cls_telegraph.fetch_day），合并写入
data/telegraph/YYYYMMDD.json（与 web 后端落盘结构一致，前端"本地缓存"可直接显示）。

原理: 恒用 refresh_type=1 + last_time 逐页回溯（refresh_type=2 翻页不可靠），
      因此可以回补任意历史日期（前提：财联社服务端仍保留该天数据）。

用法:
    python3 backfill_telegraph.py 2026-10-24 2026-10-25   # 补指定日期（可多个）
    python3 backfill_telegraph.py --auto                  # 自动补齐：从已有最早日期到昨天，逐日合并（幂等）
    python3 backfill_telegraph.py --auto --since 2026-10-15   # 指定起点
"""
import argparse
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cls_telegraph import ClsTelegraph  # noqa: E402

TELE_DIR = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "telegraph"))


def slim(it: dict) -> dict:
    """原始电报 -> 精简结构（与 web/server/server.js 的 slimTelegraphItems 一致）"""
    return {
        "id": it["id"],
        "ctime": it["ctime"],
        "modified_time": it.get("modified_time"),
        "level": it.get("level") or "",
        "title": it.get("title") or "",
        "brief": it.get("brief") or "",
        "content": it.get("content") or "",
        "stocks": [
            {"name": s.get("name"), "id": s.get("StockID"), "change_pct": s.get("RiseRange")}
            for s in (it.get("stock_list") or [])
        ],
        "plates": [
            (p.get("plate_name") or p.get("name"))
            for p in (it.get("plate_list") or [])
            if p.get("plate_name") or p.get("name")
        ],
        "reading_num": it.get("reading_num"),
    }


def merge_write(day: str, slim_items: list) -> int:
    """按 id 去重合并写入当天文件，返回新增条数"""
    path = os.path.join(TELE_DIR, f"{day}.json")
    existing = []
    if os.path.exists(path):
        try:
            existing = json.load(open(path, encoding="utf-8")).get("items") or []
        except Exception:
            existing = []
    seen = {i["id"] for i in existing}
    fresh = [s for s in slim_items if s["id"] not in seen]
    merged = existing + fresh
    merged.sort(key=lambda x: x["ctime"], reverse=True)
    out = {
        "meta": {
            "date": day,
            "count": len(merged),
            "updated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "items": merged,
    }
    os.makedirs(TELE_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    return len(fresh)


def backfill(date_str: str, cls: ClsTelegraph):
    day = date_str.replace("-", "").replace("/", "")
    d = f"{day[:4]}-{day[4:6]}-{day[6:]}"
    print(f"📖 拉取 {d} 全天电报 ...", flush=True)
    try:
        items = cls.fetch_day(d, max_pages=400)
    except Exception as e:
        print(f"  ❌ {d} 拉取失败: {e}", file=sys.stderr)
        return
    if not items:
        print(f"  ⚠ {d} 无数据（财联社可能已不保留该天）")
        return
    fresh = merge_write(day, [slim(it) for it in items])
    total = json.load(open(os.path.join(TELE_DIR, f"{day}.json"), encoding="utf-8"))["meta"]["count"]
    cts = [i["ctime"] for i in items]
    print(f"  ✅ 拉到 {len(items)} 条, 新增 {fresh} 条, 当天缓存共 {total} 条 "
          f"({time.strftime('%H:%M', time.localtime(min(cts)))}~{time.strftime('%H:%M', time.localtime(max(cts)))})")


def list_days() -> list:
    days = []
    if os.path.isdir(TELE_DIR):
        for n in os.listdir(TELE_DIR):
            if n.startswith("telegraph_") or not n.endswith(".json"):
                continue
            d = n.replace(".json", "")
            if len(d) == 8 and d.isdigit():
                days.append(d)
    return sorted(days)


def main():
    p = argparse.ArgumentParser(description="电报历史按天补齐（写入 data/telegraph/）")
    p.add_argument("dates", nargs="*", help="日期列表: 2026-10-24 或 20261024")
    p.add_argument("--auto", action="store_true", help="自动补齐：从起点到昨天逐日合并（幂等）")
    p.add_argument("--since", default="", help="auto 模式起点 YYYY-MM-DD（默认取已有最早文件日期）")
    a = p.parse_args()

    cls = ClsTelegraph()

    if a.auto:
        if a.since:
            start = a.since.replace("-", "")
        else:
            days = list_days()
            if not days:
                print("data/telegraph/ 为空且未指定 --since，无法确定起点")
                sys.exit(1)
            start = days[0]
        end = dt.date.today() - dt.timedelta(days=1)
        d = dt.datetime.strptime(start, "%Y%m%d").date()
        print(f"🔁 自动补齐 {d} ~ {end}（已存在文件也会全量合并去重）")
        while d <= end:
            backfill(d.strftime("%Y%m%d"), cls)
            d += dt.timedelta(days=1)
    elif a.dates:
        for x in a.dates:
            backfill(x, cls)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
