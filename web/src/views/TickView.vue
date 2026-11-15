<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { fetchTickDates, streamTickFetch, streamTickFetchGroups } from '../api.js';
import TickChartPanel from './TickChartPanel.vue';

// 分时数据页：① 下载区 ② 多图表面板（每面板独立日期选择，可对比不同日期）
// 面板组件 TickChartPanel.vue 自包含：日期下拉/分组折叠拖拽/股票勾选/ECharts 绘图

// ===== 下载区 =====
const fetchCodes = ref('');
const fetchDate = ref(new Date().toISOString().slice(0, 10).replace(/-/g, '')); // 默认今天
const fetchMode = ref('auto');
const fetchForce = ref(false);
const fetching = ref(false);
const fetchProgress = ref([]);
const fetchStatus = ref('');
let fetchAborter = null;

// ===== 题材 JSON 分组下载 =====
const groupJson = ref('');
const groupError = ref('');
const parsedGroups = ref(null);

// ===== 下载进度 =====
const progressOpen = ref(false);
const fetchTotal = ref(0);
const fetchDone = ref(0);
const progressMap = ref(new Map());

const fetchPercent = computed(() => (fetchTotal.value ? Math.round((fetchDone.value / fetchTotal.value) * 100) : 0));
const fetchOkCount = computed(() => [...progressMap.value.values()].filter((r) => r.status === 'ok').length);
const fetchSkipCount = computed(() => [...progressMap.value.values()].filter((r) => r.status === 'skipped').length);
const fetchErrCount = computed(() => [...progressMap.value.values()].filter((r) => r.status === 'err').length);
const progressByGroup = computed(() => {
  const m = new Map();
  for (const r of progressMap.value.values()) {
    if (!m.has(r.group)) m.set(r.group, []);
    m.get(r.group).push(r);
  }
  return [...m.entries()].map(([group, items]) => ({ group, items }));
});

