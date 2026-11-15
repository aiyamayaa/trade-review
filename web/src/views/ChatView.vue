<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue';
import {
  createChatSession,
  sendChatMessageStream,
  interruptChatSession,
  closeChatSession,
  fetchChatConfig,
  fetchDirList,
} from '../api.js';
import { renderMarkdown } from '../utils.js';

// ===== 极简对话框：零配置，进入即聊 =====
// - 会话懒创建：首次发消息时才创建（模型跟随 data/config/ai_config.json，无需手填）
// - 顶栏：模型下拉（切换即开新对话）+ 📁 工作目录（授权 AI 访问该文件夹）+ 新对话按钮
// - 消息支持：流式正文(Markdown) / 思考过程折叠 / 工具调用 / 停止

const sessionId = ref('');
const sessionModel = ref(''); // 当前会话实际使用的模型（展示用）
const messages = ref([]); // { role, text, thinking, thinkingOpen, toolCalls, meta, streaming, error }
const input = ref('');
const sending = ref(false);
let aborter = null;

// ===== 工作目录（把文件夹"交给"AI：会话绑定 cwd，AI 可读取/检索该目录下文件）=====
const selectedCwd = ref(''); // 选中的工作目录（空 = 后端默认）
// 目录浏览弹窗
const cwdOpen = ref(false);
const cwdPath = ref(''); // 当前浏览路径
const cwdParent = ref(null);
const cwdDirs = ref([]);
const cwdLoading = ref(false);
const cwdError = ref('');
const selectedDir = ref(''); // 列表内单选高亮（仅视觉）

async function openCwdDialog() {
  cwdOpen.value = true;
  // 默认从当前选中目录（或家目录）开始浏览
  await browseDirs(selectedCwd.value || undefined);
}

async function browseDirs(dirPath) {
  cwdLoading.value = true;
  cwdError.value = '';
  try {
    const r = await fetchDirList(dirPath);
    cwdPath.value = r.path;
    cwdParent.value = r.parent;
    cwdDirs.value = r.dirs || [];
  } catch (e) {
    cwdError.value = e.message;
  } finally {
    cwdLoading.value = false;
  }
}

// 确认选择当前浏览的目录作为 AI 工作目录
function chooseCwd() {
  if (!cwdPath.value) return;
  const changed = selectedCwd.value !== cwdPath.value;
  selectedCwd.value = cwdPath.value;
  cwdOpen.value = false;
  // cwd 是会话创建参数，切换目录 → 开新对话（与切换模型一致）
  if (changed && (sessionId.value || messages.value.length)) newChat();
}

function clearCwd() {
  const changed = !!selectedCwd.value;
  selectedCwd.value = '';
  cwdOpen.value = false;
  if (changed && (sessionId.value || messages.value.length)) newChat();
}

const cwdLabel = computed(() => {
  if (!selectedCwd.value) return '默认目录';
  const p = selectedCwd.value;
  return p.length > 26 ? '…' + p.slice(-25) : p;
});

// 模型列表（默认跟随配置文件）
const modelChoice = ref('');
const availableModels = ref([]);
const defaultModel = ref(null);
onMounted(async () => {
  try {
    const cfg = await fetchChatConfig();
    availableModels.value = cfg.available_models || [];
    defaultModel.value = cfg.default_model || null;
  } catch (e) {
    console.warn('加载 AI 模型配置失败:', e);
  }
});

const QUICK_TIPS = [
  '用大白话解释一下 A 股打板的「炸板」「烂板」是什么意思',
  '短线情绪周期（冰点→回暖→高潮→退潮）各阶段有什么特征？',
  '帮我写一个 Python 脚本：批量重命名当前目录下的图片文件',
  'asyncio 异步编程有哪些常见的坑？',
];

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
const toolLabel = (n) => TOOL_LABELS[n] || n;

const scrollBox = ref(null);
const inputEl = ref(null);

