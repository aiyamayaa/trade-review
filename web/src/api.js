// 数据请求封装

// ===== 通用表格导出 PDF（走 Python 后端 Chrome 打印）=====

/**
 * 把表格数据导出为 PDF 并触发浏览器下载。
 * title: PDF 标题；columns: 表头；rows: 二维数组；meta: 标题下说明行（可选）
 */
export async function exportTablePdf(title, columns, rows, meta = '') {
  const r = await fetch('/api/analysis/export-pdf', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, columns, rows, meta: meta || null }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `PDF 生成失败 (${r.status})`);
  }
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${title}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * 文档模式导出 PDF：直接传 Markdown 正文（标题/段落/加粗），长文本友好、不截断。
 */
export async function exportDocPdf(title, markdown, meta = '') {
  const r = await fetch('/api/analysis/export-pdf', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, markdown, meta: meta || null }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `PDF 生成失败 (${r.status})`);
  }
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${title}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

// 链接导航（data/config/links.json，修改配置即时生效）
export async function fetchLinks() {
  const r = await fetch('/api/links');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载链接导航失败 (${r.status})`);
  }
  return r.json(); // { groups: [{ group, items: [{name, desc, url}] }] }
}

export async function fetchData() {
  const r = await fetch('/api/data');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载情绪数据失败 (${r.status})`);
  }
  return r.json();
}

export async function fetchSector() {
  const r = await fetch('/api/sector');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载板块数据失败 (${r.status})`);
  }
  return r.json();
}

export async function fetchTicaiDates() {
  const r = await fetch('/api/ticai/dates');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载题材日期失败 (${r.status})`);
  }
  return r.json();
}

// ===== 葛南维均线评分（data/stocks/granville/{date}.json，每日 make fetch-granville 采集）=====

/**
 * 查询某交易日的葛南维均线评分。
 * date 为空时返回最新一份。返回 { exists, date, available_dates, data? }；
 * data 含 stocks（按分数降序）/ skipped（次新跳过）/ errors / generated_at。
 */
export async function fetchGranville(date = '') {
  const r = await fetch('/api/granville' + (date ? `?date=${encodeURIComponent(date)}` : ''));
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载葛南维评分失败 (${r.status})`);
  }
  return r.json();
}

// 政策/会议日历（data/meta/meeting.json，修改即时生效）
export async function fetchMeetings() {
  const r = await fetch('/api/meta/meeting');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载会议日历失败 (${r.status})`);
  }
  return r.json(); // { events: [...], total: n }
}

// 个股 → 行业 + 概念列表 反向索引（data/meta 两个全量表构建）
export async function fetchStockMap() {
  const r = await fetch('/api/meta/stock-map');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载个股归属映射失败 (${r.status})`);
  }
  return r.json();
}

// 个股 URL 映射（code → url，轻量接口）
export async function fetchStockUrls() {
  const r = await fetch('/api/stock-urls');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载个股URL失败 (${r.status})`);
  }
  return r.json();
}

// 个股信息表列表（ths_stock_info.json 轻量概要）
export async function fetchStocks() {
  const r = await fetch('/api/stocks');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载个股信息失败 (${r.status})`);
  }
  return r.json();
}

// 个股详情（完整行业 + 概念关联）
export async function fetchStockDetail(code) {
  const r = await fetch(`/api/stocks/${code}`);
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载个股详情失败 (${r.status})`);
  }
  return r.json();
}

// 概念详情弹窗（关联行业板块 + 成分股含跳转链接）
export async function fetchConceptDetail(code) {
  const r = await fetch(`/api/concepts/${code}/detail`);
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载概念详情失败 (${r.status})`);
  }
  return r.json();
}

// 目录浏览（AI 会话 cwd 选择器）：列出指定目录的子目录
export async function fetchDirList(dirPath) {
  const q = dirPath ? `?path=${encodeURIComponent(dirPath)}` : '';
  const r = await fetch(`/api/fs/dirs${q}`);
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `读取目录失败 (${r.status})`);
  }
  return r.json();
}

// AI 聊天配置（默认模型 + 可用模型列表）
export async function fetchChatConfig() {
  const r = await fetch('/api/chat/config');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载 AI 配置失败 (${r.status})`);
  }
  return r.json();
}

