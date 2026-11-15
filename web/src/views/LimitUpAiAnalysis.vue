<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue';
import { fetchLimitupAnalysis, streamLimitupAnalysis } from '../api.js';
import { renderMarkdown, formatDate } from '../utils.js';

// 当日涨停股 AI 复盘分析（题材分类 / 催化原因 / 财报披露）
// 结果按天缓存在 data/analysis/{YYYYMMDD}.json：
//   - 默认只读缓存（不发 AI 请求）
//   - 无缓存 → 「生成分析」；有缓存 → 「重新分析」（force 强制覆盖）
const props = defineProps({
  date: { type: String, default: '' }, // YYYYMMDD
});

// 已缓存的分析结果 { date, generated_at, model, stock_count, duration_ms, analysis }
const cached = ref(null);
const loading = ref(false);
// 生成中状态（SSE 流式）
const running = ref(false);
const output = ref('');
const thinking = ref('');
const showThinking = ref(false);
const statusMsg = ref('');
const stats = ref(null); // { duration_ms, num_turns, total_cost_usd }
const error = ref('');
// 过程反馈：本地耗时计时 + AI 工具调用记录（让"分析中"看得见）
const elapsed = ref(0); // 秒
const toolCalls = ref([]); // [{ label, at }] 最近在前
let elapsedTimer = null;
let aborter = null;

const TOOL_LABELS = {
  WebSearch: '联网搜索',
  web_search: '联网搜索',
  WebFetch: '抓取网页',
  web_fetch: '抓取网页',
  Read: '读取文件',
  Grep: '检索内容',
  Glob: '查找文件',
  Bash: '执行命令',
};

const dateLabel = computed(() => (props.date ? formatDate(props.date) : ''));

const elapsedText = computed(() => {
  const s = elapsed.value;
  if (s < 60) return `${s} 秒`;
  return `${Math.floor(s / 60)} 分 ${s % 60} 秒`;
});

// 最近一次工具调用（展示"AI 正在干什么"）
const lastTool = computed(() => toolCalls.value[0] || null);

async function loadCache() {
  cached.value = null;
  error.value = '';
  if (!props.date) return;
  loading.value = true;
  try {
    const r = await fetchLimitupAnalysis(props.date);
    if (r.exists) cached.value = r.data;
  } catch (e) {
    error.value = friendlyError(e.message);
  } finally {
    loading.value = false;
  }
}

// 错误信息友好化：给出可操作的提示
function friendlyError(msg) {
  const m = String(msg || '');
  if (m.includes('Not Found') || /\b404\b/.test(m)) {
    return 'AI 后端未加载分析接口（404）。分析接口是新增的，请重启 AI 后端后重试：cd ai_agent/python && python3 chat_server.py';
  }
  if (m.includes('无法连接') || m.includes('Connection') || m.includes('Failed to fetch') || /\b502\b/.test(m)) {
    return `AI 后端未启动或已断开：${m}\n请启动：cd ai_agent/python && python3 chat_server.py`;
  }
  if (m.includes('正在进行中') || /\b409\b/.test(m)) {
    return `${m}（同一天只能同时分析一次，可稍候再试）`;
  }
  return m;
}

onMounted(loadCache);
watch(() => props.date, loadCache);

function scrollBottom() {
  nextTick(() => {
    if (outBox.value) outBox.value.scrollTop = outBox.value.scrollHeight;
  });
}

function scrollThinking() {
  nextTick(() => {
    if (thinkBox.value) thinkBox.value.scrollTop = thinkBox.value.scrollHeight;
  });
}

function stopTimer() {
  if (elapsedTimer) {
    clearInterval(elapsedTimer);
    elapsedTimer = null;
  }
}

// force: true = 忽略缓存，强制重新分析
function analyze(force) {
  if (running.value || !props.date) return;
  error.value = '';
  output.value = '';
  thinking.value = '';
  stats.value = null;
  toolCalls.value = [];
  // 点击立即反馈：不等任何服务端事件
  statusMsg.value = '已提交分析请求，正在组装当日涨停数据并调用 AI…';
  elapsed.value = 0;
  stopTimer();
  elapsedTimer = setInterval(() => {
    elapsed.value += 1;
  }, 1000);
  showThinking.value = true; // 生成中实时展开思考过程
  running.value = true;

  aborter = streamLimitupAnalysis(props.date, { force }, (ev, data) => {
    if (ev === 'status') {
      if (data.message) statusMsg.value = data.message;
    } else if (ev === 'heartbeat') {
      // AI 联网搜索/抓网页期间长时间无输出 → 心跳保持"分析中"可见
      if (data.message && !output.value && !thinking.value) statusMsg.value = data.message;
    } else if (ev === 'text') {
      output.value += data.text;
      scrollBottom();
    } else if (ev === 'thinking') {
      thinking.value += data.text;
      scrollThinking();
    } else if (ev === 'tool_use') {
      // 记录 AI 工具调用，展示"AI 正在联网搜索/抓取网页…"
      toolCalls.value.unshift({
        label: TOOL_LABELS[data.name] || data.name,
        at: elapsed.value,
      });
      if (toolCalls.value.length > 12) toolCalls.value.length = 12;
    } else if (ev === 'result') {
      stats.value = data;
    } else if (ev === 'saved') {
      statusMsg.value = `分析完成，已保存到 data/analysis/${data.date}.json`;
    } else if (ev === 'error') {
      error.value = friendlyError(data.error || 'AI 分析失败');
    } else if (ev === 'done') {
      running.value = false;
      stopTimer();
      showThinking.value = false;
      loadCache(); // 重新拉取缓存（保存成功后展示带元信息的完整结果）
    }
  });
}

