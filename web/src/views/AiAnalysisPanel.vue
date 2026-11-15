<script setup>
import { ref, onMounted, nextTick } from 'vue';
import { createChatSession, sendChatMessageStream, saveMarketAnalysis } from '../api.js';

// ===== 状态 =====
const loadingData = ref(true);
const sessionId = ref(null);
const running = ref(false);
const output = ref('');
const thinking = ref('');
const showThinking = ref(false);
const error = ref(null);
const followUp = ref('');
const outBox = ref(null);
const thinkBox = ref(null);
let aborter = null;

// 当日市场数据（一次拉取，构造分析上下文用）
let dayData = null;
let dayKey = '';

const ANALYSES = [
  { key: 'overview', label: '市场情绪总览' },
  { key: 'limitup', label: '涨停结构分析' },
  { key: 'risk', label: '跌停炸板风险' },
];

onMounted(async () => {
  try {
    const r = await fetch('/api/data');
    if (!r.ok) throw new Error(`加载数据失败 (${r.status})`);
    const d = await r.json();
    const keys = Object.keys(d.data || {}).sort();
    dayKey = keys[keys.length - 1] || '';
    dayData = d.data[dayKey] || {};
  } catch (e) {
    error.value = e.message;
  } finally {
    loadingData.value = false;
  }
});

// ===== 构造分析 prompt（把当日关键数据摘要喂给 AI） =====
function fmtPct(v) {
  return v == null ? '-' : `${Number(v) > 0 ? '+' : ''}${Number(v).toFixed(2)}%`;
}
function conceptTopN(stocks, n = 8) {
  // 概念计数（依赖后端 stock-map 不方便，这里直接用股票的 concepts 字段——涨停数据无此字段，
  // 用行业聚合 + 连板梯队替代；若需要概念可后续接 meta 接口）
  const ind = new Map();
  for (const s of stocks) {
    const k = s.industry || '其他';
    ind.set(k, (ind.get(k) || 0) + 1);
  }
  return [...ind.entries()].sort((a, b) => b[1] - a[1]).slice(0, n)
    .map(([k, c]) => `${k}(${c}只)`).join('、');
}
function ladder(stocks) {
  const m = new Map();
  for (const s of stocks) {
    const b = s.board || 1;
    m.set(b, (m.get(b) || 0) + 1);
  }
  return [...m.entries()].sort((a, b) => b[0] - a[0])
    .map(([b, c]) => `${b}板×${c}`).join('、');
}
function topSeals(stocks, n = 5) {
  return [...stocks].sort((a, b) => (b.seal_amount || 0) - (a.seal_amount || 0)).slice(0, n)
    .map((s) => `${s.name}(${((s.seal_amount || 0) / 1e8).toFixed(2)}亿)`).join('、');
}

function buildContext() {
  const ups = dayData.limit_up_stocks || [];
  const downs = dayData.limit_down_stocks || [];
  const blows = dayData.blow_up_stocks || [];
  const idx = dayData.indices || {};
  const maxBoard = ups.reduce((m, s) => Math.max(m, s.board || 1), 0);
  const maxBoardStocks = ups.filter((s) => (s.board || 1) === maxBoard).map((s) => s.name);
  const idxText = ['上证指数', '深证成指', '创业板指']
    .map((n) => `${n}${fmtPct(idx[n]?.pct_change)}`).join('，');
  return [
    `日期：${dayKey}`,
    `三大指数：${idxText}`,
    `涨停${ups.length}只（最高连板${maxBoard}板：${maxBoardStocks.join('、') || '-'}），跌停${downs.length}只，炸板${blows.length}只`,
    `涨停连板梯队：${ladder(ups) || '无'}`,
    `涨停行业分布TOP8：${conceptTopN(ups)}`,
    `跌停行业分布：${conceptTopN(downs, 5) || '无'}`,
    `炸板行业分布：${conceptTopN(blows, 5) || '无'}`,
    `封单金额TOP5：${topSeals(ups) || '无'}`,
    `跌停股：${downs.map((s) => s.name).join('、') || '无'}`,
    `炸板股：${blows.map((s) => s.name).join('、') || '无'}`,
  ].join('\n');
}