export async function fetchTicaiBoards(file) {
  const q = file ? `?file=${encodeURIComponent(file)}` : '';
  const r = await fetch('/api/ticai/boards' + q);
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载题材板块失败 (${r.status})`);
  }
  return r.json();
}

export async function fetchTicaiBoard(code, file) {
  const params = new URLSearchParams({ code });
  if (file) params.set('file', file);
  const r = await fetch('/api/ticai/board?' + params.toString());
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载板块成分股失败 (${r.status})`);
  }
  return r.json();
}

export async function fetchTicaiBoardTrend(code) {
  const r = await fetch('/api/ticai/board-trend?code=' + encodeURIComponent(code));
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载板块趋势失败 (${r.status})`);
  }
  return r.json();
}

// 板块详细趋势：每日涨跌停数 + 涨/跌超9%个股明细（用于题材趋势弹框）
export async function fetchTicaiBoardDetailTrend(code) {
  const r = await fetch('/api/ticai/board-detail-trend?code=' + encodeURIComponent(code));
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载板块详细趋势失败 (${r.status})`);
  }
  return r.json();
}

export async function fetchTicaiAllTrend() {
  const r = await fetch('/api/ticai/all-trend');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载题材趋势失败 (${r.status})`);
  }
  return r.json();
}

// ===== 财联社电报（scripts/cls_telegraph.py，后端按需拉取 + 60s 缓存）=====

/**
 * 拉取电报列表。
 * options: { category?: ''|'red'|'announcement'|'watch'|'hk_us'|'fund'|'remind',
 *            count?: 1-50, lastTime?: 翻页用的最早一条 ctime }
 * 返回 { count, items: [{ id, ctime, level, title, brief, stocks, plates, reading_num }] }
 */
export async function fetchTelegraph(options = {}) {
  const params = new URLSearchParams();
  if (options.category) params.set('category', options.category);
  if (options.count) params.set('count', String(options.count));
  if (options.lastTime) params.set('last_time', String(options.lastTime));
  const r = await fetch('/api/telegraph' + (params.toString() ? '?' + params.toString() : ''));
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载电报失败 (${r.status})`);
  }
  return r.json();
}

// ===== 开盘啦竞价异动（scripts/fetch_yidong.py，缓存 data/yidong/）=====

/** 已缓存的日期列表（倒序）+ 后端是否配置了凭证。返回 { dates, has_credentials } */
export async function fetchYidongDates() {
  const r = await fetch('/api/yidong/dates');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载竞价异动日期失败 (${r.status})`);
  }
  return r.json();
}

/**
 * 取某天竞价异动。date 为空=实时（当前交易日）；refresh=true 忽略缓存重拉。
 * 返回 { date, new, continued, other, from_cache, saved, empty, has_credentials }
 * 列表项：{ code, name, burst, amount, strength, net_inflow, raw }
 */
export async function fetchYidong(date = '', refresh = false) {
  const params = new URLSearchParams();
  if (date) params.set('date', date);
  if (refresh) params.set('refresh', '1');
  const r = await fetch('/api/yidong' + (params.toString() ? '?' + params.toString() : ''));
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载竞价异动失败 (${r.status})`);
  }
  return r.json();
}

// ===== 东方财富公告（scripts/fetch_gonggao.py，按月 CSV 存储 data/gonggao/）=====

/** 本地公告概览。返回 { months, total, min_date, max_date, syncing } */
export async function fetchGonggaoMeta() {
  const r = await fetch('/api/gonggao/meta');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载公告概览失败 (${r.status})`);
  }
  return r.json();
}

/**
 * 查询本地已存储公告（读 CSV，无网络请求）。
 * query: { from, to (YYYY-MM-DD), company(代码/名称), cat(分类), q(标题关键词), page, size }
 * 返回 { total, page, size, items:[{time,date,codes,names,cats,title,art_code,url,pdf}], top_cats:[{name,count}] }
 */
export async function fetchGonggao(query = {}) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== '' && v != null) params.set(k, String(v));
  }
  const r = await fetch('/api/gonggao?' + params.toString());
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `查询公告失败 (${r.status})`);
  }
  return r.json();
}

/**
 * 在线抓取并落盘。实时刷新: syncGonggao({}) 抓今天；补历史: { from, to }（≤31天）；{ days: N } 最近N天。
 * 返回 { days:[{day,fetched,added,skipped}], fetched, added }
 */
export async function syncGonggao(body = {}) {
  const r = await fetch('/api/gonggao/sync', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `抓取公告失败 (${r.status})`);
  }
  return r.json();
}

// ===== 开盘啦实时龙虎榜（scripts/fetch_lhb_realtime.py，快照落盘 data/lhb_realtime/）=====

/** 已有快照的日期列表（倒序）+ 是否配置凭证。返回 { dates, has_credentials } */
export async function fetchLhbDates() {
  const r = await fetch('/api/lhb-realtime/dates');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载实时龙虎榜日期失败 (${r.status})`);
  }
  return r.json();
}