function stop() {
  aborter && aborter.abort();
  running.value = false;
  stopTimer();
  statusMsg.value = '已停止（本次未完成，不保存结果）';
}

onUnmounted(() => {
  stopTimer();
  aborter && aborter.abort();
});

// 耗时格式化
const durationText = computed(() => {
  const ms = stats.value?.duration_ms ?? cached.value?.duration_ms;
  if (ms == null) return '';
  return ms >= 60000 ? `${Math.round(ms / 60000)} 分钟` : `${Math.round(ms / 1000)} 秒`;
});
</script>

<template>
  <div class="panel luai-panel">
    <div class="luai-head">
      <h2>涨停股信息 AI 分析</h2>
      <span class="luai-sub" v-if="dateLabel">
        {{ dateLabel }} ·
        <template v-if="cached"
          >已分析（{{ cached.generated_at }}<template v-if="cached.model"> · {{ cached.model }}</template
          ><template v-if="cached.stock_count"> · {{ cached.stock_count }} 只</template>）</template
        >
        <template v-else>尚未分析</template>
      </span>
      <div class="luai-actions">
        <button
          v-if="!cached && !running"
          class="luai-btn"
          :disabled="!date"
          title="调用 AI 分析当日涨停股：题材分类（列全个股）→ 催化原因核实 → 财报披露日历"
          @click="analyze(false)"
        >
          ⚡ 生成分析
        </button>
        <button
          v-if="cached && !running"
          class="luai-btn ghost"
          title="忽略已有结果，强制重新调用 AI 分析"
          @click="analyze(true)"
        >
          ↻ 重新分析
        </button>
        <button v-if="running" class="luai-btn stop" @click="stop">■ 停止</button>
      </div>
    </div>

    <div class="luai-body" ref="outBox">
      <div v-if="error" class="luai-error">{{ error }}</div>

      <!-- 分析中状态条：进度动画 + 本地计时 + AI 工具活动（让"分析中"看得见） -->
      <div v-if="running" class="luai-status">
        <span class="luai-spin"></span>
        <div class="luai-status-main">
          <div class="luai-status-line">{{ statusMsg || 'AI 分析中…' }}</div>
          <div class="luai-status-sub">
            <span class="luai-timer">⏱ 已进行 {{ elapsedText }}</span>
            <span v-if="lastTool" class="luai-tool">
              🔧 {{ lastTool.label }}中…<template v-if="toolCalls.length > 1">
                （累计 {{ toolCalls.length }} 次工具调用）</template
              >
            </span>
            <span v-else class="luai-tool-dim">联网核实新闻与财报需要几分钟，可随时停止</span>
          </div>
        </div>
      </div>

      <!-- 思考过程：生成中实时展示，无输出时给占位提示 -->
      <div v-if="running || thinking" class="luai-thinking">
        <button class="tg-btn" @click="showThinking = !showThinking">
          {{ showThinking ? '▾' : '▸' }} 思考过程{{ running ? '（进行中…）' : '' }}
        </button>
        <pre v-if="showThinking && thinking" class="thinking-text" ref="thinkBox">{{ thinking }}</pre>
        <div v-else-if="showThinking && running && !thinking" class="thinking-wait">
          等待 AI 输出第一段思考…（模型深度思考/调用工具期间可能数十秒无输出，属正常现象）
        </div>
      </div>

      <!-- 生成中：流式渲染 -->
      <div v-if="running && output" class="md-body" v-html="renderMarkdown(output)"></div>
      <div v-else-if="running && !output" class="luai-empty">
        AI 正在分析题材分类 / 核实催化原因 / 查询财报披露，分析结果将在这里实时输出…
      </div>
      <!-- 非生成中：展示缓存结果 -->
      <div v-else-if="cached" class="md-body" v-html="renderMarkdown(cached.analysis)"></div>
      <div
        v-else-if="!running && !error && !loading"
        class="luai-empty"
      >
        <template v-if="dateLabel"
          >{{ dateLabel }} 暂无 AI 分析结果。点击「生成分析」，AI 将：① 对涨停股做题材分类（完整列出每个分类下全部个股）②
          联网核实催化原因（重大利好新闻/公告）③ 梳理财报披露时间。结果按天缓存，次日自动读取。</template
        >
        <template v-else>等待涨停数据加载…</template>
      </div>

      <div v-if="durationText && !running" class="luai-meta">AI 耗时约 {{ durationText }}</div>
    </div>
  </div>
</template>