function scrollToBottom() {
  nextTick(() => {
    if (scrollBox.value) scrollBox.value.scrollTop = scrollBox.value.scrollHeight;
  });
}

// 错误友好化：给出可操作的提示
function friendlyError(msg) {
  const m = String(msg || '');
  if (m.includes('Authentication') || m.includes('认证')) {
    return 'AI 认证失败：请检查 data/config/codebuddy_token.txt 中的 token 是否有效';
  }
  if (m.includes('无法连接') || m.includes('Connection') || m.includes('Failed to fetch') || /\b502\b/.test(m)) {
    return `AI 后端未启动：${m}\n请启动：cd ai_agent/python && python3 chat_server.py`;
  }
  return m;
}

// ===== 会话管理 =====
async function ensureSession() {
  if (sessionId.value) return sessionId.value;
  sessionId.value = await createChatSession({
    model: modelChoice.value || undefined,
    cwd: selectedCwd.value || undefined, // 工作目录：AI 可读取/检索该文件夹下的文件
    permissionMode: 'plan',
    thinking: 'adaptive',
  });
  sessionModel.value = modelChoice.value || defaultModel.value || '默认模型';
  return sessionId.value;
}

// 切换模型：模型在创建会话时固定，切换即开启新对话
function onModelChange() {
  if (sessionId.value || messages.value.length) newChat();
}

function newChat() {
  stop();
  if (sessionId.value) closeChatSession(sessionId.value).catch(() => {});
  sessionId.value = '';
  sessionModel.value = '';
  messages.value = [];
}

// ===== 发送 =====
async function send(presetText) {
  const text = (presetText || input.value).trim();
  if (!text || sending.value) return;
  input.value = '';
  resetInputHeight();

  // user 消息补全字段（与 assistant 一致），避免模板访问 undefined 崩溃
  messages.value.push({
    role: 'user',
    text,
    thinking: '',
    thinkingOpen: false,
    toolCalls: [],
    meta: null,
    streaming: false,
    error: '',
  });
  messages.value.push({
    role: 'assistant',
    text: '',
    thinking: '',
    thinkingOpen: false, // 思考过程默认折叠（点击标题可展开）
    toolCalls: [],
    meta: null,
    streaming: true,
    error: '',
  });
  // 注意：必须取 reactive 代理（直接改原始对象不触发视图更新）
  const aiMsg = messages.value[messages.value.length - 1];
  scrollToBottom();

  sending.value = true;
  try {
    const sid = await ensureSession();
    aborter = sendChatMessageStream(sid, text, (ev, data) => {
      if (ev === 'text') {
        aiMsg.text += data.text;
      } else if (ev === 'thinking') {
        aiMsg.thinking += data.text;
      } else if (ev === 'tool_use') {
        aiMsg.toolCalls.push({ name: data.name, input: data.input });
      } else if (ev === 'result') {
        aiMsg.meta = data;
        if (data.is_error) aiMsg.error = (data.errors || []).join('; ');
      } else if (ev === 'error') {
        aiMsg.error = friendlyError(data.error);
      } else if (ev === 'done') {
        aiMsg.streaming = false;
        aiMsg.thinkingOpen = false; // 完成后收起思考过程（可点开回看）
        sending.value = false;
        aborter = null;
      }
      scrollToBottom();
    });
  } catch (e) {
    aiMsg.error = friendlyError(e.message || '会话创建失败');
    aiMsg.streaming = false;
    sending.value = false;
  }
}

async function stop() {
  if (sessionId.value) {
    try {
      await interruptChatSession(sessionId.value);
    } catch {
      /* ignore */
    }
  }
  if (aborter) {
    aborter.abort();
    aborter = null;
  }
  sending.value = false;
  const last = messages.value[messages.value.length - 1];
  if (last && last.streaming) last.streaming = false;
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    send();
  }
}

