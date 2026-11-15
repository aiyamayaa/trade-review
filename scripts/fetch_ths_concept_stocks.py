"""
抓取同花顺概念板块成分股，补充到 data/meta/ths_concept_info.json
数据源: https://q.10jqka.com.cn/gn/detail/code/{code}/ (GBK 编码, 每页 10 只)
翻页:   /gn/detail/code/{code}/page/{n}/  (非 AJAX 路径, 无需反爬头)

用法:
  python3 scripts/fetch_ths_concept_stocks.py            # 只抓金属铅(第一阶段测试)
  python3 scripts/fetch_ths_concept_stocks.py --all      # 抓全部概念
  python3 scripts/fetch_ths_concept_stocks.py --code 308864  # 按编号抓单个
"""
import sys
import json
import time
import requests
from bs4 import BeautifulSoup

META_FILE = "/Users/fengjiaxin/code/ava/review/data/meta/ths_concept_info.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
# 列顺序: 0序号 1代码 2名称 3现价 4涨跌幅 5涨跌 6涨速 7换手 8量比
#         9振幅 10成交额 11流通股 12流通市值 13市盈率


def get_soup(url, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "lxml")
            print(f"  [warn] {url} -> HTTP {r.status_code}")
        except Exception as e:
            print(f"  [warn] {url} -> {e}")
        time.sleep(1.5)
    return None


def parse_rows(soup):
    """解析成分股表格行"""
    out = []
    for tr in soup.select("tbody tr"):
        tds = [td.text.strip() for td in tr.find_all("td")]
        if len(tds) < 14:  # "暂无成份股数据" 行 / 表头行
            continue
        out.append({
            "code": tds[1],          # 代码
            "name": tds[2],          # 名称
            "float_shares": tds[11],  # 流通股数
            "float_mv": tds[12],     # 流通市值
            "pe": tds[13],           # 市盈率
        })
    return out


def fetch_concept_stocks(code):
    """抓取单个概念的全部成分股(自动翻页)"""
    soup = get_soup(f"http://q.10jqka.com.cn/gn/detail/code/{code}/")
    if not soup:
        return None
    pi = soup.find("span", class_="page_info")
    total_pages = int(pi.text.split("/")[1]) if pi else 1
    stocks = parse_rows(soup)
    for p in range(2, total_pages + 1):
        time.sleep(0.6)
        soup = get_soup(f"http://q.10jqka.com.cn/gn/detail/code/{code}/page/{p}/")
        if not soup:
            print(f"  [warn] 第 {p} 页失败, 跳过")
            continue
        stocks += parse_rows(soup)
    return stocks


def update_json(targets):
    """targets: {name: stocks_list} 更新到 JSON"""
    with open(META_FILE, encoding="utf-8") as f:
        data = json.load(f)
    for c in data["concepts"]:
        if c["name"] in targets:
            c["stocks"] = targets[c["name"]]
            c["stocks_count"] = len(targets[c["name"]])
    # 原子写入
    tmp = META_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    import os
    os.replace(tmp, META_FILE)


def main():
    args = sys.argv[1:]
    with open(META_FILE, encoding="utf-8") as f:
        data = json.load(f)
    concepts = data["concepts"]

    if "--all" in args:
        todo = concepts
    elif "--code" in args:
        code = args[args.index("--code") + 1]
        todo = [c for c in concepts if c["code"] == code]
    else:
        todo = [c for c in concepts if c["name"] == "金属铅"]  # 第一阶段: 只抓金属铅

    print(f"待抓取概念数: {len(todo)}")
    targets = {}
    for i, c in enumerate(todo, 1):
        stocks = fetch_concept_stocks(c["code"])
        if stocks is None:
            print(f"[{i}/{len(todo)}] {c['name']}({c['code']}) 抓取失败!")
            continue
        targets[c["name"]] = stocks
        print(f"[{i}/{len(todo)}] {c['name']}({c['code']}): "
              f"{len(stocks)} 只 (预期 {c.get('company_count')})")
        # 每 10 个概念保存一次, 防中断丢失
        if len(targets) % 10 == 0 or i == len(todo):
            update_json(targets)
            targets = {}
        time.sleep(0.8)
    if targets:
        update_json(targets)
    print("完成!")


if __name__ == "__main__":
    main()
