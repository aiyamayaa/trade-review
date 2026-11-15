# A股涨跌停/连板情绪数据采集 & 展示
#
# 用法:
#   1. 采集情绪数据（涨停/跌停/炸板/连板）:
#      make fetch-limit              # 默认最近15个交易日，输出到 data/concept/
#      make fetch-limit N=20         # 取最近20个交易日
#      make fetch-limit OUT=./output # 自定义输出目录
#      make fetch-limit-info         # 额外用 Wind+iFinD 采集最新交易日涨停股基础信息（需插件环境）
#
#   2. 采集板块数据（申万行业，输出 concept/sector_data.json）:
#      make fetch-sector             # 默认最近约14天（自动跳过非交易日），输出到 data/concept/
#      make fetch-sector START=20260801 END=20260812   # 自定义日期范围
#      make fetch-sector OUT=./output # 自定义输出目录
#
#   3. 前端看板（Vue 3 + Vite + Node 原生后端，读取 data/concept/ 下两份 JSON）:
#      make web-install   # 安装前端依赖（首次必跑）
#      make web-build     # 生产构建（输出 web/dist）
#      make web           # 构建并启动生产服务，默认端口 8788，数据目录 ./data
#      make web PORT=9000 DIR=/path/to/data   # 自定义端口与数据目录
#      make web-dev       # 开发模式（Vite + Node 后端热更新），打开 http://localhost:5173
#      浏览器打开 http://127.0.0.1:<PORT> 后，顶部导航切换「市场情绪」与「板块分析」两个页面
#
#   4. 九方智投题材数据采集（输出 data/ticai/）:
#      make fetch-ticai                 # 采集题材板块列表（默认概念 GN，按涨跌幅排序）
#      make fetch-ticai TYPE=hy         # 行业板块 HY；TYPE=dq 地区板块
#      make fetch-ticai SORT=fundflow   # 按主力净流入排序（默认 pxChangeRate 涨跌幅）
#      make fetch-ticai-full            # 采集板块列表 + 每个板块的全部成分股（个股明细）
#      make fetch-ticai-full LIMIT=10   # 仅采集前 10 个板块的成分股（快速测试）
#      make fetch-ticai-detail CODE=GN886033   # 采集指定题材下的个股明细（连板数排序）
#      make fetch-ticai-detail CODE=GN886033 DETAIL_SORT=pxChangeRate   # 明细按涨跌幅排序
#
#   注：数据目录下需含 concept/limit_up_down_data.json 与 concept/sector_data.json
#
#   5. AI 对话后端（Python FastAPI，供 web「AI 对话」页调用）:
#      make chat-install   # 安装 Python 依赖（首次必跑，需 pip3）
#      make chat-server    # 启动聊天后端，默认端口 8799
#      make chat-server CHAT_PORT=9001   # 自定义端口（需与 web 的 CHAT_API_BASE 一致）
#      需先完成 CodeBuddy 登录或设置 CODEBUDDY_API_KEY，详见 docs/ai_agent_sdk_guide.md
#      运行时需与 `make web` 同时启动：web 会把 /api/chat/* 反向代理到本服务
#
#   6. 葛南维均线评分（对最新交易日涨停股批量打分，输出 data/stocks/granville/）:
#      make fetch-granville              # 最新交易日涨停股全量打分
#      make fetch-granville TOP=20       # 仅封单金额前 20 只
#      make fetch-granville CODES=000017,301218   # 指定代码
#      make fetch-granville ALL=1        # 补历史：对数据中每个交易日依次打分
#
#   7. 单股分时/分笔成交（指定代码+日期，输出 data/stocks_daily/）:
#      make fetch-tick CODE=605179 DATE=20260901          # 当日→分笔+分钟线，历史→分钟线
#      make fetch-tick CODE=sz301218 DATE=20260828 MODE=minute   # 强制分钟线
#
#   8. 按题材 JSON 批量下载分时数据（JSON 格式: { "题材名": { "代码": "名称" } }）:
#      make fetch-ticks-json                        # 用 makefile 里定义的 FILE/DATE 默认值
#      make fetch-ticks-json DATE=20260903          # 命令行覆盖日期
#      make fetch-ticks-json FILE=x.json DATE=20260903 MODE=minute FORCE=1
#      存储: data/stocks_daily/{日期}/{题材}/，已存在自动跳过（缺哪种补哪种）