/** 某日已落盘快照列表（时间倒序）。返回 { date, snapshots:[{id,time,range}] } */
export async function fetchLhbSnapshots(date) {
  const r = await fetch('/api/lhb-realtime/snapshots?date=' + encodeURIComponent(date));
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载快照列表失败 (${r.status})`);
  }
  return r.json();
}

/** 读取某个本地快照（不触发网络请求） */
export async function fetchLhbSnapshot(date, id) {
  const r = await fetch(`/api/lhb-realtime/snapshot?date=${encodeURIComponent(date)}&id=${encodeURIComponent(id)}`);
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载快照失败 (${r.status})`);
  }
  return r.json();
}

/**
 * 在线拉取最新实时快照（并自动落盘）。pages 1-5；start/end 为区间 HHMM（可选）。
 * 返回 { day, time, count, range, items:[{code,name,plate,price,pct,amount,net_inflow,net_ratio,board_desc,popularity,raw}], empty, saved, has_credentials }
 */
export async function fetchLhbLive({ pages = 1, start = '', end = '' } = {}) {
  const params = new URLSearchParams({ pages: String(pages) });
  if (start && end) { params.set('start', start); params.set('end', end); }
  const r = await fetch('/api/lhb-realtime?' + params.toString());
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `拉取实时龙虎榜失败 (${r.status})`);
  }
  return r.json();
}

// ===== 涨停板池（data/zt_pool/，东财涨停/炸板/跌停）=====

/** 已有涨停池数据的日期列表（倒序）。返回 { dates: ['20261020', ...] } */
export async function fetchZtPoolDates() {
  const r = await fetch('/api/zt-pool/dates');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载涨停池日期失败 (${r.status})`);
  }
  return r.json();
}

/** 某日涨停池数据。返回 { meta, 涨停: [...], 炸板: [...], 跌停: [...] }（字段为中文键） */
export async function fetchZtPool(date) {
  const r = await fetch('/api/zt-pool?date=' + encodeURIComponent(date));
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载涨停池失败 (${r.status})`);
  }
  return r.json();
}

/** 本地电报缓存日期列表（data/telegraph/，按天落盘）。返回 { dates: ['20261015', ...] } */
export async function fetchTelegraphDates() {
  const r = await fetch('/api/telegraph/dates');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载电报缓存日期失败 (${r.status})`);
  }
  return r.json();
}

/** 读取某天的本地电报缓存。返回 { date, count, items } */
export async function fetchTelegraphHistory(date) {
  const r = await fetch('/api/telegraph/history?date=' + encodeURIComponent(date));
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载电报缓存失败 (${r.status})`);
  }
  return r.json();
}

// ===== 全市场单日行情（data/market/market_data_{YYYYMMDD}.json）=====

/** 已有的全市场行情日期列表。返回 { dates: ['20260910', ...] } */
export async function fetchMarketDates() {
  const r = await fetch('/api/market/dates');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载全市场行情日期失败 (${r.status})`);
  }
  return r.json();
}

/** 某日全市场行情（含每只股票涨跌幅等）。返回 { date, meta, stocks } */
export async function fetchMarketDay(date) {
  const r = await fetch('/api/market/' + encodeURIComponent(date));
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载全市场行情失败 (${r.status})`);
  }
  return r.json();
}

// 题材板块黑名单（从 data/meta/jiufang_boards_blacklist.json 加载）
export async function fetchBoardBlacklist() {
  const r = await fetch('/api/board-blacklist');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载板块黑名单失败 (${r.status})`);
  }
  return r.json();
}

// ===== 同花顺行业板块 =====

export async function fetchIndustries() {
  const r = await fetch('/api/industries');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载行业板块失败 (${r.status})`);
  }
  return r.json();
}

export async function fetchIndustryStocks(code) {
  const r = await fetch('/api/industries/' + encodeURIComponent(code) + '/stocks');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载行业成分股失败 (${r.status})`);
  }
  return r.json();
}

// ===== 同花顺概念板块 =====

export async function fetchConcepts() {
  const r = await fetch('/api/concepts');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载概念板块失败 (${r.status})`);
  }
  return r.json();
}

