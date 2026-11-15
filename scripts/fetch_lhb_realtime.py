#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开盘啦"实时龙虎榜"采集脚本（盘中主力净流入/涨幅/成交排行）

注意: 这不是交易所收盘后披露的正式龙虎榜，而是开盘啦对盘中资金、涨幅、成交的实时排行。

接口（应用侧接口，非正式公开 API，字段/认证可能调整）:
    https://apphq.longhuvip.com/w1/api/index.php
    POST application/x-www-form-urlencoded, a=RealRankingInfo_W8, c=NewStockRanking
    分页: st=60（每页最多 60 条），index 为偏移量（第1页=0、第2页=60、第3页=120）
    区间: 额外传 RStart/REnd（HHMM），取盘中某段时间的排名

认证: 项目根 .env 中的 KPL_USER_ID / KPL_TOKEN（由 scripts/_env.py 自动加载）。
      文档说明"部分版本/权限可能要求"，无凭证时先尝试，返回空再提示配置。

快照存储（实时数据无历史接口，每次拉取都按"交易日 + 时间点"落盘，便于盘后回看）:
    data/lhb_realtime/{YYYY-MM-DD}/{HHMM}.json            全时段排名
    data/lhb_realtime/{YYYY-MM-DD}/{HHMM}_{RStart}-{REnd}.json   区间排名
    list 为空（非交易日/非交易时段）时不落盘。

用法:
    python3 fetch_lhb_realtime.py                    # 拉第 1 页（60 条）
    python3 fetch_lhb_realtime.py --pages 3          # 拉前 3 页（180 条）
    python3 fetch_lhb_realtime.py --start 0925 --end 0930   # 区间排名（开盘后前5分钟）
    python3 fetch_lhb_realtime.py --json             # JSON 输出（供 web 后端调用）
    python3 fetch_lhb_realtime.py --no-save          # 只拉不落盘
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import sys
import time
import uuid

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402,F401  加载项目根 .env

URL = "https://apphq.longhuvip.com/w1/api/index.php"
OUT_DIR = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "lhb_realtime"))
PAGE_SIZE = 60

# list 内每项为数组，文档约定的常用下标（未经真实数据验证；原始数组保存在 raw 字段）
FIELD_INDEX = {
    "code": 0,        # 股票代码
    "name": 1,        # 股票名称
    "plate": 4,       # 所属板块/概念
    "price": 5,       # 现价
    "pct": 6,         # 涨幅%
    "amount": 7,      # 成交额
    "net_inflow": 13,  # 主力净额
    "net_ratio": 19,  # 净流占比
    "board_desc": 23,  # 连板说明
    "popularity": 58,  # 人气值
}


def _device_id() -> str:
    env = os.environ.get("KPL_DEVICE_ID")
    if env:
        return env
    seed = f"ava-review-{platform.node()}-{uuid.getnode()}"
    return str(uuid.UUID(hashlib.md5(seed.encode()).hexdigest()))


def has_credentials() -> bool:
    return bool(os.environ.get("KPL_USER_ID") and os.environ.get("KPL_TOKEN"))


def _headers() -> dict:
    return {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "User-Agent": os.environ.get("KPL_UA", "Mozilla/5.0 (Linux; Android 12) Dalvik/2.1.0"),
    }


def _payload(page: int, start: str = "", end: str = "") -> dict:
    p = {
        "Order": "1",
        "a": "RealRankingInfo_W8",
        "st": str(PAGE_SIZE),
        "c": "NewStockRanking",
        "PhoneOSNew": "1",
        "DeviceID": _device_id(),
        "VerSion": os.environ.get("KPL_VERSION", "5.18.0.0"),
        "index": str(page * PAGE_SIZE),
        "apiv": os.environ.get("KPL_APIV", "w36"),
        "Type": "1",
        "FilterMotherboard": "0",
        "Filter": "0",
        "Ratio": "6",
        "FilterTIB": "0",
        "FilterGem": "0",
    }
    # 有凭证才带（文档：部分版本/权限可能要求认证）
    if has_credentials():
        p["UserID"] = os.environ["KPL_USER_ID"]
        p["Token"] = os.environ["KPL_TOKEN"]
    if start and end:
        p["RStart"], p["REnd"] = start, end
    return p


def _norm_row(row) -> dict:
    """数组 -> 命名字典；保留原始数组 raw"""
    if not isinstance(row, list):
        return {"raw": row}
    d = {k: (row[i] if len(row) > i else None) for k, i in FIELD_INDEX.items()}
    d["raw"] = row
    return d