const PROMPTS = {
  overview: (ctx) =>
    `你是一名资深A股市场情绪分析师。以下是最新交易日（${dayKey}）的市场数据，请从赚钱效应、亏钱效应、市场情绪周期（冰点/回暖/高潮/退潮）等角度做一段简明扼要的分析，给出结论和明日关注要点：\n\n${ctx}`,
  limitup: (ctx) =>
    `你是一名资深A股涨停板复盘分析师。以下是最新交易日的涨停数据，请分析：1）连板梯队结构与高度；2）行业/题材主线与资金合力方向；3）封单质量（封单金额与板块地位）；4）明日涨停晋级展望。要求条理清晰、有具体个股依据：\n\n${ctx}`,
  risk: (ctx) =>
    `你是一名资深A股风险控制分析师。以下是最新交易日的跌停与炸板数据，请分析：1）亏钱效应集中方向；2）跌停股与炸板股的共性（高位退潮？题材出清？）；3）对短线情绪的影响与回避建议：\n\n${ctx}`,
};

// ===== 会话与流式调用 =====
async function ensureSession() {
  if (sessionId.value) return sessionId.value;
  sessionId.value = await createChatSession({
    permissionMode: 'plan',
    thinking: 'enabled', // 开启思考过程流式输出
    systemPrompt:
      '你是一名专业的A股市场情绪与短线交易分析师，擅长连板梯队、题材轮动、资金博弈分析。回答用中文，条理清晰，直接给结论和依据，不啰嗦。',
  });
  return sessionId.value;
}

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

async function send(prompt) {
  if (running.value || !prompt) return;
  error.value = null;
  output.value = '';
  thinking.value = '';
  showThinking.value = true; // 生成中实时展开思考过程
  running.value = true;
  try {
    const sid = await ensureSession();
    aborter = sendChatMessageStream(sid, prompt, (ev, data) => {
      if (ev === 'text') {
        output.value += data.text;
        scrollBottom();
      } else if (ev === 'thinking') {
        thinking.value += data.text;
        scrollThinking();
      } else if (ev === 'error') {
        error.value = data.error || 'AI 调用失败';
      } else if (ev === 'done') {
        running.value = false;
        showThinking.value = false; // 生成完成后自动收起思考过程（可点击回看）
      }
    });
  } catch (e) {
    error.value = e.message || '会话创建失败';
    running.value = false;
  }
}

function runAnalysis(key) {
  if (loadingData.value || !dayData) {
    error.value = '市场数据尚未加载完成';
    return;
  }
  send(PROMPTS[key](buildContext()));
}

function sendFollowUp() {
  const q = followUp.value.trim();
  if (!q) return;
  followUp.value = '';
  send(q);
}

function stop() {
  aborter && aborter.abort();
  running.value = false;
}

function reset() {
  stop();
  sessionId.value = null;
  output.value = '';
  thinking.value = '';
  error.value = null;
}

// ===== 保存分析结果到 data/analysis/ =====
const saving = ref(false);
const saveMsg = ref(''); // 保存反馈：成功提示 / 错误
let saveTimer = null;

async function saveAnalysis() {
  const text = (output.value || '').trim();
  if (!text || saving.value) return;
  saving.value = true;
  saveMsg.value = '';
  try {
    const r = await saveMarketAnalysis({ analysis: text, date: dayKey });
    const files = ['md', 'json'].filter((k) => r[k]).join(' / ');
    const pdfTip = r.pdf_ok ? '（含 PDF）' : (r.pdf_error ? `（PDF 未生成：${r.pdf_error}）` : '');
    saveMsg.value = `已保存：data/analysis/market_${r.date}.${files}${pdfTip}`;
  } catch (e) {
    saveMsg.value = '保存失败：' + (e.message || '未知错误');
  } finally {
    saving.value = false;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      saveMsg.value = '';
    }, 4000);
  }
}
</script>

