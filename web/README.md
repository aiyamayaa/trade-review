# A股复盘看板（Vue 3 + Vite + Node）

基于 `review/data/concept/` 下两份 JSON 数据的可视化看板：

- `limit_up_down_data.json` —— 市场情绪数据（指数 / 资金 / 涨跌停 / 连板进阶），对应「市场情绪」页
- `sector_data.json` —— 板块分析数据（各行业涨停分布 / 炸板率 / 龙虎榜等），对应「板块分析」页

顶部导航在两个页面间切换，每页可切换交易日查看当日明细。

## 目录结构

```
web/
├── index.html            # SPA 入口
├── package.json
├── vite.config.js        # dev 代理 /api -> Node 后端
├── server/
│   └── server.js         # Node 原生 HTTP 后端（API + 静态托管）
└── src/
    ├── main.js
    ├── App.vue           # 顶部导航，切换两个视图
    ├── style.css
    ├── api.js            # 请求 /api/data、/api/sector
    ├── utils.js          # 金额/百分比格式化、周期阶段判断等
    ├── components/
    │   ├── StatCard.vue  # 统计卡片
    │   └── BarChart.vue  # 横向条形图（SVG）
    └── views/
        ├── EmotionView.vue  # 市场情绪
        └── SectorView.vue   # 板块分析
```

## 运行

```bash
cd web
npm install

# 开发模式（同时启动 Vite 与 Node 后端）
npm run dev
# 打开 http://localhost:5173  （/api 由 Vite 代理到 :8788）

# 生产构建 + 启动（Node 托管 dist）
npm run build
npm run start
# 打开 http://localhost:8788
```

## 配置

后端通过环境变量配置：

- `PORT`：服务端口，默认 `8788`
- `DATA_DIR`：数据目录，默认取 `../data`（即 `review/data`），读取其下 `concept/*.json`

示例（读取自定义目录）：

```bash
DATA_DIR=/path/to/data PORT=9000 npm run start
```

## 数据来源

数据由 `scripts/fetch_limit_data.py` 与 `scripts/fetch_sector_data.py` 采集（依赖 `akshare`、`pandas`）。
字段含义见 `docs/limit_up_down_data_schema.md` 与 `docs/sector_data_schema.md`。