<style scoped>
.luai-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.luai-head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.luai-head h2 {
  margin: 0;
  font-size: 15px;
}
.luai-sub {
  font-size: 12px;
  color: var(--text-dim);
}
.luai-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
  flex-wrap: wrap;
}
.luai-btn {
  font-size: 12.5px;
  font-weight: 600;
  color: #fff;
  background: var(--blue);
  border: none;
  border-radius: 16px;
  padding: 6px 16px;
  cursor: pointer;
  transition: all 0.15s;
}
.luai-btn:hover:not(:disabled) {
  filter: brightness(1.08);
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.35);
}
.luai-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.luai-btn.ghost {
  background: var(--card-2);
  color: var(--text-dim);
  border: 1px solid var(--border);
}
.luai-btn.stop {
  background: #dc2626;
}
.luai-body {
  max-height: 560px;
  overflow-y: auto;
  background: var(--card-2);
  border-radius: 10px;
  padding: 14px;
  min-height: 80px;
}
.luai-empty {
  color: var(--text-dim);
  font-size: 12.5px;
  text-align: center;
  padding: 28px 20px;
  line-height: 1.8;
}
.luai-error {
  color: #dc2626;
  font-size: 12.5px;
  padding: 8px 10px;
  white-space: pre-wrap;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  line-height: 1.7;
  margin-bottom: 8px;
}
.luai-status {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 10px;
  margin-bottom: 10px;
}
.luai-spin {
  width: 14px;
  height: 14px;
  border: 2px solid var(--blue);
  border-top-color: transparent;
  border-radius: 50%;
  animation: luai-rotate 0.8s linear infinite;
  flex-shrink: 0;
  margin-top: 2px;
}
.luai-status-main {
  flex: 1;
  min-width: 0;
}
.luai-status-line {
  font-size: 13px;
  font-weight: 600;
  color: var(--blue);
  line-height: 1.5;
}
.luai-status-sub {
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 12px;
}
.luai-timer {
  color: var(--blue);
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
.luai-tool {
  color: #b45309;
  background: #fef3c7;
  border-radius: 10px;
  padding: 1px 10px;
  font-weight: 600;
}
.luai-tool-dim {
  color: var(--text-dim);
  font-size: 11.5px;
}
@keyframes luai-rotate {
  to {
    transform: rotate(360deg);
  }
}
.luai-thinking {
  margin-bottom: 10px;
}
.tg-btn {
  font-size: 11px;
  color: var(--text-dim);
  background: none;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 2px 10px;
  cursor: pointer;
}
.thinking-text {
  white-space: pre-wrap;
  font-size: 11.5px;
  color: var(--text-dim);
  background: #fff;
  border-radius: 8px;
  padding: 10px;
  max-height: 180px;
  overflow-y: auto;
  margin: 6px 0 0;
}
.thinking-wait {
  margin: 6px 0 0;
  font-size: 11.5px;
  color: var(--text-dim);
  background: #fff;
  border: 1px dashed var(--border);
  border-radius: 8px;
  padding: 10px;
  line-height: 1.7;
}
.luai-meta {
  margin-top: 10px;
  font-size: 11.5px;
  color: var(--text-dim);
  text-align: right;
}

/* Markdown 渲染样式 */
.md-body :deep(h3) {
  font-size: 15px;
  margin: 16px 0 6px;
  color: var(--text);
}
.md-body :deep(h4) {
  font-size: 13.5px;
  margin: 12px 0 4px;
  color: var(--text);
}
.md-body :deep(h5),
.md-body :deep(h6) {
  font-size: 13px;
  margin: 10px 0 4px;
  color: var(--text-dim);
}
.md-body :deep(p) {
  margin: 6px 0;
  font-size: 13px;
  line-height: 1.75;
}
.md-body :deep(ul),
.md-body :deep(ol) {
  margin: 6px 0;
  padding-left: 20px;
}
.md-body :deep(li) {
  font-size: 13px;
  line-height: 1.7;
  margin: 2px 0;
}
.md-body :deep(table) {
  border-collapse: collapse;
  margin: 10px 0;
  width: 100%;
  font-size: 12.5px;
  background: #fff;
}
.md-body :deep(th),
.md-body :deep(td) {
  border: 1px solid var(--border);
  padding: 5px 8px;
  text-align: left;
  vertical-align: top;
}
.md-body :deep(th) {
  background: var(--card-2);
  font-weight: 600;
  white-space: nowrap;
}
.md-body :deep(code) {
  background: #fff;
  border: 1px solid var(--border);
  padding: 0 5px;
  border-radius: 4px;
  font-size: 12px;
}
.md-body :deep(pre) {
  background: #fff;
  border: 1px solid var(--border);
  padding: 10px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 12px;
  margin: 8px 0;
}
.md-body :deep(blockquote) {
  border-left: 3px solid var(--blue);
  padding: 2px 10px;
  margin: 8px 0;
  color: var(--text-dim);
  font-size: 12.5px;
}
.md-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--border);
  margin: 14px 0;
}
.md-body :deep(a) {
  color: var(--blue);
}
.md-body :deep(b) {
  color: var(--red, #d93026);
}
</style>
