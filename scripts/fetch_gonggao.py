#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
东方财富公告大全采集脚本（按月存储 CSV）

接口（公开，无需 Token/签名/Cookie）:
    GET https://np-anotice-stock.eastmoney.com/api/security/ann
    详见 docs/东方财富公告大全接口用法.md

存储: data/gonggao/YYYY-MM.csv（按公告时间(披露日)所在月份分月；UTF-8 带 BOM，Excel 可直接打开）
列:
    公告时间   display_time（实际披露时间，精确到秒；缺失时回退 notice_date）
    公告日期   notice_date（YYYY-MM-DD；公告所属交易日，晚间披露的会归到下一交易日，见下方说明）
    公司代码   多证券公告用 ; 连接
    公司名     多证券公告用 ; 连接
    公告分类   多分类公告用 ; 连接
    公告标题   去掉了开头的"公司简称:"前缀
    art_code   公告唯一 ID（去重键）
    详情链接   https://data.eastmoney.com/notices/detail/{代码}/{art_code}.html
    PDF链接    https://pdf.dfcfw.com/pdf/H2_{art_code}_1.pdf
同一 art_code 重复拉取只更新、不重复；文件按 公告时间 倒序。

【重要：公告日期 ≠ 披露日】
    接口按 notice_date 筛选，而 notice_date 是"公告所属交易日"：前一天收盘后（15:00 后）
    披露的公告会归到下一个交易日。例如抓 notice_date=11-13 的 1579 条里，
    1073 条的披露时间(display_time)其实是 11-12 晚上；而 11-13 晚上披露的公告
    要抓 notice_date=11-14 才有。
    因此本脚本把「抓取某披露日 D」实现为抓 notice_date ∈ {D, D+1}（次日不晚于今天），
    保证按"公告时间"筛选的某一天是完整的；页面/接口的时间范围也按公告时间(display_time)的日期筛选。

用法:
    python3 fetch_gonggao.py                         # 今天（实时增量，供 web 轮询复用）
    python3 fetch_gonggao.py 2026-11-12              # 指定披露日（自动含 D+1 的 notice_date）
    python3 fetch_gonggao.py 2026-11-01 2026-11-12   # 日期范围（逐日抓取，已完整抓过的历史日自动跳过）
    python3 fetch_gonggao.py --days 7                # 最近 7 天（含今天）
    python3 fetch_gonggao.py 2026-11-12 --force      # 强制重抓
    python3 fetch_gonggao.py --json                  # JSON 摘要输出（供 web 后端调用）

