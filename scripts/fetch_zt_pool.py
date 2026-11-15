#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股涨停板池数据采集脚本（数据源：东方财富，公开免密钥）

采集当日的三个池：
    涨停池: https://push2ex.eastmoney.com/getTopicZTPool
    炸板池: https://push2ex.eastmoney.com/getTopicZBPool
    跌停池: https://push2ex.eastmoney.com/getTopicDTPool

输出: data/zt_pool/zt_pool_YYYYMMDD.json（YYYYMMDD 取接口返回的真实交易日 qdate）

注意: 东财该接口会忽略传入的历史日期、始终返回"调用当日"的数据，
      因此只能每天执行一次进行积累（配合 make today / make all），
      无法回溯补历史。

用法:
    python3 fetch_zt_pool.py                       # 采集当日，归档 data/zt_pool/
    python3 fetch_zt_pool.py 20261020              # 同上（日期仅作参考，实际以接口 qdate 为准）
    python3 fetch_zt_pool.py --csv out.csv         # 额外导出 CSV
    python3 fetch_zt_pool.py --report              # 终端打印可读报表

模块调用:
    from fetch_zt_pool import get_pool_items
    data = get_pool_items()   # {'涨停': [...], '炸板': [...], '跌停': [...]}
"""
import argparse
import csv
import datetime as dt
import json
import os
import time

import requests

BASE_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/125.0 Safari/537.36"),
    "Referer": "https://quote.eastmoney.com/",
}


def _fetch_pool(kind: str) -> tuple:
    """kind: 'ZT'=涨停 'ZB'=炸板 'DT'=跌停。返回 (qdate, pool_list)"""
    url = f"https://push2ex.eastmoney.com/getTopic{kind}Pool"
    params = {
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "dpt": "wz.ztzt",
        "Pageindex": "0",
        "pagesize": "10000",
        "sort": "fbt:asc",
        "date": dt.date.today().strftime("%Y%m%d"),
        "_": str(int(time.time() * 1000)),
    }
    r = requests.get(url, params=params, headers=BASE_HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    inner = data.get("data") or {}
    return str(inner.get("qdate") or ""), inner.get("pool") or []


def _fmt_time(v) -> str:
    """东财封板时间如 92500 -> 09:25:00"""
    try:
        s = str(int(v)).zfill(6)
        return f"{s[:2]}:{s[2:4]}:{s[4:6]}"
    except (TypeError, ValueError):
        return ""


def _fmt_amount(v) -> float:
    """金额字段统一为元 -> 转亿元"""
    try:
        return round(float(v) / 1e8, 2)
    except (TypeError, ValueError):
        return 0.0


def _normalize(it: dict) -> dict:
    """东财原始字段 -> 可读字典"""
    zttj = it.get("zttj") or {}
    return {
        "代码": it.get("c", ""),
        "名称": it.get("n", ""),
        "涨跌幅%": round(it.get("zdp", 0), 2),
        "最新价": round(it.get("p", 0) / 1000, 2),
        "连板数": it.get("lbc", 0),
        "首次封板时间": _fmt_time(it.get("fbt")),
        "最后封板时间": _fmt_time(it.get("lbt")),
        "炸板次数": it.get("zbc", 0),
        "封单资金(亿)": _fmt_amount(it.get("fund")),
        "成交额(亿)": _fmt_amount(it.get("amount")),
        "流通市值(亿)": _fmt_amount(it.get("ltsz")),
        "总市值(亿)": _fmt_amount(it.get("tshare")),
        "换手率%": round(it.get("hs", 0), 2),
        "行业板块": it.get("hybk", ""),
        "几日几板": f"{zttj.get('days', 0)}天{zttj.get('ct', 0)}板",
        "所属市场": {"0": "深", "1": "沪"}.get(str(it.get("m", "")), ""),
    }


def get_pool_items() -> dict:
    """拉取当日三个池，返回 {'涨停': [...], '炸板': [...], '跌停': [...], '_qdate': '...'}"""
    qdate = ""
    result = {}
    for kind, name in (("ZT", "涨停"), ("ZB", "炸板"), ("DT", "跌停")):
        q, pool = _fetch_pool(kind)
        qdate = qdate or q
        result[name] = [_normalize(it) for it in pool]
    result["_qdate"] = qdate
    return result


def print_report(data: dict):
    zt, zb, dt_pool = data["涨停"], data["炸板"], data["跌停"]
    print(f"\n  {data.get('_qdate', '')}  涨停池全景")
    if not zt:
        print("  当日无涨停数据（可能是非交易日，或当日尚未开盘）")
    else:
        lbc_count = {}
        for it in zt:
            lbc_count[it["连板数"]] = lbc_count.get(it["连板数"], 0) + 1
        lbc_stat = "  ".join(f"{k}板:{v}只" for k, v in sorted(lbc_count.items()))
        total_fund = sum(it["封单资金(亿)"] for it in zt)
        print(f"  涨停 {len(zt)} 只 | 炸板 {len(zb)} 只 | 跌停 {len(dt_pool)} 只")
        print(f"  连板结构: {lbc_stat}")
        print(f"  封单资金合计: {total_fund:.1f} 亿")
        hy = {}
        for it in zt:
            hy[it["行业板块"]] = hy.get(it["行业板块"], 0) + 1
        top_hy = sorted(hy.items(), key=lambda x: -x[1])[:5]
        print(f"  行业TOP5: " + "  ".join(f"{k}({v})" for k, v in top_hy))
        zt_sorted = sorted(zt, key=lambda x: (-x["连板数"], x["首次封板时间"]))
        for it in zt_sorted[:10]:
            star = "★" if it["连板数"] >= 3 else " "
            print(f"  {it['代码']} {it['名称']:<8} {it['连板数']:>2}板{star} "
                  f"首封{it['首次封板时间']} 炸{it['炸板次数']}次 "
                  f"封单{it['封单资金(亿)']}亿 {it['行业板块']} {it['几日几板']}")
        if len(zt_sorted) > 10:
            print(f"  ...（共 {len(zt_sorted)} 只，详见 JSON）")
    print()


def export_csv(data: dict, path: str):
    rows = []
    for cat in ("涨停", "炸板", "跌停"):
        for it in data.get(cat) or []:
            it2 = dict(it)
            it2["类别"] = cat
            rows.append(it2)
    if not rows:
        print("无数据可导出")
        return
    fields = ["类别"] + [k for k in rows[0].keys() if k != "类别"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"已导出 {len(rows)} 行 -> {path}")


def main():
    p = argparse.ArgumentParser(description="A股涨停板池采集（东财：涨停/炸板/跌停）")
    p.add_argument("date", nargs="?", default=None,
                   help="日期参考值（接口实际返回调用当日数据，归档以接口 qdate 为准）")
    p.add_argument("--out", default=None, help="输出目录 (默认 ../data/zt_pool)")
    p.add_argument("--csv", metavar="FILE", help="额外导出 CSV 文件路径")
    p.add_argument("--report", action="store_true", help="打印终端报表")
    a = p.parse_args()

    out_dir = a.out or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data", "zt_pool")
    out_dir = os.path.abspath(out_dir)

    print("📡 拉取东财涨停/炸板/跌停池 ...")
    data = get_pool_items()
    qdate = data.pop("_qdate") or dt.date.today().strftime("%Y%m%d")
    counts = {k: len(v) for k, v in data.items()}

    if not any(counts.values()):
        print("❌ 三个池均为空（非交易日或接口异常）")
        return

    # 传入日期与接口 qdate 不一致时提示（接口只返回调用当日数据）
    if a.date:
        want = str(a.date).strip().replace("-", "").replace("/", "")
        if want != qdate:
            print(f"  [WARN] 传入日期 {want}，但接口返回的是 {qdate} 的数据"
                  f"（东财该接口仅支持当日，已按 {qdate} 归档）", flush=True)

    output = {
        "meta": {
            "source": "东方财富涨停板池 push2ex.eastmoney.com",
            "date": qdate,
            "counts": counts,
            "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        **data,
    }
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"zt_pool_{qdate}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=1)
    print(f"✅ 涨停 {counts['涨停']} | 炸板 {counts['炸板']} | 跌停 {counts['跌停']}")
    print(f"✅ 已保存: {path}")
    if a.csv:
        export_csv(data, a.csv)
    if a.report:
        print_report({**data, "_qdate": qdate})


if __name__ == "__main__":
    main()