def fetch_page(page: int, start: str = "", end: str = "", retries: int = 3) -> dict:
    last_err = None
    for i in range(retries):
        try:
            r = requests.post(URL, data=_payload(page, start, end), headers=_headers(), timeout=15)
            r.raise_for_status()
            data = r.json()
            if str(data.get("errcode")) != "0":
                raise RuntimeError(f"接口返回异常: {json.dumps(data, ensure_ascii=False)[:200]}")
            return data
        except (requests.ConnectionError, requests.Timeout) as e:
            last_err = e
            if i < retries - 1:
                time.sleep(1.5 * (i + 1))
    raise last_err


def _day_of(data: dict) -> str:
    """接口 Day 字段可能是 ['2026-11-15'] 或 '2026-11-15'"""
    d = data.get("Day")
    if isinstance(d, list):
        d = d[0] if d else ""
    return str(d or dt.date.today().strftime("%Y-%m-%d"))


def fetch_snapshot(pages: int = 1, start: str = "", end: str = "", sleep: float = 1.0) -> dict:
    """拉取 pages 页，合并为一份快照。

    返回 {day, time, ts, count, range, items:[...], has_credentials, empty}
    """
    items, meta = [], {}
    for p in range(pages):
        data = fetch_page(p, start, end)
        if p == 0:
            meta = data
        rows = data.get("list") or []
        items.extend(_norm_row(x) for x in rows)
        if len(rows) < PAGE_SIZE:  # 不足一页说明已到末尾
            break
        time.sleep(sleep)
    ts = meta.get("Time")
    try:
        tstr = dt.datetime.fromtimestamp(int(ts)).strftime("%H:%M:%S")
    except (TypeError, ValueError):
        tstr = dt.datetime.now().strftime("%H:%M:%S")
    return {
        "day": _day_of(meta),
        "time": tstr,
        "ts": ts,
        "count": meta.get("Count"),
        "range": f"{start}-{end}" if (start and end) else "",
        "items": items,
        "empty": not items,
        "has_credentials": has_credentials(),
        "fetched_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def snapshot_path(snap: dict) -> str:
    hhmm = snap["time"].replace(":", "")[:4]
    suffix = f"_{snap['range']}" if snap.get("range") else ""
    return os.path.join(OUT_DIR, snap["day"], f"{hhmm}{suffix}.json")


def save_snapshot(snap: dict) -> str:
    p = snapshot_path(snap)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False)
    return p


def main():
    ap = argparse.ArgumentParser(description="开盘啦实时龙虎榜采集（快照落盘 data/lhb_realtime/）")
    ap.add_argument("--pages", type=int, default=1, help="页数（每页 60 条，默认 1）")
    ap.add_argument("--start", default="", help="区间开始 HHMM，如 0925（需同时指定 --end）")
    ap.add_argument("--end", default="", help="区间结束 HHMM，如 0930")
    ap.add_argument("--json", action="store_true", help="JSON 输出（供 web 后端）")
    ap.add_argument("--no-save", action="store_true", help="只拉取不落盘")
    a = ap.parse_args()

    if bool(a.start) != bool(a.end):
        ap.error("--start 与 --end 必须同时指定")

    try:
        snap = fetch_snapshot(max(1, a.pages), a.start, a.end)
    except Exception as e:  # noqa: BLE001
        if a.json:
            print(json.dumps({"error": str(e)[:300]}, ensure_ascii=False))
            sys.exit(1)
        print(f"❌ 拉取失败: {e}", file=sys.stderr)
        sys.exit(1)

    snap["saved"] = False
    if not snap["empty"] and not a.no_save:
        snap["file"] = save_snapshot(snap)
        snap["saved"] = True

    if a.json:
        print(json.dumps(snap, ensure_ascii=False))
        return
    print(f"{snap['day']} {snap['time']} 共 {len(snap['items'])} 条"
          f"（接口 Count={snap['count']}）{'  已落盘 ' + snap['file'] if snap['saved'] else ''}")
    if snap["empty"]:
        hint = "" if snap["has_credentials"] else "（.env 未配置 KPL_USER_ID/KPL_TOKEN）"
        print(f"  ⚠ 列表为空：可能是非交易日/非交易时段/无权限{hint}")
    for it in snap["items"][:10]:
        print(f"  {it.get('code')} {it.get('name')} 板块:{it.get('plate')} 现价:{it.get('price')} "
              f"涨幅:{it.get('pct')}% 成交额:{it.get('amount')} 主力净额:{it.get('net_inflow')} "
              f"人气:{it.get('popularity')}")


if __name__ == "__main__":
    main()