// textarea 自动增高
function autoResize() {
  const el = inputEl.value;
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 140) + 'px';
}
function resetInputHeight() {
  nextTick(() => {
    if (inputEl.value) inputEl.value.style.height = 'auto';
  });
}

const canSend = computed(() => !sending.value && !!input.value.trim());

function fmtMs(ms) {
  if (ms == null) return '-';
  return ms >= 1000 ? (ms / 1000).toFixed(1) + ' 秒' : ms + 'ms';
}

onBeforeUnmount(() => {
  if (aborter) aborter.abort();
  if (sessionId.value) closeChatSession(sessionId.value).catch(() => {});
});
</script>

<template>
  <div class="chat-view">
    <!-- 顶栏：标题 + 模型 + 新对话（仅此三项，无其他配置） -->
    <div class="chat-top">
      <div class="chat-title">
        <span class="chat-logo">🤖</span>
        <span class="chat-name">AI 对话</span>
        <span v-if="sessionModel" class="chat-model-tag">{{ sessionModel }}</span>
      </div>
      <div class="chat-top-actions">
        <select
          v-model="modelChoice"
          class="model-select"
          title="选择模型（切换模型将开启新对话）"
          @change="onModelChange"
        >
          <option value="">默认模型{{ defaultModel ? `（${defaultModel}）` : '' }}</option>
          <option v-for="m in availableModels" :key="m" :value="m">{{ m }}</option>
        </select>
        <button class="top-btn cwd-btn" :class="{ active: selectedCwd }" title="选择 AI 可访问的工作目录（切换将开启新对话）" @click="openCwdDialog">
          📁 {{ cwdLabel }}
        </button>
        <button class="top-btn" :disabled="!sessionId && !messages.length" @click="newChat">
          ＋ 新对话
        </button>
      </div>
    </div>

    <!-- 消息区 -->
    <div class="chat-scroll" ref="scrollBox">
      <!-- 空状态：欢迎 + 快捷提问 -->
      <div v-if="!messages.length" class="chat-welcome">
        <div class="welcome-icon">💬</div>
        <div class="welcome-title">开始新对话</div>
        <div class="welcome-desc">支持多轮上下文 · 思考过程 · 联网搜索，直接输入或点击下方问题开始</div>
        <div class="welcome-tips">
          <button v-for="t in QUICK_TIPS" :key="t" class="tip-btn" @click="send(t)">
            {{ t }}
          </button>
        </div>
      </div>

      <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.role">
        <div class="msg-avatar">{{ m.role === 'user' ? '我' : 'AI' }}</div>
        <div class="msg-bubble">
          <!-- 思考过程（可折叠，生成中自动展开） -->
          <div v-if="m.thinking" class="msg-thinking">
            <button class="think-toggle" @click="m.thinkingOpen = !m.thinkingOpen">
              💭 思考过程{{ m.streaming ? '（进行中…）' : '' }} {{ m.thinkingOpen ? '▾' : '▸' }}
            </button>
            <pre v-show="m.thinkingOpen" class="think-body">{{ m.thinking }}</pre>
          </div>

          <!-- 工具调用（简洁 chip，悬浮看参数） -->
          <div v-if="m.toolCalls && m.toolCalls.length" class="msg-tools">
            <span
              v-for="(t, ti) in m.toolCalls"
              :key="ti"
              class="tool-chip"
              :title="JSON.stringify(t.input)"
            >
              🔧 {{ toolLabel(t.name) }}
            </span>
          </div>

          <!-- 正文（Markdown 渲染） -->
          <div v-if="m.text" class="msg-text md" v-html="renderMarkdown(m.text)"></div>

          <!-- 等待第一段输出 -->
          <div v-if="m.streaming && !m.text && !m.thinking" class="msg-waiting">
            <span class="dot"></span><span class="dot"></span><span class="dot"></span>
          </div>

          <!-- 错误 -->
          <div v-if="m.error" class="msg-error">{{ m.error }}</div>

          <!-- 汇总 -->
          <div v-if="m.meta && !m.meta.is_error && !m.streaming" class="msg-meta">
            耗时 {{ fmtMs(m.meta.duration_ms) }} · {{ m.meta.num_turns }} 轮
          </div>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="chat-input-area">
      <textarea
        ref="inputEl"
        v-model="input"
        class="chat-input"
        rows="1"
        placeholder="输入消息，Enter 发送 · Shift+Enter 换行"
        @keydown="handleKeydown"
        @input="autoResize"
      ></textarea>
      <button v-if="sending" class="send-btn stop" @click="stop">■ 停止</button>
      <button v-else class="send-btn" :disabled="!canSend" @click="send()">发送</button>
    </div>

    <!-- 工作目录选择弹窗（把文件夹交给 AI：会话绑定 cwd，AI 可读取/检索该目录） -->
    <div v-if="cwdOpen" class="cwd-mask" @click.self="cwdOpen = false">
      <div class="cwd-dialog">
        <div class="cwd-head">
          <span class="cwd-title">选择 AI 工作目录</span>
          <button class="cwd-close" @click="cwdOpen = false">✕</button>
        </div>
        <div class="cwd-tip">
          选中的文件夹会作为会话工作目录，AI 可读取 / 检索其中文件（只读）。切换目录将开启新对话。
        </div>
        <div class="cwd-path-bar">
          <button class="cwd-nav" :disabled="!cwdParent" @click="browseDirs(cwdParent)">⬆ 上级</button>
          <button class="cwd-nav" @click="browseDirs('')">🏠 家目录</button>
          <span class="cwd-path" :title="cwdPath">{{ cwdPath }}</span>
        </div>
        <div v-if="cwdError" class="cwd-error">⚠ {{ cwdError }}</div>
        <div class="cwd-list">
          <div v-if="cwdLoading" class="cwd-empty">加载中…</div>
          <div v-else-if="!cwdDirs.length" class="cwd-empty">此目录下没有子文件夹</div>
          <div
            v-for="d in cwdDirs"
            :key="d"
            class="cwd-item"
            @dblclick="browseDirs(cwdPath + '/' + d)"
            @click="selectedDir = d"
            :class="{ sel: selectedDir === d }"
          >
            <span class="cwd-item-icon">📂</span>{{ d }}
            <button class="cwd-item-open" @click.stop="browseDirs(cwdPath + '/' + d)">进入 ›</button>
          </div>
        </div>
        <div class="cwd-foot">
          <button v-if="selectedCwd" class="cwd-clear" @click="clearCwd">恢复默认目录</button>
          <button class="cwd-choose" @click="chooseCwd">✓ 用此目录（{{ cwdPath }}）</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-view {
  max-width: 860px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  height: calc(100vh - 130px);
  min-height: 480px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
}

