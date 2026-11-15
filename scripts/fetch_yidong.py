#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开盘啦"板块竞价异动"采集脚本（集合竞价阶段板块异动）

接口（应用侧接口，非正式公开 API，字段/认证可能调整）:
    实时: https://apphwhq.longhuvip.com/w1/api/index.php        （当前交易日）
    历史: https://apphis.longhuvip.com/w1/api/index.php         （额外传 Day=YYYY-MM-DD）
    POST application/x-www-form-urlencoded, a=GetBKJJ_W36, c=StockBidYiDong

认证（只用环境变量，绝不写入代码/文档/仓库）:
    推荐写在项目根目录 .env（由 scripts/_env.py 自动加载；shell 中 export 的值优先）
    KPL_USER_ID   开盘啦账户标识
    KPL_TOKEN     账户认证信息
    KPL_DEVICE_ID （可选）设备标识，不设则按机器固定生成，避免每次变化
    KPL_VERSION   （可选）客户端版本，默认 5.18.0.0
    KPL_APIV      （可选）客户端协议版本，默认 w36
    KPL_UA        （可选）User-Agent
    HTTPS_PROXY / HTTP_PROXY  （可选）requests 自动识别的代理

缓存: data/yidong/yidong_YYYY-MM-DD.json
    - 已缓存且非空的日期直接复用，不再请求（--force 强制重拉）
    - 接口返回三个列表全空（非交易日/未触发/无权限）时不落盘，避免空文件阻止后续重试

用法:
    python3 fetch_yidong.py                       # 实时（当前交易日）
    python3 fetch_yidong.py 2026-11-13            # 指定日期（历史接口）
    python3 fetch_yidong.py 2026-11-12 2026-11-13 # 多个日期
    python3 fetch_yidong.py 2026-11-13 --force    # 忽略缓存重拉
    python3 fetch_yidong.py --json 2026-11-13     # JSON 输出（供 web 后端调用）
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
import _env  # noqa: E402,F401  加载项目根 .env（KPL_USER_ID/KPL_TOKEN 等）

REALTIME_URL = "https://apphwhq.longhuvip.com/w1/api/index.php"
HISTORY_URL = "https://apphis.longhuvip.com/w1/api/index.php"

OUT_DIR = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "yidong"))

# 列表项数组位置含义（文档约定，未经真实数据验证；原始数组也一并保存在 raw 字段中）
ITEM_FIELDS = ["code", "name", "burst", "amount", "strength", "net_inflow"]


def _device_id() -> str:
    """优先用环境变量；否则按机器信息生成稳定 UUID（避免每次请求设备标识变化）"""
    env = os.environ.get("KPL_DEVICE_ID")
    if env:
        return env
    seed = f"ava-review-{platform.node()}-{uuid.getnode()}"
    return str(uuid.UUID(hashlib.md5(seed.encode()).hexdigest()))


def _payload(day: str = "") -> dict:
    p = {
        "a": "GetBKJJ_W36",
        "c": "StockBidYiDong",
        "PhoneOSNew": "1",
        "DeviceID": _device_id(),
        "VerSion": os.environ.get("KPL_VERSION", "5.18.0.0"),
        "apiv": os.environ.get("KPL_APIV", "w36"),
        # 无凭证时仍会请求（实测返回空列表），由调用方根据空结果提示配置凭证
        "UserID": os.environ.get("KPL_USER_ID", ""),
        "Token": os.environ.get("KPL_TOKEN", ""),
    }
    if day:
        p["Day"] = day
    return p


def has_credentials() -> bool:
    return bool(os.environ.get("KPL_USER_ID") and os.environ.get("KPL_TOKEN"))


def _headers() -> dict:
    return {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "User-Agent": os.environ.get("KPL_UA", "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"),
    }


def _norm_item(it) -> dict:
    """数组项 -> 命名字典；保留原始数组 raw（字段顺序若变化可回看原始数据）"""
    if not isinstance(it, list):
        return {"raw": it}
    d = {ITEM_FIELDS[i]: it[i] for i in range(min(len(it), len(ITEM_FIELDS)))}
    d["raw"] = it
    return d


