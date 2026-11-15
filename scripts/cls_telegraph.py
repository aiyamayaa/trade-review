#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
财联社电报接口封装（零密钥，本地签名）
接口: https://www.cls.cn/v1/roll/get_roll_list
用法:
    from cls_telegraph import ClsTelegraph
    cls = ClsTelegraph()
    items = cls.fetch(rn=20)                    # 最新20条
    items = cls.fetch(category="red")           # 只要重要红标电报
    items = cls.fetch(last_time=<ctime>)        # 往前翻页
    for it in cls.iter_all(max_pages=5): ...    # 连续翻页迭代器

命令行:
    python3 cls_telegraph.py -n 20              # 文本摘要（默认）
    python3 cls_telegraph.py --json -n 30       # JSON 输出（供 web 后端调用）
    python3 cls_telegraph.py -c red -p 3        # 重要电报，翻3页
    python3 cls_telegraph.py -d 2026-10-31      # 拉取某天全天电报
    python3 cls_telegraph.py -d 2026-10-31 -c red --json   # 某天红标电报 JSON

历史按天拉取要点（实测结论）:
    - 接口不支持 start_time/end_time 参数（会被忽略）
    - refresh_type=2 翻页不可靠（会偶发忽略 last_time 返回最新页）
    - 可靠做法: 恒用 refresh_type=1 + last_time=<ctime>，返回 ctime < last_time
      的最新一页，逐页向历史回溯，直到越过当天 0 点
