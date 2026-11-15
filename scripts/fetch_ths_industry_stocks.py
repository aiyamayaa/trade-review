"""
抓取同花顺行业板块成分股（数据源: http://q.10jqka.com.cn/thshy/detail/code/{code}/）
页面每页 20 行, 游客最多 5 页(100只)。>100 只的行业此脚本抓前 100 只,
后续由 enrich 脚本用九方数据补全。

用法: python3 scripts/fetch_ths_industry_stocks.py
"""
import json
import time
import requests
from bs4 import BeautifulSoup

THS_FILE = "/Users/fengjiaxin/code/ava/review/data/meta/同花顺行业板块全量表.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def get_soup(url, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "lxml")
            print(f"  [warn] {url} -> HTTP {r.status_code}", flush=True)
        except Exception as e:
            print(f"  [warn] {url} -> {e}", flush=True)
        time.sleep(1.5)
    return None


def parse_rows(soup):
    """行业页 14 列: 0序号 1代码 2名称 ... 11流通股 12流通市值 13市盈率"""
    out = []
    for tr in soup.select("tbody tr"):
        tds = [td.text.strip() for td in tr.find_all("td")]
        if len(tds) < 14:
            continue
        out.append({
            "code": tds[1],
            "name": tds[2],
            "float_shares": tds[11],
            "float_mv": tds[12],
            "pe": tds[13],
        })
    return out


def fetch_industry(code):
    """抓单个行业(最多5页, 每页20行)"""
    soup = get_soup(f"http://q.10jqka.com.cn/thshy/detail/code/{code}/")
    if not soup:
        return None, 0
    pi = soup.find("span", class_="page_info")
    total_pages = int(pi.text.split("/")[1]) if pi else 1
    stocks = parse_rows(soup)
    for p in range(2, min(total_pages, 5) + 1):
        time.sleep(0.4)
        soup = get_soup(f"http://q.10jqka.com.cn/thshy/detail/code/{code}/page/{p}/")
        if not soup:
            continue
        stocks += parse_rows(soup)
    return stocks, total_pages


def main():
    with open(THS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    concepts = data["concepts"]
    print(f"共 {len(concepts)} 个行业", flush=True)

    for i, c in enumerate(concepts, 1):
        stocks, total_pages = fetch_industry(c["code"])
        if stocks is None:
            print(f"[{i}/{len(concepts)}] {c['name']} 抓取失败!", flush=True)
            continue
        c["stocks"] = stocks
        c["stocks_count"] = len(stocks)
        c["_page_info"] = total_pages
        truncated = (c.get("company_count") or 0) > len(stocks)
        mark = " [截断]" if truncated else ""
        print(f"[{i}/{len(concepts)}] {c['name']}: {len(stocks)}/{c.get('company_count')}"
              f" (共{total_pages}页){mark}", flush=True)
        # 每 15 个行业保存一次
        if i % 15 == 0:
            _save(data)

    _save(data)
    done = sum(1 for c in concepts if c.get("stocks"))
    trunc = sum(1 for c in concepts if (c.get("company_count") or 0) > (c.get("stocks_count") or 0))
    print(f"完成! {done}/{len(concepts)} 个行业, 其中 {trunc} 个被截断(>100只)", flush=True)


def _save(data):
    for c in data["concepts"]:
        c.pop("_page_info", None)
    tmp = THS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    import os
    os.replace(tmp, THS_FILE)


if __name__ == "__main__":
    main()