function parseCodes() {
  return fetchCodes.value
    .split(/[,，\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function parseGroupJson() {
  groupError.value = '';
  parsedGroups.value = null;
  const text = groupJson.value.trim();
  if (!text) return;
  let obj;
  try {
    obj = JSON.parse(text);
  } catch (e) {
    groupError.value = 'JSON 解析失败：' + e.message;
    return;
  }
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
    groupError.value = '格式需为对象：{ "题材名": { "股票代码": "名称" } }';
    return;
  }
  let total = 0;
  for (const [g, m] of Object.entries(obj)) {
    if (!m || typeof m !== 'object' || Array.isArray(m)) {
      groupError.value = `题材「${g}」的值需为对象 { "股票代码": "名称" }`;
      return;
    }
    total += Object.keys(m).length;
  }
  if (!total) {
    groupError.value = 'JSON 中没有股票';
    return;
  }
  parsedGroups.value = obj;
}

function initProgress(items) {
  const m = new Map();
  for (const it of items) {
    m.set(`${it.group}|${it.code}`, { code: it.code, name: it.name || it.code, group: it.group, status: 'pending' });
  }
  progressMap.value = m;
  fetchTotal.value = items.length;
  fetchDone.value = 0;
}

// ===== 进度持久化（localStorage） =====
const PROGRESS_KEY = 'tick_fetch_progress';

function saveProgress() {
  try {
    localStorage.setItem(PROGRESS_KEY, JSON.stringify({
      date: fetchDate.value,
      status: fetchStatus.value,
      running: fetching.value,
      total: fetchTotal.value,
      done: fetchDone.value,
      items: [...progressMap.value.values()],
      savedAt: Date.now(),
    }));
  } catch { /* ignore */ }
}

function restoreProgress() {
  try {
    const s = localStorage.getItem(PROGRESS_KEY);
    if (!s) return;
    const p = JSON.parse(s);
    if (!p || !Array.isArray(p.items) || !p.items.length) return;
    const m = new Map();
    for (const it of p.items) {
      if (p.running === false && it.status === 'pending') it.status = 'aborted';
      m.set(`${it.group}|${it.code}`, it);
    }
    progressMap.value = m;
    fetchTotal.value = p.total || p.items.length;
    fetchDone.value = p.done || 0;
    fetchDate.value = p.date || fetchDate.value;
    fetchStatus.value = p.status || '';
    if (p.running) {
      fetchStatus.value = '上次下载因页面刷新中断，可点「继续下载」断点续传';
      for (const it of m.values()) if (it.status === 'pending') it.status = 'aborted';
    }
  } catch { /* ignore */ }
}

let progressSaveTimer = null;
function scheduleSaveProgress() {
  clearTimeout(progressSaveTimer);
  progressSaveTimer = setTimeout(saveProgress, 300);
}

function markProgress(data) {
  const status = data.skipped ? 'skipped' : data.ok ? 'ok' : 'err';
  const key = `${data.group || ''}|${data.code}`;
  const r = progressMap.value.get(key);
  if (r) {
    r.status = status;
    if (data.file) r.file = data.file;
    if (data.error) r.error = data.error;
  } else {
    progressMap.value.set(key, {
      code: data.code, name: data.code, group: data.group || '',
      status, file: data.file, error: data.error,
    });
  }
  fetchDone.value = Math.min(fetchDone.value + 1, fetchTotal.value);
}

function expandGroups(groups) {
  const items = [];
  for (const [group, m] of Object.entries(groups)) {
    for (const [code, name] of Object.entries(m)) items.push({ code, name, group });
  }
  return items;
}

function onFetchProgress(ev, data) {
  if (ev === 'status') {
    fetchStatus.value = data.message || fetchStatus.value;
  } else if (ev === 'progress') {
    fetchProgress.value.push(data);
    markProgress(data);
    fetchStatus.value = `已完成 ${fetchDone.value}/${fetchTotal.value || data.total}：${data.code} ${data.ok ? '✓' : '✗'}`;
    scheduleSaveProgress();
  } else if (ev === 'done') {
    fetching.value = false;
    const skip = data.skipped ? `，跳过已存在 ${data.skipped}` : '';
    fetchStatus.value = `下载完成：成功 ${data.ok}/${fetchProgress.value.length}${skip}`;
    saveProgress();
    refreshKey.value++;
    loadDates();
  } else if (ev === 'error') {
    fetching.value = false;
    fetchStatus.value = '下载失败：' + (data.error || '未知错误');
    saveProgress();
  }
}

function startFetch() {
  const codes = parseCodes();
  if (!codes.length || fetching.value) return;
  if (!/^\d{8}$/.test(fetchDate.value)) {
    fetchStatus.value = '日期格式需为 YYYYMMDD';
    return;
  }
  initProgress(codes.map((c) => ({ code: c, group: '' })));
  fetching.value = true;
  fetchProgress.value = [];
  fetchStatus.value = `正在下载 ${codes.length} 只股票…`;
  fetchAborter = streamTickFetch(codes, fetchDate.value, fetchMode.value, onFetchProgress, fetchForce.value);
}

function startGroupFetch() {
  if (!parsedGroups.value || fetching.value) return;
  if (!/^\d{8}$/.test(fetchDate.value)) {
    fetchStatus.value = '日期格式需为 YYYYMMDD';
    return;
  }
  const items = expandGroups(parsedGroups.value);
  initProgress(items);
  fetching.value = true;
  fetchProgress.value = [];
  fetchStatus.value = `正在按题材下载 ${items.length} 只股票…`;
  fetchAborter = streamTickFetchGroups(parsedGroups.value, fetchDate.value, fetchMode.value, onFetchProgress, fetchForce.value);
}

function stopFetch() {
  if (fetchAborter) fetchAborter.abort();
  fetchAborter = null;
  fetching.value = false;
  for (const r of progressMap.value.values()) {
    if (r.status === 'pending') r.status = 'aborted';
  }
  fetchStatus.value = '已停止，未完成的可点「继续下载」';
  saveProgress();
}

const pendingCount = computed(
  () => [...progressMap.value.values()].filter((r) => r.status === 'pending' || r.status === 'aborted').length
);

function resumeFetch() {
  if (fetching.value || !pendingCount.value) return;
  if (!/^\d{8}$/.test(fetchDate.value)) {
    fetchStatus.value = '日期格式需为 YYYYMMDD';
    return;
  }
  const all = [...progressMap.value.values()];
  const pending = all.filter((r) => r.status === 'pending' || r.status === 'aborted');
  const m = new Map();
  for (const r of all) {
    m.set(`${r.group}|${r.code}`, r.status === 'pending' || r.status === 'aborted' ? { ...r, status: 'pending' } : r);
  }
  progressMap.value = m;
  fetchDone.value = all.length - pending.length;
  const groups = {};
  for (const r of pending) {
    (groups[r.group || ''] ||= {})[r.code] = r.name;
  }
  fetching.value = true;
  fetchProgress.value = [];
  fetchStatus.value = `继续下载 ${pending.length} 只…`;
  fetchAborter = streamTickFetchGroups(groups, fetchDate.value, fetchMode.value, onFetchProgress, fetchForce.value);
}

function clearTask() {
  if (fetchAborter) {
    fetchAborter.abort();
    fetchAborter = null;
  }
  fetching.value = false;
  progressMap.value = new Map();
  fetchTotal.value = 0;
  fetchDone.value = 0;
  fetchProgress.value = [];
  fetchStatus.value = '';
  try {
    localStorage.removeItem(PROGRESS_KEY);
  } catch { /* ignore */ }
}

// ===== 可用日期（下载完成/刷新时更新，传给所有面板） =====
const dates = ref([]);
const refreshKey = ref(0);

async function loadDates() {
  try {
    const r = await fetchTickDates();
    dates.value = r.dates || [];
  } catch (e) {
    console.warn('加载分时日期失败:', e);
  }
}

// ===== 图表面板列表（可增删，每个独立选日期对比） =====
const panels = ref([{ id: 1 }]);
let panelSeq = 1;

function addPanel() {
  panelSeq += 1;
  panels.value.push({ id: panelSeq });
}
function removePanel(id) {
  panels.value = panels.value.filter((p) => p.id !== id);
}

onMounted(() => {
  restoreProgress();
  loadDates();
});

onUnmounted(() => {
  fetchAborter && fetchAborter.abort();
});
</script>

<template>
  <div>
    <!-- ① 下载区 -->
    <div class="panel">
      <h2>下载分时/分笔数据</h2>
      <div class="tk-fetch-bar">
        <input v-model="fetchCodes" class="search tk-codes" placeholder="股票代码，逗号分隔：605179, sz000560, 301218" :disabled="fetching" />
        <input v-model="fetchDate" class="search tk-date" placeholder="日期 20260901" :disabled="fetching" />
        <select v-model="fetchMode" class="tk-select" :disabled="fetching">
          <option value="auto">自动（当日→分笔+分钟线都下，历史→仅分钟线）</option>
          <option value="ticks">仅分笔成交（仅最新交易日）</option>
          <option value="minute">仅分钟线（近约10个交易日）</option>
        </select>
        <button v-if="!fetching" class="tk-btn" :disabled="!parseCodes().length" @click="startFetch">⬇ 下载</button>
        <button v-else class="tk-btn stop" @click="stopFetch">■ 停止</button>
        <label class="tk-force" title="已下载的也重新拉取（用于补充昨收等新字段，或数据有更新时）">
          <input type="checkbox" v-model="fetchForce" :disabled="fetching" /> 强制重下
        </label>
      </div>
      <div v-if="fetchStatus" class="tk-fetch-status">{{ fetchStatus }}</div>

      <div v-if="fetchTotal" class="tk-progress-wrap">
        <div class="tk-progress-track">
          <div class="tk-progress-fill" :style="{ width: fetchPercent + '%' }"></div>
        </div>
        <span class="tk-progress-text">{{ fetchDone }}/{{ fetchTotal }}（{{ fetchPercent }}%）</span>
        <span v-if="fetchOkCount" class="tk-progress-ok">✓{{ fetchOkCount }}</span>
        <span v-if="fetchSkipCount" class="tk-progress-skip">⏭{{ fetchSkipCount }}</span>
        <span v-if="fetchErrCount" class="tk-progress-err">✗{{ fetchErrCount }}</span>
        <button v-if="!fetching && pendingCount" class="tk-btn ghost tk-detail-btn" title="只下载未完成的，已完成进度保留" @click="resumeFetch">▶ 继续下载（{{ pendingCount }}）</button>
        <button v-if="!fetching" class="tk-btn ghost tk-detail-btn tk-clear-btn" @click="clearTask">🗑 清除任务</button>
        <button class="tk-btn ghost tk-detail-btn" @click="progressOpen = true">📋 进度明细</button>
      </div>

      <div v-if="fetchProgress.length" class="tk-fetch-list">
        <div v-for="(p, pi) in fetchProgress" :key="pi" class="tk-fetch-item" :class="{ err: !p.ok, skip: p.skipped }">
          {{ p.skipped ? '⏭' : p.ok ? '✓' : '✗' }} {{ p.code }}{{ p.skipped ? '（已存在，跳过）' : '' }}<span v-if="p.group" class="tk-group-tag">{{ p.group }}</span><span v-if="p.file" class="tk-file">{{ p.file }}</span><span v-else class="tk-err">{{ p.error }}</span>
        </div>
      </div>

      <details class="tk-json-box">
        <summary>📦 按题材分组下载（JSON 输入）</summary>
        <textarea v-model="groupJson" class="tk-json-input" :disabled="fetching" placeholder='JSON：{ "题材名": { "股票代码": "名称" } }'></textarea>
        <div class="tk-json-actions">
          <button class="tk-btn ghost" @click="parseGroupJson" :disabled="fetching || !groupJson.trim()">解析预览</button>
          <button class="tk-btn" @click="startGroupFetch" :disabled="fetching || !parsedGroups">⬇ 按题材下载</button>
          <span v-if="groupError" class="tk-err">{{ groupError }}</span>
        </div>
        <div v-if="parsedGroups" class="tk-json-preview">
          <span v-for="(m, g) in parsedGroups" :key="g" class="tk-chip">{{ g }}（{{ Object.keys(m).length }} 只）</span>
          <span class="tk-hint">将存到 data/stocks_daily/{{ fetchDate }}/{题材名}/</span>
        </div>
      </details>
      <div class="tk-hint">数据保存到 data/stocks_daily/{日期}/[{题材}/] · 分笔仅支持最新交易日 · 分钟线支持近约 10 个交易日</div>
    </div>

    <!-- ② 分时数据浏览：多面板 -->
    <div class="panel">
      <div class="tk-panels-head">
        <h2>分时数据浏览</h2>
        <button class="tk-btn" @click="addPanel">＋ 新建图表</button>
        <span class="tk-hint tk-head-hint">{{ panels.length }} 个面板 · 每个面板独立选择日期，可同时对比不同交易日</span>
      </div>
      <TickChartPanel
        v-for="p in panels"
        :key="p.id"
        :dates="dates"
        :refresh-key="refreshKey"
        :closable="panels.length > 1"
        @remove="removePanel(p.id)"
      />
    </div>

    <!-- 下载进度明细弹窗 -->
    <div v-if="progressOpen" class="tk-modal-mask" @click.self="progressOpen = false">
      <div class="tk-modal">
        <div class="tk-modal-head">
          <span class="tk-modal-title">下载进度明细 · {{ fetchDate }}</span>
          <button class="tk-modal-close" @click="progressOpen = false">✕</button>
        </div>
        <div class="tk-modal-summary">
          <span>共 {{ fetchTotal }} 只</span>
          <span class="tk-progress-ok">✓ 已下载 {{ fetchOkCount }}</span>
          <span v-if="fetchSkipCount" class="tk-progress-skip">⏭ 已存在 {{ fetchSkipCount }}</span>
          <span class="tk-progress-err">✗ 失败 {{ fetchErrCount }}</span>
          <span class="tk-progress-pending">⋯ 待下载 {{ fetchTotal - fetchDone }}</span>
        </div>
        <div class="tk-modal-body">
          <div v-for="g in progressByGroup" :key="g.group || '_none'" class="tk-modal-group">
            <div class="tk-group-title">{{ g.group || '未分组' }}<span class="tk-group-count">{{ g.items.length }} 只</span></div>
            <div v-for="r in g.items" :key="r.group + r.code" class="tk-modal-item" :class="r.status">
              <span class="tk-mi-status">
                <template v-if="r.status === 'ok'">✓</template>
                <template v-else-if="r.status === 'skipped'">⏭</template>
                <template v-else-if="r.status === 'err'">✗</template>
                <template v-else-if="r.status === 'aborted'">■</template>
                <template v-else>⋯</template>
              </span>
              <span class="tk-mi-name">{{ r.name }}</span>
              <span class="tk-mi-code">{{ r.code }}</span>
              <span v-if="r.status === 'err' && r.error" class="tk-mi-err" :title="r.error">{{ r.error }}</span>
              <span v-else-if="r.status === 'ok'" class="tk-mi-ok">已下载</span>
              <span v-else-if="r.status === 'skipped'" class="tk-mi-skip" :title="r.file">已存在，未重复下载</span>
              <span v-else-if="r.status === 'aborted'" class="tk-mi-abort">已中断</span>
              <span v-else class="tk-mi-pending">待下载</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tk-fetch-bar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.tk-codes { flex: 1; min-width: 260px; }
.tk-date { width: 130px; }
.tk-select {
  font-size: 12.5px; padding: 7px 10px; border: 1px solid var(--border);
  border-radius: 8px; background: var(--card-2); color: var(--text); cursor: pointer;
}
.tk-btn {
  font-size: 12.5px; font-weight: 600; color: #fff; background: var(--blue);
  border: none; border-radius: 8px; padding: 8px 18px; cursor: pointer; white-space: nowrap;
}
.tk-btn:hover:not(:disabled) { filter: brightness(1.08); }
.tk-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.tk-btn.stop { background: #dc2626; }
.tk-btn.ghost { background: var(--card-2); color: var(--text-dim); border: 1px solid var(--border); padding: 6px 12px; }
.tk-force { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; color: var(--text-dim); cursor: pointer; user-select: none; }
.tk-fetch-status { font-size: 12.5px; color: var(--blue); margin-top: 8px; }
.tk-progress-wrap { display: flex; align-items: center; gap: 10px; margin-top: 8px; flex-wrap: wrap; }
.tk-progress-track {
  flex: 1; min-width: 160px; height: 8px; background: var(--card-2);
  border: 1px solid var(--border); border-radius: 6px; overflow: hidden;
}
.tk-progress-fill {
  height: 100%; background: linear-gradient(90deg, #1890ff, #40a9ff);
  border-radius: 6px; transition: width 0.3s ease;
}
.tk-progress-text { font-size: 12px; color: var(--text); font-variant-numeric: tabular-nums; white-space: nowrap; }
.tk-progress-ok { font-size: 12px; color: #16a34a; font-weight: 600; }
.tk-progress-skip { font-size: 12px; color: #2563eb; font-weight: 600; }
.tk-progress-err { font-size: 12px; color: #dc2626; font-weight: 600; }
.tk-progress-pending { font-size: 12px; color: var(--text-dim); }
.tk-detail-btn { padding: 4px 12px; font-size: 12px; }
.tk-clear-btn { color: #dc2626; border-color: #fecaca; }
.tk-clear-btn:hover { background: #fef2f2; }
.tk-fetch-list { margin-top: 8px; max-height: 140px; overflow-y: auto; font-size: 12px; }
.tk-fetch-item { padding: 3px 0; color: #16a34a; }
.tk-fetch-item.err { color: #dc2626; }
.tk-fetch-item.skip { color: #2563eb; }
.tk-group-tag {
  margin-left: 6px; font-size: 10px; color: #7c3aed;
  background: #f5f3ff; border: 1px solid #e9d5ff; border-radius: 8px; padding: 0 6px;
}
.tk-file { color: var(--text-dim); margin-left: 8px; font-size: 11px; word-break: break-all; }
.tk-err { margin-left: 8px; font-size: 11px; }
.tk-hint { font-size: 11.5px; color: var(--text-dim); margin-top: 8px; }
.tk-json-box { margin-top: 10px; border: 1px dashed var(--border); border-radius: 10px; padding: 8px 12px; }
.tk-json-box summary { font-size: 12.5px; color: var(--text-dim); cursor: pointer; user-select: none; }
.tk-json-input {
  width: 100%; min-height: 110px; margin-top: 8px; padding: 8px 10px;
  font-family: 'SF Mono', Menlo, monospace; font-size: 12px; line-height: 1.6;
  border: 1px solid var(--border); border-radius: 8px; background: var(--card-2);
  color: var(--text); resize: vertical; outline: none; box-sizing: border-box;
}
.tk-json-input:focus { border-color: var(--blue); }
.tk-json-actions { display: flex; gap: 8px; align-items: center; margin-top: 8px; flex-wrap: wrap; }
.tk-json-preview { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 8px; }
.tk-chip {
  display: inline-flex; align-items: center; gap: 5px; font-size: 12.5px;
  padding: 5px 12px; border: 1px solid var(--border); border-radius: 16px;
  background: var(--card-2); cursor: pointer; user-select: none;
}
.tk-panels-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.tk-panels-head h2 { margin: 0; }
.tk-head-hint { margin-top: 0; }
.tk-modal-mask {
  position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45);
  display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 20px;
}
.tk-modal {
  width: 640px; max-width: 100%; max-height: 80vh; background: var(--card, #fff);
  border-radius: 14px; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
  display: flex; flex-direction: column; overflow: hidden;
}
.tk-modal-head { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--border); }
.tk-modal-title { font-size: 14px; font-weight: 700; }
.tk-modal-close { background: none; border: none; font-size: 16px; color: var(--text-dim); cursor: pointer; padding: 2px 6px; }
.tk-modal-close:hover { color: var(--text); }
.tk-modal-summary {
  display: flex; gap: 16px; padding: 10px 18px; font-size: 12.5px; color: var(--text-dim);
  border-bottom: 1px solid var(--border); background: var(--card-2);
}
.tk-modal-body { padding: 12px 18px; overflow-y: auto; }
.tk-modal-group { margin-bottom: 12px; }
.tk-group-title { font-size: 12.5px; font-weight: 700; margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }
.tk-group-count { font-size: 11px; font-weight: 400; color: var(--text-dim); }
.tk-modal-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 12.5px; }
.tk-mi-status { width: 16px; text-align: center; font-weight: 700; }
.tk-modal-item.ok .tk-mi-status { color: #16a34a; }
.tk-modal-item.err .tk-mi-status { color: #dc2626; }
.tk-modal-item.skipped .tk-mi-status { color: #2563eb; }
.tk-modal-item.aborted .tk-mi-status { color: #b45309; }
.tk-mi-name { font-weight: 600; }
.tk-mi-code { font-size: 11px; color: var(--text-dim); font-family: 'SF Mono', Menlo, monospace; }
.tk-mi-ok { margin-left: auto; font-size: 11px; color: #16a34a; }
.tk-mi-skip { margin-left: auto; font-size: 11px; color: #2563eb; }
.tk-mi-abort { margin-left: auto; font-size: 11px; color: #b45309; }
.tk-mi-err { margin-left: auto; font-size: 11px; color: #dc2626; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tk-mi-pending { margin-left: auto; font-size: 11px; color: var(--text-dim); }
</style>