/* ===== 顶栏 ===== */
.chat-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--card);
  flex-wrap: wrap;
}
.chat-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.chat-logo {
  font-size: 18px;
}
.chat-name {
  font-size: 15px;
  font-weight: 700;
}
.chat-model-tag {
  font-size: 11px;
  color: var(--blue);
  background: #e8f3ff;
  border-radius: 10px;
  padding: 2px 10px;
  font-family: 'SF Mono', Menlo, monospace;
}
.chat-top-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.model-select {
  font-size: 12.5px;
  color: var(--text);
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 5px 8px;
  outline: none;
  cursor: pointer;
  max-width: 180px;
}
.model-select:focus {
  border-color: var(--blue);
}
.top-btn {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-dim);
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 5px 14px;
  cursor: pointer;
  white-space: nowrap;
}
.top-btn:hover:not(:disabled) {
  color: var(--blue);
  border-color: var(--blue);
}
.top-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.cwd-btn.active {
  color: var(--blue);
  border-color: var(--blue);
  background: #e8f3ff;
}
/* ===== 工作目录弹窗 ===== */
.cwd-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}
.cwd-dialog {
  width: 560px;
  max-width: 100%;
  max-height: 80vh;
  background: var(--card, #fff);
  border-radius: 14px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.cwd-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
}
.cwd-title {
  font-size: 14px;
  font-weight: 700;
}
.cwd-close {
  background: none;
  border: none;
  font-size: 16px;
  color: var(--text-dim);
  cursor: pointer;
}
.cwd-tip {
  font-size: 12px;
  color: var(--text-dim);
  padding: 10px 18px;
  border-bottom: 1px solid var(--border);
  background: var(--card-2);
  line-height: 1.6;
}
.cwd-path-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  border-bottom: 1px solid var(--border);
}
.cwd-nav {
  font-size: 12px;
  color: var(--text-dim);
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px 10px;
  cursor: pointer;
  white-space: nowrap;
}
.cwd-nav:hover:not(:disabled) {
  color: var(--blue);
  border-color: var(--blue);
}
.cwd-nav:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.cwd-path {
  font-size: 12px;
  font-family: 'SF Mono', Menlo, monospace;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.cwd-error {
  color: #dc2626;
  font-size: 12.5px;
  padding: 8px 18px;
}
.cwd-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 12px;
  min-height: 200px;
}
.cwd-empty {
  color: var(--text-dim);
  font-size: 12.5px;
  text-align: center;
  padding: 40px 0;
}
.cwd-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  padding: 7px 10px;
  border-radius: 8px;
  cursor: pointer;
  user-select: none;
}
.cwd-item:hover {
  background: #f5faff;
}
.cwd-item.sel {
  background: #e8f3ff;
  color: var(--blue);
}
.cwd-item-icon {
  font-size: 14px;
}
.cwd-item-open {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-dim);
  background: none;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 2px 8px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s;
}
.cwd-item:hover .cwd-item-open {
  opacity: 1;
}
.cwd-item-open:hover {
  color: var(--blue);
  border-color: var(--blue);
}
.cwd-foot {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  padding: 12px 18px;
  border-top: 1px solid var(--border);
}
.cwd-clear {
  font-size: 12.5px;
  color: var(--text-dim);
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 7px 14px;
  cursor: pointer;
}
.cwd-choose {
  font-size: 12.5px;
  font-weight: 600;
  color: #fff;
  background: var(--blue);
  border: none;
  border-radius: 10px;
  padding: 7px 16px;
  cursor: pointer;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cwd-choose:hover {
  filter: brightness(1.08);
}

/* ===== 消息区 ===== */
.chat-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 18px 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* 空状态 */
.chat-welcome {
  margin: auto;
  text-align: center;
  padding: 30px 20px;
}
.welcome-icon {
  font-size: 40px;
  margin-bottom: 12px;
}
.welcome-title {
  font-size: 17px;
  font-weight: 700;
  margin-bottom: 6px;
}
.welcome-desc {
  font-size: 12.5px;
  color: var(--text-dim);
  margin-bottom: 20px;
}
.welcome-tips {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 460px;
  margin: 0 auto;
}
.tip-btn {
  font-size: 12.5px;
  color: var(--text);
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 9px 14px;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s;
}
.tip-btn:hover {
  border-color: var(--blue);
  color: var(--blue);
  background: #e8f3ff;
}

/* 消息行 */
.msg-row {
  display: flex;
  gap: 10px;
}
.msg-row.user {
  flex-direction: row-reverse; /* 用户消息靠右 */
}
.msg-avatar {
  flex: 0 0 auto;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  background: var(--blue);
}
.msg-row.assistant .msg-avatar {
  background: var(--gold);
}
.msg-bubble {
  flex: 1;
  min-width: 0;
  max-width: 86%;
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px 14px;
}
.msg-row.user .msg-bubble {
  background: #e8f3ff;
  border-color: #bcd9f7;
}
.msg-row.user .msg-text {
  white-space: pre-wrap;
  font-size: 13.5px;
  line-height: 1.6;
  word-break: break-word;
}

/* 思考过程 */
.msg-thinking {
  margin-bottom: 8px;
  border-radius: 8px;
  background: #fbfaf5;
  border: 1px solid #eee0b8;
  overflow: hidden;
}
.think-toggle {
  width: 100%;
  text-align: left;
  font-size: 12px;
  color: #a3862d;
  padding: 6px 10px;
  cursor: pointer;
  font-weight: 600;
  background: none;
  border: none;
}
.think-body {
  font-size: 11.5px;
  color: #8b7a3f;
  padding: 0 10px 10px;
  white-space: pre-wrap;
  line-height: 1.6;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
}

/* 工具调用 */
.msg-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-bottom: 8px;
}
.tool-chip {
  font-size: 11px;
  color: #b45309;
  background: #fef3c7;
  border-radius: 10px;
  padding: 2px 9px;
  cursor: default;
  white-space: nowrap;
}

