"""
补全 同花顺行业板块全量表.json:
1. 14 个 >100 只的行业(页面只抓到前100只)用九方二级行业名单补充剩余
   - 13 个行业有九方同名行业; 建筑装饰 用 装修装饰Ⅱ+房屋建设Ⅱ 组合
   - 补充前验证页面可见集与九方名单重合度(>90% 才采用)
2. 补充股票的字段(流通股/流通市值/市盈率)取自腾讯行情
3. 全部 stocks 统一补充 url / info_url

用法: python3 scripts/enrich_ths_industry_stocks.py
"""
import json
import time
import requests

THS_FILE = "/Users/fengjiaxin/code/ava/review/data/meta/同花顺行业板块全量表.json"
JF_FILE = "/Users/fengjiaxin/code/ava/review/data/ticai/jiufang_boards_hy_20260823.json"

# 同花顺行业 -> 九方二级行业名列表(建筑装饰为5个二级行业组合, 其余同名)
JF_MAP_OVERRIDE = {
    "建筑装饰": ["工程咨询服务Ⅱ", "专业工程", "基础建设", "装修装饰Ⅱ", "房屋建设Ⅱ"],
}


def tencent_prefix(code):
    if code.startswith(("600", "601", "603", "605", "688", "689")):
        return "sh" + code
    if code.startswith(("000", "001", "002", "003", "300", "301")):
        return "sz" + code
    return "bj" + code


def fetch_tencent_quotes(codes):
    result = {}
    code_list = list(codes)
    batch = 55
    for i in range(0, len(code_list), batch):
        chunk = code_list[i:i + batch]
        qs = ",".join(tencent_prefix(c) for c in chunk)
        try:
            r = requests.get(f"http://qt.gtimg.cn/q={qs}", timeout=20)
            text = r.content.decode("gbk", errors="ignore")
        except Exception as e:
            print(f"  [warn] 行情批次失败: {e}", flush=True)
            time.sleep(1)
            continue
        for line in text.split(";"):
            if '="' not in line or "~" not in line:
                continue
            fields = line.split('="')[1].rstrip('"').split("~")
            if len(fields) < 73:
                continue
            try:
                fs = float(fields[72])
                mv = float(fields[44])
            except ValueError:
                continue
            pe = fields[52].strip() if len(fields) > 52 else ""
            result[fields[2]] = {
                "name": fields[1],
                "float_shares": f"{fs / 1e8:.2f}亿",
                "float_mv": f"{mv:.2f}亿",
                "pe": pe if pe else "--",
            }
        time.sleep(0.3)
    return result


def main():
    with open(THS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    concepts = data["concepts"]
    with open(JF_FILE, encoding="utf-8") as f:
        jf_boards = {b["name"]: b for b in json.load(f)["boards"]}

    # 1. 找出被截断的行业及其九方候选名单
    need_fill = {}
    for c in concepts:
        declared = c.get("company_count") or 0
        have = c.get("stocks_count") or 0
        if declared <= have:
            continue
        names = JF_MAP_OVERRIDE.get(c["name"], [c["name"], c["name"] + "Ⅱ"])
        cands = []
        for n in names:
            if n in jf_boards:
                cands.append(jf_boards[n])
        if not cands:
            print(f"[skip] {c['name']}: 九方无候选行业", flush=True)
            continue
        # 验证重合度: 页面可见集 vs 九方候选并集
        jf_codes = set()
        for b in cands:
            jf_codes |= {s["code"] for s in b.get("stocks", [])}
        page_codes = {s["code"] for s in c.get("stocks", [])}
        overlap = len(page_codes & jf_codes) / len(page_codes) if page_codes else 0
        if overlap < 0.9:
            print(f"[skip] {c['name']}: 重合度仅 {overlap:.0%}, 不采用九方补充", flush=True)
            continue
        extra_codes = jf_codes - page_codes
        need_fill[c["name"]] = extra_codes
        print(f"[fill] {c['name']}: 页面{have}/声明{declared}, 九方并集{len(jf_codes)}, "
              f"重合度{overlap:.0%}, 补充 {len(extra_codes)} 只", flush=True)

    # 2. 腾讯行情拉取全部补充股票
    all_extra = set()
    for v in need_fill.values():
        all_extra |= v
    print(f"\n需补充股票共 {len(all_extra)} 只, 拉取腾讯行情...", flush=True)
    quotes = fetch_tencent_quotes(all_extra) if all_extra else {}
    print(f"行情获取 {len(quotes)}/{len(all_extra)}", flush=True)

    # 3. 组装: 补充到 stocks 尾部 + 全部股票统一加 url/info_url
    jf_stock_info = {}
    for b in jf_boards.values():
        for s in b.get("stocks", []):
            jf_stock_info[s["code"]] = s

    for c in concepts:
        if c["name"] in need_fill:
            for code in sorted(need_fill[c["name"]]):
                q = quotes.get(code)
                s = jf_stock_info.get(code, {})
                if q:
                    c["stocks"].append({
                        "code": code,
                        "name": q["name"],
                        "float_shares": q["float_shares"],
                        "float_mv": q["float_mv"],
                        "pe": q["pe"],
                    })
                else:
                    c["stocks"].append({
                        "code": code,
                        "name": s.get("name", code),
                        "float_shares": None,
                        "float_mv": None,
                        "pe": None,
                    })
            c["stocks_count"] = len(c["stocks"])
        # 统一 url / info_url
        for s in c.get("stocks", []):
            s["url"] = f"https://stockpage.10jqka.com.cn/{s['code']}"
            s["info_url"] = f"https://basic.10jqka.com.cn/{s['code']}/"

    # 4. meta + 写入
    total = sum(c.get("stocks_count", 0) for c in concepts)
    data["meta"]["stocks_source"] = (
        "成分股: 同花顺行业页 q.10jqka.com.cn/thshy (页面直抓, 游客限前5页100只); "
        ">100只的行业用九方智投二级行业名单补全(重合度验证>90%), "
        "补充股票的流通股/流通市值/市盈率取自腾讯行情"
    )
    data["meta"]["total_stocks"] = total
    data["meta"]["stocks_generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    tmp = THS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    import os
    os.replace(tmp, THS_FILE)
    print(f"\n完成! 90 个行业, 成分股共 {total} 条, 已写入 {THS_FILE}", flush=True)


if __name__ == "__main__":
    main()
