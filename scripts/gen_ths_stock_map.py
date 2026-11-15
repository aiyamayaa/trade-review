"""
根据 同花顺行业板块全量表.json + ths_concept_info.json 生成个股维度的聚合信息表。
输出: data/meta/ths_stock_info.json
结构: { meta, stocks: { code: { 基础字段, industries: [...], concepts: [...] } } }
  - 基础字段(code/name/float_shares/float_mv/pe)优先取行业全量表(最新抓取),
    仅在概念表出现的股票取概念表字段, url/info_url 由 code 拼接
  - industries: 个股关联的行业板块概要(同花顺行业唯一归属, 理论上 1 个)
  - concepts: 个股关联的概念板块概要(按概念表顺序=资金流热度排序)
用法: python3 scripts/gen_ths_stock_map.py
"""
import json
import time

IND_FILE = "/Users/fengjiaxin/code/ava/review/data/meta/同花顺行业板块全量表.json"
CON_FILE = "/Users/fengjiaxin/code/ava/review/data/meta/ths_concept_info.json"
OUT = "/Users/fengjiaxin/code/ava/review/data/meta/ths_stock_info.json"


def new_stock(s):
    """初始化个股条目（基础字段 + url/info_url 拼接）"""
    code = s["code"]
    return {
        "code": code,
        "name": s.get("name"),
        "float_shares": s.get("float_shares"),
        "float_mv": s.get("float_mv"),
        "pe": s.get("pe"),
        "url": f"https://stockpage.10jqka.com.cn/{code}",
        "info_url": f"https://basic.10jqka.com.cn/{code}/",
        "industries": [],
        "concepts": [],
    }


def main():
    stocks = {}

    # ===== 1. 行业全量表（基础字段以此为准, 最近抓取） =====
    with open(IND_FILE, encoding="utf-8") as f:
        ind_data = json.load(f)
    for ind in ind_data.get("concepts", []):
        ind_info = {
            "name": ind["name"],
            "code": ind["code"],
            "company_count": ind.get("company_count"),
            "url": ind.get("url"),
        }
        for s in ind.get("stocks", []):
            code = s["code"]
            stocks.setdefault(code, new_stock(s))
            stocks[code]["industries"].append(ind_info)
    from_industry = len(stocks)
    print(f"行业表: {len(ind_data['concepts'])} 个行业, 覆盖个股 {from_industry} 只")

    # ===== 2. 概念表（补充概念关联 + 概念独有的个股） =====
    with open(CON_FILE, encoding="utf-8") as f:
        con_data = json.load(f)
    for con in con_data.get("concepts", []):
        con_info = {
            "name": con["name"],
            "code": con["code"],
            "company_count": con.get("company_count"),
            "url": con.get("url"),
        }
        for s in con.get("stocks", []):
            code = s["code"]
            stocks.setdefault(code, new_stock(s))
            stocks[code]["concepts"].append(con_info)
    print(f"概念表: {len(con_data['concepts'])} 个概念, 合并后总个股 {len(stocks)} 只"
          f" (概念表补充 {len(stocks) - from_industry} 只)")

    # ===== 3. 统计 + 输出 =====
    no_industry = sum(1 for v in stocks.values() if not v["industries"])
    no_concept = sum(1 for v in stocks.values() if not v["concepts"])
    multi_ind = sum(1 for v in stocks.values() if len(v["industries"]) > 1)
    data = {
        "meta": {
            "data_source": (
                "同花顺行业板块全量表.json(行业归属+基础字段) + "
                "ths_concept_info.json(概念归属); url/info_url 由 code 拼接"
            ),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "stock_count": len(stocks),
            "fields": {
                "code": "个股代码(key)",
                "name": "名称", "float_shares": "流通股数",
                "float_mv": "流通市值", "pe": "市盈率",
                "url": "同花顺个股页", "info_url": "同花顺F10基础信息页",
                "industries": "关联行业板块列表(同花顺行业唯一归属, 通常 1 个)",
                "concepts": "关联概念板块列表(按概念表热度排序)",
            },
            "stats": {
                "no_industry": no_industry,
                "no_concept": no_concept,
                "multi_industry": multi_ind,
            },
        },
        "stocks": stocks,
    }
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    import os
    os.replace(tmp, OUT)
    print(f"已写入 {OUT}")
    print(f"统计: 无行业归属 {no_industry} 只, 无概念归属 {no_concept} 只, 多行业 {multi_ind} 只")


if __name__ == "__main__":
    main()