/* 等待动画 */
.msg-waiting {
  display: inline-flex;
  gap: 4px;
  padding: 6px 0;
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--blue);
  animation: dot-jump 1.2s infinite;
}
.dot:nth-child(2) {
  animation-delay: 0.15s;
}
.dot:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes dot-jump {
  0%,
  60%,
  100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  30% {
    transform: translateY(-4px);
    opacity: 1;
  }
}

.msg-error {
  color: var(--red);
  font-size: 12.5px;
  margin-top: 6px;
  white-space: pre-wrap;
}
.msg-meta {
  margin-top: 8px;
  font-size: 11px;
  color: var(--text-dim);
  text-align: right;
}

/* ===== 输入区 ===== */
.chat-input-area {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  background: var(--card);
}
.chat-input {
  flex: 1;
  padding: 10px 14px;
  font-size: 13.5px;
  font-family: inherit;
  color: var(--text);
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: 12px;
  resize: none;
  outline: none;
  line-height: 1.5;
  max-height: 140px;
  overflow-y: auto;
}
.chat-input:focus {
  border-color: var(--blue);
}
.send-btn {
  flex: 0 0 auto;
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  background: var(--blue);
  border: none;
  border-radius: 12px;
  padding: 10px 20px;
  cursor: pointer;
  transition: all 0.15s;
}
.send-btn:hover:not(:disabled) {
  filter: brightness(1.08);
}
.send-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.send-btn.stop {
  background: #dc2626;
}