#   9. 开盘啦（需在项目根 .env 填写 KPL_USER_ID / KPL_TOKEN，模板见 .env.example）:
#      make fetch-yidong                     # 竞价异动：实时（交易日 9:15-9:25 有数据）
#      make fetch-yidong DATE=2026-11-13     # 竞价异动：指定日期（历史接口，非空自动缓存到 data/yidong/）
#      make fetch-lhb                        # 实时龙虎榜：盘中资金排行快照（落盘 data/lhb_realtime/）
#      make fetch-lhb PAGES=3                # 取前 3 页（每页 60 条）
#
#  10. 东方财富公告（无需 Token；按月存 CSV：data/gonggao/YYYY-MM.csv，按 art_code 去重）:
#      make fetch-gonggao                    # 抓今天
#      make fetch-gonggao GG_DAYS=7          # 最近 7 天
#      make fetch-gonggao GG_FROM=2026-11-01 GG_TO=2026-11-12   # 指定日期范围（逐日，已抓过的历史日自动跳过）

# 加载项目根 .env（KEY=VALUE，可选；shell 中已 export 的值优先），传给所有子命令
ifneq (,$(wildcard .env))
include .env
export $(shell sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1/p' .env)
endif

PYTHON   := python3
PIP      := pip3
PORT     ?= 8788
DIR      ?= $(shell pwd)/data
WEB_DIR  := web
CHAT_DIR := ai_agent/python
CHAT_PORT ?= 8799

# 情绪数据采集参数（N = 最近 N 个交易日）
N   ?= 10
OUT ?= data/concept

# 板块数据采集参数（START/END 为 YYYYMMDD）
TODAY   := $(shell date +%Y%m%d)
START   ?= 20260923
END     ?= $(TODAY)
SEC_OUT ?= data/concept

# 九方智投题材数据采集参数
# TYPE: gn=概念 hy=行业 dq=地区
# SORT: boards 排序字段（默认涨跌幅）
# DETAIL_SORT: detail 排序字段（默认连板数）
# LIMIT: 仅采集前 N 个板块（配合 fetch-ticai-full）
TICAI_OUT  ?= data/ticai
TYPE       ?= gn
SORT       ?= pxChangeRate
DETAIL_SORT ?= countBoard
CODE       ?= GN886033
LIMIT      ?=

# 葛南维均线评分参数（scripts/fetch_granville_data.py）
GRANVILLE_OUT ?= data/stocks/granville
TOP           ?=
CODES         ?=
ALL           ?=

# 单股分时/分笔参数（scripts/fetch_stock_tick.py）
TICK_OUT ?= data/stocks_daily
MODE      ?=   # ticks|minute，默认 auto（当日→分笔，历史→分钟线）

# 全市场单日行情参数（scripts/fetch_market_data.py，输出 data/market/）
MARKET_OUT   ?= data/market
MARKET_DATE  ?= $(TODAY)
MARKET_DAYS  ?= 30

# 涨停板池参数（scripts/fetch_zt_pool.py，东财涨停/炸板/跌停，输出 data/zt_pool/）
# 注意: 东财接口仅返回调用当日数据，需每天执行积累（DATE 仅作参考，归档以接口实际日期为准）
ZT_OUT  ?= data/zt_pool
ZT_DATE ?= $(TODAY)

# 开盘啦参数（凭证在 .env）：DATE_YD=YYYY-MM-DD 历史竞价异动；PAGES 实时龙虎榜页数；LHB_START/LHB_END 区间(HHMM)
DATE_YD   ?= $(DATE)
PAGES     ?= 1
LHB_START ?=
LHB_END   ?=

# 东方财富公告参数：GG_DAYS 最近N天；GG_FROM/GG_TO 日期范围；GG_FORCE=1 强制重抓
GG_DAYS  ?=
GG_FROM  ?=
GG_TO    ?=
GG_FORCE ?=

.PHONY: today all_for_day fetch-limit fetch-limit-info fetch-sector fetch-ticai fetch-ticai-full fetch-ticai-detail fetch-granville fetch-tick fetch-ticks-json fetch-market fetch-market-history fetch-zt-pool fetch-yidong fetch-lhb fetch-gonggao web web-dev web-build web-install chat-install chat-server

# fetch-limit:
# 	$(PYTHON) scripts/fetch_limit_data.py $(N) $(OUT)

all: fetch-limit-info fetch-sector fetch-ticai-full 	

# 仅采集当天数据（make all 的当日精简版）：
#   情绪 N=1（只最新交易日）、板块 START=END=今天、题材当日快照
today:
	$(MAKE) fetch-limit-info N=1
	$(MAKE) fetch-sector START=$(TODAY) END=$(TODAY)
	$(MAKE) fetch-ticai-full

# 按日期列表采集指定几天的数据（参考 make today）：
#   make all_for_day DATES=2026-10-07,2026-10-08,2026-10-09
#   日期支持 2026-10-07 或 20261007 写法，英文逗号/中文逗号/顿号/空格分隔均可
#   每个日期拉取：板块+龙虎榜（精确到日）、全市场行情（供题材弹框展示个股）
#   情绪数据：按最早日期至今的交易日数一次性拉取
#   题材板块：九方接口仅当日快照，历史无法回溯（不在本目标范围）
DATES ?= 2026-11-02、2026-11-03、2026-11-04、2026-11-05、2026-11-06、2026-11-09

all_for_day:
	@test -n "$(DATES)" || (echo "用法: make all_for_day DATES=2026-10-07,2026-10-08,2026-10-09" && exit 1)
	@earliest=99999999; \
	for d in $$(echo $(DATES) | sed 's/[，、,]/ /g'); do \
		d=$$(echo $$d | tr -dc '0-9'); \
		test -n "$$d" || continue; \
		echo "==> 板块+龙虎榜 $$d"; \
		$(MAKE) --no-print-directory fetch-sector START=$$d END=$$d || exit 1; \
		echo "==> 全市场行情 $$d（约2-3分钟）"; \
		$(MAKE) --no-print-directory fetch-market MARKET_DATE=$$d || exit 1; \
		if [ "$$d" -lt "$$earliest" ]; then earliest=$$d; fi; \
	done; \
	echo "==> 情绪数据（$$earliest ~ 今天）"; \
	ndays=$$(python3 -c "import akshare as ak, pandas as pd; df=ak.tool_trade_date_hist_sina(); df['trade_date']=pd.to_datetime(df['trade_date']); t=pd.Timestamp.now().normalize(); e=pd.Timestamp(str($$earliest)); print(len(df[(df['trade_date']>=e)&(df['trade_date']<=t)]))"); \
	$(MAKE) --no-print-directory fetch-limit-info N=$$ndays

fetch-limit-info:
	$(PYTHON) scripts/fetch_limit_data.py $(N) $(OUT) --with-stock-info

fetch-sector:
	$(PYTHON) scripts/fetch_sector_data.py $(START) $(END) $(SEC_OUT)

fetch-ticai:
	$(PYTHON) scripts/fetch_jiufang_data.py boards --type $(TYPE) --sort $(SORT) --output-dir $(TICAI_OUT)

fetch-ticai-full:
	$(PYTHON) scripts/fetch_jiufang_data.py boards --type $(TYPE) --sort $(SORT) --with-stocks $(if $(LIMIT),--limit $(LIMIT)) --output-dir $(TICAI_OUT)

fetch-ticai-detail:
	$(PYTHON) scripts/fetch_jiufang_data.py detail --code $(CODE) --type $(TYPE) --sort $(DETAIL_SORT) --output-dir $(TICAI_OUT)

# 葛南维均线评分：拉取涨停股日线 → 计算MA5/10/20/30/60 → 八大法则打分
fetch-granville:
	$(PYTHON) scripts/fetch_granville_data.py --output-dir $(GRANVILLE_OUT) \
		$(if $(TOP),--top $(TOP)) \
		$(if $(CODES),--codes $(CODES)) \
		$(if $(ALL),--all-dates)

# 全市场单日行情：make fetch-market DATE=20260910（单日）
# 全市场最近N个交易日行情：make fetch-market-history DAYS=30
fetch-market:
	$(PYTHON) scripts/fetch_market_data.py $(MARKET_DATE) $(MARKET_OUT)

fetch-market-history:
	$(PYTHON) scripts/fetch_market_history.py --days $(MARKET_DAYS) --output-dir $(MARKET_OUT)

# 涨停板池（东财）：涨停 + 炸板 + 跌停 三池，按天归档 data/zt_pool/zt_pool_YYYYMMDD.json
# 接口仅返回调用当日数据，建议加入每日例程（如 make today）积累历史
fetch-zt-pool:
	$(PYTHON) scripts/fetch_zt_pool.py $(ZT_DATE) --out $(ZT_OUT)

# 开盘啦竞价异动：凭证读项目根 .env；DATE 为空=实时，非空=历史（YYYY-MM-DD，非空结果自动缓存）
fetch-yidong:
	$(PYTHON) scripts/fetch_yidong.py $(DATE_YD)

# 开盘啦实时龙虎榜（盘中资金排行快照，落盘 data/lhb_realtime/{日期}/{HHMM}.json）
fetch-lhb:
	$(PYTHON) scripts/fetch_lhb_realtime.py --pages $(PAGES) $(if $(LHB_START),--start $(LHB_START) --end $(LHB_END))

# 东方财富公告：按月 CSV 存储 data/gonggao/（无需凭证）
fetch-gonggao:
	$(PYTHON) scripts/fetch_gonggao.py $(if $(GG_DAYS),--days $(GG_DAYS),$(GG_FROM) $(GG_TO)) $(if $(GG_FORCE),--force)

# 单股分时/分笔成交：make fetch-tick CODE=605179 DATE=20260901 [MODE=minute]
fetch-tick:
	@test -n "$(CODE)" || (echo "用法: make fetch-tick CODE=605179 DATE=20260901 [MODE=ticks|minute]" && exit 1)
	@test -n "$(DATE)" || (echo "缺少 DATE，如 DATE=20260901" && exit 1)
	$(PYTHON) scripts/fetch_stock_tick.py $(CODE) $(DATE) --out $(TICK_OUT) \
		$(if $(MODE),--mode $(MODE))


# 按题材 JSON 批量下载参数（scripts/fetch_ticks_json.py）
# 每日更新下面两行后直接 make fetch-ticks-json（也可命令行覆盖：make fetch-ticks-json DATE=20260903）
FILE  ?= data/stocks_daily/meta/20260907.json   # 题材 JSON：{ "题材名": { "代码": "名称" } }
DATE  ?= 20260907                                # 下载日期 YYYYMMDD
FORCE ?=   # 1=已存在也重下

# 按题材 JSON 批量下载：make fetch-ticks-json FILE=meta/xxx.json DATE=20260902 [MODE=minute] [FORCE=1]
fetch-ticks-json:
	@test -n "$(FILE)" || (echo "用法: make fetch-ticks-json FILE=data/stocks_daily/meta/20260902.json DATE=20260901" && exit 1)
	@test -n "$(DATE)" || (echo "缺少 DATE，如 DATE=20260902" && exit 1)
	$(PYTHON) scripts/fetch_ticks_json.py $(FILE) $(DATE) --out $(TICK_OUT) \
		$(if $(MODE),--mode $(MODE)) \
		$(if $(FORCE),--force)

web-install:
	cd $(WEB_DIR) && npm install

web-build:
	cd $(WEB_DIR) && npm run build

web-dev:
	cd $(WEB_DIR) && npm run dev

web: web-build
	@echo "==> 关闭占用端口 $(PORT) 的进程（如有）..."
	@PIDS=$$(lsof -ti :$(PORT) 2>/dev/null); if [ -n "$$PIDS" ]; then kill -9 $$PIDS 2>/dev/null; sleep 1; fi
	cd $(WEB_DIR) && DATA_DIR=$(DIR) PORT=$(PORT) node server/server.js

chat-install:
	cd $(CHAT_DIR) && $(PIP) install -r requirements.txt

chat-server:
	@echo "==> 关闭占用端口 $(CHAT_PORT) 的进程（如有）..."
	@PIDS=$$(lsof -ti :$(CHAT_PORT) 2>/dev/null); if [ -n "$$PIDS" ]; then kill -9 $$PIDS 2>/dev/null; sleep 1; fi
	cd $(CHAT_DIR) && $(PYTHON) -m uvicorn chat_server:app --host 0.0.0.0 --port $(CHAT_PORT)