"""
import argparse
import datetime
import hashlib
import json
import time

import requests


class ClsTelegraph:
    BASE = "https://www.cls.cn/v1/roll/get_roll_list"
    HEADERS = {
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/125.0 Safari/537.36"),
        "Referer": "https://www.cls.cn/telegraph",
        "Accept": "application/json, text/plain, */*",
    }
    CATEGORIES = {
        "": "全部（默认）",
        "red": "重要（加红加粗的电报）",
        "announcement": "公告",
        "watch": "盘中/题材观察（连板分析等）",
        "hk_us": "港美股",
        "fund": "基金",
        "remind": "提醒（预告等）",
    }

    @staticmethod
    def make_sign(params: dict) -> str:
        """sign = md5( sha1( 参数按key字典序拼成 k=v&k=v 的串 ) )
        纯本地计算，不需要任何账号或密钥。"""
        qs = "&".join(f"{k}={params[k]}" for k in sorted(params))
        sha1 = hashlib.sha1(qs.encode("utf-8")).hexdigest()
        return hashlib.md5(sha1.encode("utf-8")).hexdigest()

    def fetch(self, category="", last_time="", refresh_type=1, rn=20, timeout=15, retries=3):
        """拉一页电报，返回 list[dict]。
        category: 见 self.CATEGORIES
        last_time: 传上一页最早一条的 ctime 即可向前翻页
        refresh_type: 1=最新一页; 传 2 配合 last_time 表示继续翻页
        rn: 每页条数（实测 20 稳定，最大可到 50）
        retries: 网络瞬时故障自动重试次数"""
        params = {
            "app": "CailianpressWeb",
            "category": category,
            "last_time": last_time,
            "os": "web",
            "refresh_type": refresh_type,
            "rn": rn,
            "sv": "8.4.6",
        }
        params["sign"] = self.make_sign(params)
        last_err = None
        for i in range(retries):
            try:
                r = requests.get(self.BASE, params=params, headers=self.HEADERS, timeout=timeout)
                r.raise_for_status()
                data = r.json()
                if data.get("errno") != 0:
                    raise RuntimeError(f"接口返回错误: {data}")
                return data.get("data", {}).get("roll_data", [])
            except (requests.ConnectionError, requests.Timeout) as e:
                last_err = e
                if i < retries - 1:
                    time.sleep(1.5 * (i + 1))  # 1.5s / 3s 退避后重试
        raise last_err

    def iter_all(self, category="", max_pages=10, rn=20, sleep=0.3, last_time=""):
        """连续向前翻页的生成器，最多 max_pages 页。

        注意: 财联社接口在翻页模式(refresh_type=2)下 rn>20 会忽略 last_time
        直接返回最新一页，因此翻页时每页条数强制不超过 20。"""
        seen = set()
        for _ in range(max_pages):
            rtype = 1 if not last_time else 2
            page_rn = rn if not last_time else min(rn, 20)
            items = self.fetch(category=category, last_time=last_time,
                               refresh_type=rtype, rn=page_rn)
            if not items:
                break
            new = [it for it in items if it["id"] not in seen]
            if not new:
                break
            for it in new:
                seen.add(it["id"])
                yield it
            last_time = min(it["ctime"] for it in new)
            time.sleep(sleep)

    def fetch_day(self, date, category="", max_pages=200, rn=20, sleep=0.3):
        """拉取指定某一天（本地时区）的全部电报，按 ctime 倒序返回 list[dict]。

        date: "YYYY-MM-DD" 字符串，或 datetime.date / datetime.datetime 对象
        max_pages: 安全上限（一天约 150~200 条，20 条/页约 10 页，200 足够）
        """
        if isinstance(date, str):
            d = datetime.datetime.strptime(date, "%Y-%m-%d")
        else:
            d = datetime.datetime(date.year, date.month, date.day)
        day_start = int(d.timestamp())
        day_end = day_start + 86400

        items_all, last_time, seen = [], day_end, set()
        for _ in range(max_pages):
            # 关键: 恒用 refresh_type=1，refresh_type=2 翻页会偶发忽略 last_time
            items = self.fetch(category=category, last_time=last_time,
                               refresh_type=1, rn=rn)
            if not items:
                break
            new = [it for it in items if it["id"] not in seen]
            if not new:
                break
            seen.update(it["id"] for it in new)
            items_all.extend(it for it in new if day_start <= it["ctime"] < day_end)
            min_ct = min(it["ctime"] for it in new)
            if min_ct < day_start:
                break  # 已越过当天最早一条，拉取完成
            last_time = min_ct
            time.sleep(sleep)
        items_all.sort(key=lambda x: x["ctime"], reverse=True)
        return items_all

    @staticmethod
    def brief_of(it: dict, width=80) -> str:
        """把一条电报整理成一行摘要文本。"""
        ts = time.strftime("%m-%d %H:%M", time.localtime(it.get("ctime", 0)))
        mark = "★" if it.get("level") == "A" else " "
        title = (it.get("title") or it.get("brief") or "").replace("\n", " ")
        stocks = ",".join(s.get("stock_name", "") for s in it.get("stock_list") or [])[:30]
        line = f"[{ts}]{mark} {title[:width]}"
        if stocks:
            line += f"  ({stocks})"
        return line


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="财联社电报获取")
    p.add_argument("-c", "--category", default="", help="分类: red/announcement/watch/hk_us/fund/remind")
    p.add_argument("-n", "--num", type=int, default=20, help="条数")
    p.add_argument("-p", "--pages", type=int, default=1, help="翻页数")
    p.add_argument("-t", "--last-time", default="", help="翻页起始 ctime（向前翻）")
    p.add_argument("-d", "--date", default="", help="按天拉取历史: YYYY-MM-DD（与 -n/-p/-t 互斥）")
    p.add_argument("--json", action="store_true", help="输出 JSON（供 web 后端）")
    a = p.parse_args()

    cls = ClsTelegraph()

    if a.date:
        items = cls.fetch_day(a.date, category=a.category)
    else:
        items = []
        for it in cls.iter_all(category=a.category, max_pages=a.pages,
                                rn=min(max(a.num, 1), 50), last_time=a.last_time):
            items.append(it)
            if len(items) >= a.num:
                break

    if a.json:
        print(json.dumps({"count": len(items), "items": items}, ensure_ascii=False))
    else:
        for it in items:
            print(cls.brief_of(it))