export async function fetchConceptStocks(code) {
  const r = await fetch('/api/concepts/' + encodeURIComponent(code) + '/stocks');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载成分股失败 (${r.status})`);
  }
  return r.json();
}

export async function fetchConceptMap() {
  const r = await fetch('/api/concepts/map');
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载概念映射失败 (${r.status})`);
  }
  return r.json();
}

// ===== 行业-概念关联 =====

export async function fetchIndustryConceptRelations(min = 1) {
  const r = await fetch('/api/industry-concept-relations?min=' + encodeURIComponent(min));
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载行业-概念关联失败 (${r.status})`);
  }
  return r.json();
}

export async function fetchIndustryConceptOverlap(industryCode, conceptCode) {
  const r = await fetch('/api/industry-concept-overlap/' + encodeURIComponent(industryCode) + '/' + encodeURIComponent(conceptCode));
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载共有股明细失败 (${r.status})`);
  }
  return r.json();
}

// ===== AI 聊天（多轮对话，SSE 流式） =====

/**
 * 创建一个新的多轮对话会话。
 * options: { cwd, model, permissionMode, systemPrompt, mcpServers, thinking, allowedTools, disallowedTools }
 * 返回 sessionId。
 */
export async function createChatSession(options = {}) {
  const r = await fetch('/api/chat/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      cwd: options.cwd,
      model: options.model,
      permission_mode: options.permissionMode || 'plan',
      system_prompt: options.systemPrompt,
      mcp_servers: options.mcpServers,
      thinking: options.thinking,
      allowed_tools: options.allowedTools,
      disallowed_tools: options.disallowedTools,
    }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `创建会话失败 (${r.status})`);
  }
  const data = await r.json();
  return data.session_id;
}

/** 查询指定会话的 MCP 服务器连接状态。 */
export async function fetchChatMcpStatus(sessionId) {
  const r = await fetch(`/api/chat/sessions/${sessionId}/mcp`);
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `查询 MCP 状态失败 (${r.status})`);
  }
  return r.json();
}

/** 中断当前会话正在生成的回复。 */
export async function interruptChatSession(sessionId) {
  const r = await fetch(`/api/chat/sessions/${sessionId}/interrupt`, { method: 'POST' });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `中断失败 (${r.status})`);
  }
  return r.json();
}

/** 关闭会话，释放后端资源。 */
export async function closeChatSession(sessionId) {
  await fetch(`/api/chat/sessions/${sessionId}`, { method: 'DELETE' }).catch(() => {});
}

/**
 * 发送一条消息，以流式方式消费 SSE 回复。
 * 通过 onEvent(type, data) 回调实时接收：
 *   type: 'text' | 'thinking' | 'tool_use' | 'result' | 'error' | 'done'
 *
 * 返回一个 AbortController，可用于中途取消请求。
 */
export function sendChatMessageStream(sessionId, message, onEvent) {
  return postSseStream(`/api/chat/sessions/${sessionId}/messages`, { message }, onEvent);
}

// ===== 单只涨停股 AI 分析（明日/后日上涨概率，SSE 流式） =====

/**
 * 触发单只涨停股的 AI 深度分析（SSE 流式）。
 * stock: 涨停股数据对象（code/name/board/seal_amount 等）。
 * onEvent 事件: 'status' | 'text' | 'thinking' | 'tool_use' | 'heartbeat' | 'result' | 'error' | 'done'
 * 返回 AbortController 可中途取消。
 */
export function streamStockAnalysis(stock, options = {}, onEvent) {
  return postSseStream(
    '/api/analysis/stock',
    { stock, model: options.model || null },
    onEvent
  );
}

/**
 * 读取个股分析提示词配置（data/config/stock_ai_analysis_prompt.md）。
 * 返回 { exists, file, prompt }。
 */
export async function fetchStockPrompt() {
  const r = await fetch('/api/config/stock-prompt');
  if (!r.ok) throw new Error(`读取个股提示词失败 (${r.status})`);
  return r.json();
}

// ===== 分时/分笔成交数据（data/stocks_daily/{date}/，每日 make fetch-tick 或页面下载）=====

/** 已有分时数据的日期列表。返回 { dates: ['20260901', ...] } */
export async function fetchTickDates() {
  const r = await fetch('/api/ticks/dates');
  if (!r.ok) throw new Error(`加载分时日期失败 (${r.status})`);
  return r.json();
}

