"""
补全 ths_concept_info.json 中所有概念的成分股（突破同花顺游客只能看前5页/50只的限制）

数据源组合:
1. 成分股名单: 九方智投 data/ticai/jiufang_boards_gn_full.json (395概念, 成分股完整)
2. 个股字段(流通股/流通市值/市盈率): 腾讯批量行情 qt.gtimg.cn (每批60只, 一次拿全市场)

用法: python3 scripts/enrich_ths_concept_stocks.py
"""
import json
import time
import requests

THS_FILE = "/Users/fengjiaxin/code/ava/review/data/meta/ths_concept_info.json"
JF_FILE = "/Users/fengjiaxin/code/ava/review/data/ticai/jiufang_boards_gn_full.json"


def tencent_prefix(code):
    """股票代码 -> 腾讯接口市场前缀"""
    if code.startswith(("600", "601", "603", "605", "688", "689")):
        return "sh" + code
    if code.startswith(("000", "001", "002", "003", "300", "301")):
        return "sz" + code
    return "bj" + code  # 北交所


def fetch_tencent_quotes(codes):
    """腾讯批量行情: code -> {name, price, float_shares, float_mv, pe}"""
    result = {}
    batch = 55
    code_list = list(codes)
    total_batches = (len(code_list) + batch - 1) // batch
    for i in range(0, len(code_list), batch):
        chunk = code_list[i:i + batch]
        qs = ",".join(tencent_prefix(c) for c in chunk)
        try:
            r = requests.get(f"http://qt.gtimg.cn/q={qs}", timeout=20)
            text = r.content.decode("gbk", errors="ignore")
        except Exception as e:
            print(f"  [warn] 批次 {i//batch+1}/{total_batches} 失败: {e}")
            time.sleep(1)
            continue
        for line in text.split(";"):
            if '="' not in line or "~" not in line:
                continue
            fields = line.split('="')[1].rstrip('"').split("~")
            if len(fields) < 73:
                continue
            code = fields[2]
            try:
                float_shares = float(fields[72])   # 流通股本(股)
                float_mv = float(fields[44])       # 流通市值(亿)
            except (ValueError, IndexError):
                continue
            pe = fields[52].strip() if len(fields) > 52 else ""  # 市盈率(动)
            result[code] = {
                "name": fields[1],
                "price": float(fields[3]) if fields[3] else 0,
                "float_shares_raw": float_shares,
                "float_mv": float_mv,
                "pe": pe if pe else "--",
            }
        if (i // batch + 1) % 20 == 0:
            print(f"  行情批次 {i//batch+1}/{total_batches}, 已获取 {len(result)} 只")
        time.sleep(0.3)
    return result


def fmt_yi_shares(n):
    """股数 -> 亿股字符串"""
    return f"{n / 1e8:.2f}亿"


def main():
    # 1. 同花顺概念框架
    with open(THS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    concepts = data["concepts"]

    # 2. 九方成分股名单（名称对齐: 直接匹配 + 去"同花顺"前缀匹配）
    with open(JF_FILE, encoding="utf-8") as f:
        jf_boards = {b["name"]: b for b in json.load(f)["boards"]}
    jf_stripped = {name.replace("同花顺", ""): name for name in jf_boards}

    def find_jf(name):
        if name in jf_boards:
            return jf_boards[name]
        stripped = name.replace("同花顺", "")
        if stripped in jf_stripped:
            return jf_boards[jf_stripped[stripped]]
        return None

    # 3. 收集全部成分股代码
    all_codes = set()
    matched = 0
    for c in concepts:
        b = find_jf(c["name"])
        if b:
            matched += 1
            c["_jf_stocks"] = b.get("stocks", [])
            for s in c["_jf_stocks"]:
                all_codes.add(s["code"])
    print(f"概念匹配: {matched}/{len(concepts)}, 涉及个股 {len(all_codes)} 只")

    # 4. 腾讯批量行情
    print("拉取腾讯行情...")
    quotes = fetch_tencent_quotes(all_codes)
    print(f"行情获取成功: {len(quotes)}/{len(all_codes)}")

    # 5. 组装
    total_stocks = 0
    for c in concepts:
        jf = c.pop("_jf_stocks", None)
        if jf is None:
            # 九方没有的概念: 保留之前同花顺抓的 stocks(如果有)
            c["stocks_count"] = len(c.get("stocks", []))
            total_stocks += c["stocks_count"]
            continue
        stocks = []
        for s in jf:
            q = quotes.get(s["code"])
            if q:
                stocks.append({
                    "code": s["code"],
                    "name": s["name"],
                    "float_shares": fmt_yi_shares(q["float_shares_raw"]),
                    "float_mv": f"{q['float_mv']:.2f}亿",
                    "pe": q["pe"],
                })
            else:
                stocks.append({
                    "code": s["code"],
                    "name": s["name"],
                    "float_shares": None,
                    "float_mv": None,
                    "pe": None,
                })
        c["stocks"] = stocks
        c["stocks_count"] = len(stocks)
        total_stocks += len(stocks)

    # 6. 更新 meta 并写入
    data["meta"]["stocks_source"] = (
        "成分股名单: 九方智投(完整) | 个股字段(流通股/流通市值/市盈率): 腾讯行情 qt.gtimg.cn | "
        "同花顺页面仅展示前5页50只游客数据, 已用完整数据源覆盖"
    )
    data["meta"]["total_stocks"] = total_stocks
    data["meta"]["stocks_generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    tmp = THS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    import os
    os.replace(tmp, THS_FILE)
    print(f"完成! 概念 {len(concepts)} 个, 成分股共 {total_stocks} 条, 已写入 {THS_FILE}")


if __name__ == "__main__":
    main()