/* ===== AI 正文 Markdown ===== */
.md :deep(h3) {
  font-size: 14.5px;
  margin: 12px 0 5px;
}
.md :deep(h4) {
  font-size: 13.5px;
  margin: 10px 0 4px;
}
.md :deep(p) {
  margin: 5px 0;
  font-size: 13.5px;
  line-height: 1.7;
}
.md :deep(ul),
.md :deep(ol) {
  margin: 5px 0;
  padding-left: 18px;
}
.md :deep(li) {
  font-size: 13.5px;
  line-height: 1.7;
  margin: 2px 0;
}
.md :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
  width: 100%;
  font-size: 12.5px;
  background: #fff;
}
.md :deep(th),
.md :deep(td) {
  border: 1px solid var(--border);
  padding: 4px 8px;
  text-align: left;
}
.md :deep(th) {
  background: var(--card-2);
}
.md :deep(code) {
  background: #fff;
  border: 1px solid var(--border);
  padding: 0 4px;
  border-radius: 4px;
  font-size: 12px;
}
.md :deep(pre) {
  background: #fff;
  border: 1px solid var(--border);
  padding: 10px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 12px;
  margin: 8px 0;
}
.md :deep(blockquote) {
  border-left: 3px solid var(--blue);
  padding: 2px 10px;
  margin: 6px 0;
  color: var(--text-dim);
}
.md :deep(hr) {
  border: none;
  border-top: 1px solid var(--border);
  margin: 10px 0;
}
.md :deep(a) {
  color: var(--blue);
}
</style>