/** 某日期已下载的股票列表。返回 { date, stocks: [{code, name, modes}] } */
export async function fetchTickList(date) {
  const r = await fetch('/api/ticks/list?date=' + encodeURIComponent(date));
  if (!r.ok) throw new Error(`加载分时股票列表失败 (${r.status})`);
  return r.json();
}

/** 读取某股票某模式的 CSV 数据。mode: 'ticks' | 'minute'。返回 { file, columns, rows } */
export async function fetchTickData(date, code, mode) {
  const r = await fetch(
    `/api/ticks/data?date=${encodeURIComponent(date)}&code=${encodeURIComponent(code)}&mode=${encodeURIComponent(mode)}`
  );
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || `加载分时数据失败 (${r.status})`);
  }
  return r.json();
}

/**
 * 触发批量下载分时数据（SSE 流式进度）。
 * codes: 股票代码数组；date: YYYYMMDD；mode: 'auto'|'ticks'|'minute'
 * onEvent 事件: 'status' | 'progress' {index,total,code,group,ok,file?/error?} | 'done' {results,ok}
 */
export function streamTickFetch(codes, date, mode, onEvent, force = false) {
  return postSseStream('/api/ticks/fetch', { codes, date, mode: mode || 'auto', force }, onEvent);
}

/**
 * 按题材分组下载分时数据（SSE 流式进度）。
 * groups: { 题材名: { code: 名称 } }，按题材建子目录存储
 */
export function streamTickFetchGroups(groups, date, mode, onEvent, force = false) {
  return postSseStream('/api/ticks/fetch', { groups, date, mode: mode || 'auto', force }, onEvent);
}

// ===== 涨停股 AI 复盘分析（结果按天缓存在 data/analysis/） =====

/**
 * 查询某天的涨停股 AI 分析缓存（不发 AI 请求）。
 * 返回 { exists, date, data? }；data 含 analysis(Markdown)/generated_at/model 等。
 */
export async function fetchLimitupAnalysis(date) {
  const r = await fetch('/api/analysis/limitup?date=' + encodeURIComponent(date));
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `查询分析缓存失败 (${r.status})`);
  }
  return r.json();
}

/**
 * 触发涨停股 AI 分析（SSE 流式）。
 * options: { force?: boolean, model?: string }
 * onEvent 事件: 'status' | 'cached' | 'text' | 'thinking' | 'tool_use' | 'result' | 'saved' | 'error' | 'done'
 * 返回 AbortController 可中途取消。
 */
export function streamLimitupAnalysis(date, options = {}, onEvent) {
  return postSseStream(
    '/api/analysis/limitup',
    { date, force: !!options.force, model: options.model || null },
    onEvent
  );
}

// 通用：POST + 消费 SSE 流式响应（fetch ReadableStream 解析 "event: x\ndata: {...}" 帧）

/**
 * 保存 AI 市场分析结果到 data/analysis/market_{YYYYMMDD}.json（同时写 .md）。
 * 返回 { saved, file, md, date, generated_at, title }。
 */
export async function saveMarketAnalysis({ analysis, title = '', date = '' }) {
  const r = await fetch('/api/analysis/market', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ analysis, title, date }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `保存失败 (${r.status})`);
  }
  return r.json();
}

function postSseStream(url, body, onEvent) {
  const controller = new AbortController();

  (async () => {
    let resp;
    try {
      resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
    } catch (e) {
      if (e.name !== 'AbortError') onEvent('error', { error: e.message });
      onEvent('done', {});
      return;
    }
    if (!resp.ok || !resp.body) {
      const err = await resp.json().catch(() => ({}));
      onEvent('error', { error: err.detail || err.error || `请求失败 (${resp.status})` });
      onEvent('done', {});
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE 帧以 \n\n 分隔，每帧包含 "event: xxx\ndata: {...}"
        let idx;
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          const eventMatch = frame.match(/^event: (.+)$/m);
          const dataMatch = frame.match(/^data: (.+)$/m);
          if (eventMatch && dataMatch) {
            try {
              const data = JSON.parse(dataMatch[1]);
              onEvent(eventMatch[1], data);
            } catch {
              /* 忽略解析失败的帧 */
            }
          }
        }
      }
    } catch (e) {
      if (e.name !== 'AbortError') onEvent('error', { error: e.message });
    }
  })();

  return controller;
}
