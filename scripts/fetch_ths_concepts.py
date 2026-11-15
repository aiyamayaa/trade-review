"""
抓取同花顺概念板块（数据源：https://data.10jqka.com.cn/funds/gnzjl/）
复用 akshare 内置 ths.js 生成 hexin-v 反爬 Cookie。
输出: /Users/fengjiaxin/code/ava/review/data/meta/ths_concept_info.json
"""
import re
import json
import time
import datetime
import requests
import py_mini_racer
from bs4 import BeautifulSoup
from akshare.stock_feature.stock_fund_flow import _get_file_content_ths

OUT = "/Users/fengjiaxin/code/ava/review/data/meta/ths_concept_info.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/90.0.4430.85 Safari/537.36")


def make_headers():
    """每次请求重新生成 hexin-v Cookie"""
    js = py_mini_racer.MiniRacer()
    js.eval(_get_file_content_ths("ths.js"))
    v = js.call("v")
    return {
        "Accept": "text/html, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "hexin-v": v,
        "Referer": "http://data.10jqka.com.cn/funds/gnzjl/",
        "User-Agent": UA,
        "X-Requested-With": "XMLHttpRequest",
    }


def fetch(url, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, headers=make_headers(), timeout=20)
            if r.status_code == 200 and len(r.text) > 500:
                return r.text
            print(f"  [warn] {url} -> status={r.status_code} len={len(r.text)}")
        except Exception as e:
            print(f"  [warn] {url} -> {e}")
        time.sleep(1.5)
    return None


def parse_rows(html):
    """解析表格行 -> [{name, code, company_count}]"""
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for tr in soup.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 8:
            continue
        a = tds[1].find("a")
        if not a:
            continue
        m = re.search(r"/code/(\d+)/", a.get("href", ""))
        if not m:
            continue
        name = a.get_text(strip=True)
        code = m.group(1)
        try:
            cnt = int(tds[7].get_text(strip=True))
        except ValueError:
            cnt = None
        rows.append({
            "name": name,
            "code": code,
            "company_count": cnt,
            "url": f"https://q.10jqka.com.cn/gn/detail/code/{code}/",
        })
    return rows


def main():
    # ===== 1. 抓用户给的资金流页面（全部页） =====
    base = ("http://data.10jqka.com.cn/funds/gnzjl/field/tradezdf/"
            "order/desc/page/{}/ajax/1/free/1/")
    first = fetch(base.format(1))
    if not first:
        raise SystemExit("首页抓取失败，退出")
    soup = BeautifulSoup(first, "lxml")
    page_info = soup.find("span", class_="page_info")
    total_pages = int(page_info.text.split("/")[1])
    print(f"总页数: {total_pages}")

    concepts = {}
    for row in parse_rows(first):
        concepts[row["name"]] = row
    print(f"第 1 页: 累计 {len(concepts)}")

    for p in range(2, total_pages + 1):
        html = fetch(base.format(p))
        if not html:
            print(f"第 {p} 页抓取失败，跳过")
            continue
        for row in parse_rows(html):
            concepts.setdefault(row["name"], row)
        print(f"第 {p} 页: 累计 {len(concepts)}")
        time.sleep(0.8)

    fund_flow_count = len(concepts)
    print(f"资金流页面板块总数: {fund_flow_count}")

    # ===== 2. 补充概念列表页(按名称链接)里多出的板块 =====
    try:
        import akshare as ak
        name_df = ak.stock_board_concept_name_ths()
        extra = 0
        for _, r in name_df.iterrows():
            if r["name"] not in concepts:
                concepts[r["name"]] = {
                    "name": r["name"],
                    "code": str(r["code"]),
                    "company_count": None,
                    "url": f"https://q.10jqka.com.cn/gn/detail/code/{r['code']}/",
                }
                extra += 1
        print(f"从概念列表页补充: {extra} 个（无公司家数字段）")
    except Exception as e:
        print(f"概念列表页补充失败（不影响主数据）: {e}")

    # ===== 3. 写 JSON =====
    data = {
        "meta": {
            "data_source": "同花顺-数据中心-资金流向-概念资金流 "
                           "https://data.10jqka.com.cn/funds/gnzjl/",
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_count": len(concepts),
            "fund_flow_count": fund_flow_count,
            "fields": {
                "name": "概念板块名称",
                "code": "同花顺板块编号（URL 后缀）",
                "company_count": "公司家数（仅资金流页面覆盖的板块有值）",
                "url": "板块详情页 https://q.10jqka.com.cn/gn/detail/code/{code}/",
            },
        },
        "concepts": list(concepts.values()),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已写入 {OUT}，共 {len(concepts)} 个概念板块")


if __name__ == "__main__":
    main()