<template>
  <div class="ai-panel">
    <div class="ai-head">
      <h2>AI 市场分析</h2>
      <span class="ai-sub" v-if="dayKey">{{ dayKey }} · 数据已就绪</span>
      <span class="ai-sub" v-else-if="loadingData">数据加载中...</span>
      <div class="ai-actions">
        <button
          v-for="a in ANALYSES"
          :key="a.key"
          class="ai-btn"
          :disabled="running || loadingData"
          @click="runAnalysis(a.key)"
        >
          {{ a.label }}
        </button>
        <button v-if="running" class="ai-btn stop" @click="stop">■ 停止</button>
        <button v-if="output && !running" class="ai-btn save" :disabled="saving" @click="saveAnalysis">
          {{ saving ? '保存中…' : '💾 保存' }}
        </button>
        <button v-if="output" class="ai-btn ghost" @click="reset">新话题</button>
      </div>
    </div>

    <div v-if="saveMsg" class="ai-save-msg" :class="{ err: saveMsg.includes('失败') }">
      {{ saveMsg }}
    </div>

    <div class="ai-body" ref="outBox">
      <div v-if="!output && !running && !error" class="ai-empty">
        点击上方按钮，AI 将基于当日市场数据（指数、涨停梯队、行业分布、封单、跌停炸板）生成分析
      </div>
      <div v-if="error" class="ai-error">
        {{ error }}
        <div v-if="error.includes('Authentication')" class="ai-error-tip">
          AI 服务需要登录 CodeBuddy CLI：终端执行 <code>codebuddy</code> 后输入 <code>/login</code> 完成登录（一次即可）
        </div>
      </div>
      <div v-if="thinking" class="ai-thinking">
        <button class="tg-btn" @click="showThinking = !showThinking">
          {{ showThinking ? '▾' : '▸' }} 思考过程{{ running ? '（进行中…）' : '' }}
        </button>
        <pre v-if="showThinking" class="thinking-text" ref="thinkBox">{{ thinking }}</pre>
      </div>
      <pre v-if="output" class="ai-output">{{ output }}<span v-if="running" class="cursor">▍</span></pre>
    </div>

    <div class="ai-foot" v-if="output || running">
      <input
        class="search ai-input"
        v-model="followUp"
        :disabled="running"
        placeholder="继续追问（基于本次分析上下文）..."
        @keyup.enter="sendFollowUp"
      />
      <button class="ai-btn" :disabled="running || !followUp.trim()" @click="sendFollowUp">发送</button>
    </div>
  </div>
</template>

<style scoped>
.ai-panel {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.ai-head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.ai-head h2 {
  margin: 0;
  font-size: 15px;
}
.ai-sub {
  font-size: 12px;
  color: var(--text-dim);
}
.ai-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
  flex-wrap: wrap;
}
.ai-btn {
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
.ai-btn:hover:not(:disabled) {
  filter: brightness(1.08);
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.35);
}
.ai-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.ai-btn.stop {
  background: #dc2626;
}
.ai-btn.ghost {
  background: var(--card-2);
  color: var(--text-dim);
  border: 1px solid var(--border);
}
.ai-btn.save {
  background: #16a34a;
}
.ai-btn.save:hover:not(:disabled) {
  box-shadow: 0 2px 8px rgba(22, 163, 74, 0.35);
}
.ai-save-msg {
  font-size: 12px;
  color: #16a34a;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 8px;
  padding: 6px 10px;
}
.ai-save-msg.err {
  color: #dc2626;
  background: #fef2f2;
  border-color: #fecaca;
}
.ai-body {
  min-height: 160px;
  max-height: 420px;
  overflow-y: auto;
  background: var(--card-2);
  border-radius: 10px;
  padding: 14px;
}
.ai-empty {
  color: var(--text-dim);
  font-size: 12.5px;
  text-align: center;
  padding: 40px 20px;
}
.ai-error {
  color: #dc2626;
  font-size: 12.5px;
  padding: 8px;
}
.ai-error-tip {
  margin-top: 8px;
  padding: 8px 10px;
  background: #fef2f2;
  border-radius: 8px;
  font-size: 12px;
}
.ai-error-tip code {
  background: #fff;
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid #fecaca;
  font-size: 11px;
}
.ai-output {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.75;
  margin: 0;
}
.cursor {
  animation: blink 0.9s infinite;
  color: var(--blue);
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}
.ai-thinking {
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
.ai-foot {
  display: flex;
  gap: 8px;
}
.ai-input {
  flex: 1;
}
</style>