def fetch_remote(day: str = "", retries: int = 3) -> dict:
    """请求接口，day 为空=实时；返回 {date,new,continued,other,errcode}"""
    url = HISTORY_URL if day else REALTIME_URL
    last_err = None
    for i in range(retries):
        try:
            r = requests.post(url, data=_payload(day), headers=_headers(), timeout=15)
            r.raise_for_status()
            data = r.json()
            if str(data.get("errcode")) != "0":
                raise RuntimeError(f"接口返回异常: {json.dumps(data, ensure_ascii=False)[:200]}")
            return {
                "date": data.get("Day") or day,
                "new": [_norm_item(x) for x in (data.get("List1") or [])],
                "continued": [_norm_item(x) for x in (data.get("List2") or [])],
                "other": [_norm_item(x) for x in (data.get("List3") or [])],
            }
        except (requests.ConnectionError, requests.Timeout) as e:
            last_err = e
            if i < retries - 1:
                time.sleep(1.5 * (i + 1))
    raise last_err


def cache_path(day: str) -> str:
    return os.path.join(OUT_DIR, f"yidong_{day}.json")


def load_cache(day: str):
    p = cache_path(day)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return None
    return None


def get_day(day: str = "", force: bool = False) -> dict:
    """取某天数据：缓存命中直接返回；否则请求并（非空时）落盘。

    返回 {date,new,continued,other,from_cache,saved,empty,has_credentials}
    """
    today = dt.date.today().strftime("%Y-%m-%d")
    # 实时（day 为空）视为当天；当天数据竞价结束后才稳定，实时模式不读缓存
    key = day or today
    if day and day != today and not force:
        c = load_cache(day)
        if c and (c.get("new") or c.get("continued") or c.get("other")):
            c["from_cache"] = True
            return c

    data = fetch_remote(day if (day and day != today) else "")
    real_day = data.get("date") or key
    empty = not (data["new"] or data["continued"] or data["other"])
    result = {
        "date": real_day,
        "new": data["new"],
        "continued": data["continued"],
        "other": data["other"],
        "fetched_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    saved = False
    if not empty:
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(cache_path(real_day), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        saved = True
    result.update({
        "from_cache": False,
        "saved": saved,
        "empty": empty,
        "has_credentials": has_credentials(),
    })
    return result


def main():
    ap = argparse.ArgumentParser(description="开盘啦板块竞价异动采集（缓存到 data/yidong/）")
    ap.add_argument("dates", nargs="*", help="日期 YYYY-MM-DD（可多个；不传=实时）")
    ap.add_argument("--force", action="store_true", help="忽略缓存强制重拉")
    ap.add_argument("--json", action="store_true", help="JSON 输出（供 web 后端）")
    a = ap.parse_args()

    days = [d.strip().replace("/", "-") for d in a.dates] or [""]
    results = []
    for d in days:
        if len(d) == 8 and d.isdigit():  # 兼容 20261113
            d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        try:
            results.append(get_day(d, a.force))
        except Exception as e:  # noqa: BLE001
            if a.json:
                print(json.dumps({"error": str(e)[:300]}, ensure_ascii=False))
                sys.exit(1)
            print(f"❌ {d or '实时'} 失败: {e}", file=sys.stderr)

    if a.json:
        print(json.dumps(results[0] if len(results) == 1 else results, ensure_ascii=False))
        return
    for r in results:
        tag = "缓存" if r["from_cache"] else ("已落盘" if r["saved"] else "未落盘")
        print(f"{r['date']} [{tag}] 新增 {len(r['new'])} | 延续 {len(r['continued'])} | 其他 {len(r['other'])}")
        if r.get("empty"):
            hint = "" if r["has_credentials"] else "（未设置 KPL_USER_ID/KPL_TOKEN，无凭证时接口返回空）"
            print(f"  ⚠ 三个列表均为空：可能是非交易日/未触发/无权限{hint}")
        for k, name in (("new", "今日新增"), ("continued", "昨日延续"), ("other", "其他异动")):
            for it in r[k][:5]:
                print(f"  [{name}] {it.get('code', '')} {it.get('name', '')} 爆量:{it.get('burst', '')} "
                      f"异动额:{it.get('amount', '')} 强度:{it.get('strength', '')} 主力净额:{it.get('net_inflow', '')}")


if __name__ == "__main__":
    main()