已抓取记录在 data/gonggao/.done.json（notice_date → 总条数）；
今天、昨天、前天的 notice_date 始终重抓（公告仍在增加/归属日会变），更早的抓过就不再请求。
"""
import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import time

import requests

URL = "https://np-anotice-stock.eastmoney.com/api/security/ann"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}
OUT_DIR = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "gonggao"))
DONE_FILE = os.path.join(OUT_DIR, ".done.json")

COLUMNS = ["公告时间", "公告日期", "公司代码", "公司名", "公告分类", "公告标题", "art_code", "详情链接", "PDF链接"]
PAGE_SIZE = 100
MAX_PAGES = 49  # 实测 page_index>=50 返回空；单日全市场约 1600 条≈16 页，足够


def month_path(month: str) -> str:
    return os.path.join(OUT_DIR, f"{month}.csv")


def fetch_page(day: str, page: int, stock: str = "", retries: int = 3) -> dict:
    params = {
        "sr": "-1", "page_size": str(PAGE_SIZE), "page_index": str(page),
        "ann_type": "A", "client_source": "web", "f_node": "0", "s_node": "0",
        "begin_time": day, "end_time": day,
    }
    if stock:
        params["stock_list"] = stock
    last_err = None
    for i in range(retries):
        try:
            r = requests.get(URL, params=params, headers=HEADERS, timeout=15)
            r.raise_for_status()
            d = r.json()
            if d.get("success") != 1:
                raise RuntimeError(f"东方财富接口返回异常: {str(d)[:200]}")
            return d["data"]
        except (requests.ConnectionError, requests.Timeout) as e:
            last_err = e
            if i < retries - 1:
                time.sleep(1.5 * (i + 1))
    raise last_err


def normalize(it: dict) -> dict:
    """接口原始条目 -> CSV 行（dict）"""
    codes = it.get("codes") or []
    cols = it.get("columns") or []
    art = it.get("art_code", "")
    notice = (it.get("notice_date") or "")[:10]
    disp = (it.get("display_time") or "")[:19]  # 去掉毫秒
    when = disp or (it.get("notice_date") or "")[:19]
    title = (it.get("title") or it.get("title_ch") or "").strip()
    # 标题形如 "贵州茅台:公告标题"，去掉前缀（公司名已单独成列）
    names = [c.get("short_name", "") for c in codes if c.get("short_name")]
    for n in names:
        if title.startswith(n + ":") or title.startswith(n + "："):
            title = title[len(n) + 1:]
            break
    first_code = next((c.get("stock_code") for c in codes if c.get("stock_code")), "")
    return {
        "公告时间": when,
        "公告日期": notice,
        "公司代码": ";".join(c.get("stock_code", "") for c in codes if c.get("stock_code")),
        "公司名": ";".join(names),
        "公告分类": ";".join(c.get("column_name", "") for c in cols if c.get("column_name")),
        "公告标题": title,
        "art_code": art,
        "详情链接": f"https://data.eastmoney.com/notices/detail/{first_code}/{art}.html" if art else "",
        "PDF链接": f"https://pdf.dfcfw.com/pdf/H2_{art}_1.pdf" if art else "",
    }


def fetch_day(day: str, sleep: float = 0.5) -> list:
    """拉取某个公告日期的全部公告，返回 CSV 行列表"""
    rows, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        data = fetch_page(day, page)
        items = data.get("list") or []
        if not items:
            break
        for it in items:
            if it.get("art_code") and it["art_code"] not in seen:
                seen.add(it["art_code"])
                rows.append(normalize(it))
        if page * PAGE_SIZE >= (data.get("total_hits") or 0):
            break
        time.sleep(sleep)
    return rows


def read_month(month: str) -> list:
    p = month_path(month)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def merge_write(month: str, new_rows: list) -> tuple:
    """按 art_code 合并写入月文件（新数据覆盖旧同 ID 行），返回 (新增条数, 月总条数)"""
    existing = read_month(month)
    by_id = {r["art_code"]: r for r in existing if r.get("art_code")}
    added = 0
    for r in new_rows:
        if r["art_code"] not in by_id:
            added += 1
        by_id[r["art_code"]] = r
    merged = sorted(by_id.values(), key=lambda r: (r["公告时间"], r["art_code"]), reverse=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = month_path(month) + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(merged)
    os.replace(tmp, month_path(month))  # 原子替换，避免读到写一半的文件
    return added, len(merged)


def load_done() -> dict:
    try:
        return json.load(open(DONE_FILE, encoding="utf-8"))
    except Exception:
        return {}


def save_done(done: dict):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(DONE_FILE, "w", encoding="utf-8") as f:
        json.dump(done, f, ensure_ascii=False, indent=1, sort_keys=True)


def sync_notice_date(day: str, force: bool = False) -> dict:
    """抓取并落盘某个 notice_date；返回 {day, fetched, added, month_total, skipped}"""
    today = dt.date.today()
    d = dt.datetime.strptime(day, "%Y-%m-%d").date()
    done = load_done()
    # 近 3 天的 notice_date 仍在变化（盘后公告持续归入），始终重抓；更早的抓过就跳过
    if not force and day in done and (today - d).days >= 3:
        return {"day": day, "fetched": 0, "added": 0, "month_total": None, "skipped": True}
    rows = fetch_day(day)
    # 按"公告时间"(披露日)所在月份分月写入；公告时间缺失时回退 notice_date
    by_month = {}
    for r in rows:
        m = (r["公告时间"] or r["公告日期"] or day)[:7]
        by_month.setdefault(m, []).append(r)
    added = 0
    total = 0
    for m, rs in by_month.items():
        a, t = merge_write(m, rs)
        added += a
        total = t
    done = load_done()
    done[day] = len(rows)
    save_done(done)
    return {"day": day, "fetched": len(rows), "added": added, "month_total": total or None, "skipped": False}


def sync_day(day: str, force: bool = False) -> dict:
    """抓取"披露日 day"：抓 notice_date=day 与 day+1（不晚于今天），合并结果"""
    today = dt.date.today()
    d = dt.datetime.strptime(day, "%Y-%m-%d").date()
    targets = [day]
    nxt = d + dt.timedelta(days=1)
    if nxt <= today:
        targets.append(nxt.strftime("%Y-%m-%d"))
    parts = [sync_notice_date(t, force) for t in targets]
    return {
        "day": day,
        "fetched": sum(p["fetched"] for p in parts),
        "added": sum(p["added"] for p in parts),
        "month_total": parts[-1]["month_total"],
        "skipped": all(p["skipped"] for p in parts),
        "notice_dates": targets,
    }


def daterange(a: str, b: str):
    d0 = dt.datetime.strptime(a, "%Y-%m-%d").date()
    d1 = dt.datetime.strptime(b, "%Y-%m-%d").date()
    while d0 <= d1:
        yield d0.strftime("%Y-%m-%d")
        d0 += dt.timedelta(days=1)


def norm_date(s: str) -> str:
    s = s.strip().replace("/", "-")
    if re.fullmatch(r"\d{8}", s):
        s = f"{s[:4]}-{s[4:6]}-{s[6:]}"
    dt.datetime.strptime(s, "%Y-%m-%d")  # 校验
    return s


def main():
    ap = argparse.ArgumentParser(description="东方财富公告采集（按月 CSV 存储 data/gonggao/）")
    ap.add_argument("dates", nargs="*", help="0 个=今天；1 个=该日；2 个=起止日期（含）")
    ap.add_argument("--days", type=int, default=0, help="最近 N 天（含今天），与 dates 互斥")
    ap.add_argument("--force", action="store_true", help="忽略已抓取记录强制重抓")
    ap.add_argument("--json", action="store_true", help="JSON 摘要输出")
    a = ap.parse_args()

    today = dt.date.today().strftime("%Y-%m-%d")
    if a.days > 0:
        start = (dt.date.today() - dt.timedelta(days=a.days - 1)).strftime("%Y-%m-%d")
        days = list(daterange(start, today))
    elif len(a.dates) == 0:
        days = [today]
    elif len(a.dates) == 1:
        days = [norm_date(a.dates[0])]
    elif len(a.dates) == 2:
        days = list(daterange(norm_date(a.dates[0]), norm_date(a.dates[1])))
    else:
        ap.error("dates 最多 2 个（起止日期）")

    results, err = [], None
    for day in days:
        try:
            r = sync_day(day, a.force)
        except Exception as e:  # noqa: BLE001
            err = f"{day}: {e}"
            if not a.json:
                print(f"❌ {err}", file=sys.stderr)
            break
        results.append(r)
        if not a.json:
            if r["skipped"]:
                print(f"{day}  已抓取过，跳过（--force 可重抓）")
            else:
                print(f"{day}  拉取 {r['fetched']} 条，新增 {r['added']} 条，当月共 {r['month_total']} 条")

    if a.json:
        summary = {
            "days": results,
            "fetched": sum(r["fetched"] for r in results),
            "added": sum(r["added"] for r in results),
        }
        if err:
            summary["error"] = err[:300]
        print(json.dumps(summary, ensure_ascii=False))
        sys.exit(1 if err else 0)
    if err:
        sys.exit(1)


if __name__ == "__main__":
    main()
