<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { fetchTelegraph, fetchTelegraphDates, fetchTelegraphHistory, exportDocPdf } from '../api.js';

// 财联社电报页：实时拉取（后端调 scripts/cls_telegraph.py，60s 缓存）
const CATEGORIES = [
  { value: '', label: '全部' },
  { value: 'red', label: '重要' },
  { value: 'announcement', label: '公告' },
  { value: 'watch', label: '盘中观察' },
  { value: 'hk_us', label: '港美股' },
  { value: 'fund', label: '基金' },
  { value: 'remind', label: '提醒' },
];

const category = ref('');
const items = ref([]);
const loading = ref(false);
const loadingMore = ref(false);
const error = ref('');
const autoRefresh = ref(false);
const lastUpdated = ref('');
let timer = null;

// 本地缓存（data/telegraph/ 按天落盘）：historyDate 为空 = 实时模式
const historyDates = ref([]);
const historyDate = ref('');

// 多选导出：id -> 完整电报对象（跨分类/历史保留选择）
const selectedMap = ref(new Map());
const pdfExporting = ref(false);

function toggleSelect(it) {
  const m = new Map(selectedMap.value);
  if (m.has(it.id)) m.delete(it.id);
  else m.set(it.id, it);
  selectedMap.value = m;
}
function selectAll() {
  const m = new Map(selectedMap.value);
  for (const it of items.value) m.set(it.id, it);
  selectedMap.value = m;
}
function clearSelect() {
  selectedMap.value = new Map();
}
const selectedCount = computed(() => selectedMap.value.size);
const selectedItems = computed(() =>
  [...selectedMap.value.values()].sort((a, b) => b.ctime - a.ctime)
);
const allSelected = computed(
  () => items.value.length > 0 && items.value.every((i) => selectedMap.value.has(i.id))
);
const someSelected = computed(
  () => !allSelected.value && items.value.some((i) => selectedMap.value.has(i.id))
);

function stockText(it) {
  return it.stocks
    .map((s) => `${s.name}${s.change_pct != null ? ' ' + fmtPct(s.change_pct) : ''}`)
    .join('、');
}

// 生成导出用 Markdown（MD 与 PDF 共用，完整正文不截断）
function buildMd(list) {
  const lines = [];
  for (const it of list) {
    lines.push(`## ${it.level === 'A' ? '⭐ ' : ''}[${fmtTime(it.ctime)}] ${it.title || (it.brief || '').slice(0, 40)}`);
    lines.push('');
    lines.push(it.content || it.brief || '');
    if (it.stocks.length) lines.push('', `**关联个股**：${stockText(it)}`);
    if (it.plates.length) lines.push(`**相关板块**：${it.plates.join('、')}`);
    lines.push('');
  }
  return lines.join('\n');
}

// 导出 Markdown（完整正文，浏览器直接下载）
function exportMd() {
  const list = selectedItems.value;
  if (!list.length) return;
  const md = [
    '# 财联社电报导出',
    `> 共 ${list.length} 条 · 导出于 ${new Date().toLocaleString('zh-CN', { hour12: false })}`,
    '',
    buildMd(list),
  ].join('\n');
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  a.href = url;
  a.download = `财联社电报_${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

// 导出 PDF（文档模式：完整正文，标题+段落排版，不截断）
async function exportPdf() {
  const list = selectedItems.value;
  if (!list.length || pdfExporting.value) return;
  pdfExporting.value = true;
  try {
    await exportDocPdf(
      `财联社电报（${list.length} 条）`,
      buildMd(list),
      `导出于 ${new Date().toLocaleString('zh-CN', { hour12: false })}`
    );
  } catch (e) {
    error.value = e.message;
  } finally {
    pdfExporting.value = false;
  }
}

onMounted(() => {
  load();
  loadHistoryDates();
});
onBeforeUnmount(stopTimer);

async function loadHistoryDates() {
  try {
    const r = await fetchTelegraphDates();
    historyDates.value = r.dates || [];
  } catch { /* 忽略，缓存日期加载失败不影响主流程 */ }
}

async function load() {
  if (historyDate.value) return; // 历史缓存模式下不自动刷新
  loading.value = true;
  error.value = '';
  try {
    const r = await fetchTelegraph({ category: category.value, count: 50 });
    items.value = r.items || [];
    lastUpdated.value = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    restartTimer();
    loadHistoryDates(); // 实时数据已落盘，刷新缓存日期列表
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

// 向前翻页加载更早的电报
async function loadMore() {
  if (!items.value.length || loadingMore.value) return;
  loadingMore.value = true;
  try {
    const oldest = items.value[items.value.length - 1].ctime;
    const r = await fetchTelegraph({ category: category.value, count: 30, lastTime: oldest });
    const seen = new Set(items.value.map((i) => i.id));
    const fresh = (r.items || []).filter((i) => !seen.has(i.id));
    items.value = [...items.value, ...fresh];
  } catch (e) {
    error.value = e.message;
  } finally {
    loadingMore.value = false;
  }
  loadHistoryDates(); // 翻页数据也已落盘，可能产生新的缓存日期
}

// 查看某天的本地缓存
async function viewHistory(d) {
  if (historyDate.value === d) return;
  historyDate.value = d;
  loading.value = true;
  error.value = '';
  try {
    const r = await fetchTelegraphHistory(d);
    items.value = r.items || [];
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

// 返回实时模式
function backToLive() {
  historyDate.value = '';
  load();
}

function switchCategory(c) {
  if (category.value === c) return;
  category.value = c;
  historyDate.value = '';
  load();
}

function restartTimer() {
  stopTimer();
  if (autoRefresh.value) timer = setInterval(load, 60 * 1000);
}
function stopTimer() {
  if (timer) { clearInterval(timer); timer = null; }
}
function toggleAuto() {
  autoRefresh.value = !autoRefresh.value;
  restartTimer();
}

// 时间格式化：始终显示 月-日 时:分
function fmtTime(ctime) {
  const d = new Date(ctime * 1000);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const mi = String(d.getMinutes()).padStart(2, '0');
  return `${mm}-${dd} ${hh}:${mi}`;
}
function isToday(ctime) {
  return new Date(ctime * 1000).toDateString() === new Date().toDateString();
}
function fmtReading(n) {
  if (n == null) return '';
  if (n >= 10000) return (n / 10000).toFixed(1) + '万';
  return String(n);
}
function fmtPct(v) {
  if (v == null) return '';
  return (v > 0 ? '+' : '') + v.toFixed(2) + '%';
}

// 正文：优先 content（完整文本，brief 被接口截断在 300 字）
const TEXT_LIMIT = 300;
const expanded = ref(new Set());
function textOf(it) {
  return it.content || it.brief || '';
}
function isLong(it) {
  return textOf(it).length > TEXT_LIMIT;
}
function displayText(it) {
  const t = textOf(it);
  if (isLong(it) && !expanded.value.has(it.id)) return t.slice(0, TEXT_LIMIT) + '…';
  return t;
}
function toggleExpand(id) {
  const s = new Set(expanded.value);
  if (s.has(id)) s.delete(id);
  else s.add(id);
  expanded.value = s;
}

const levelACount = computed(() => items.value.filter((i) => i.level === 'A').length);
</script>

<template>
  <div>
    <div class="panel">
      <h2>
        财联社电报
        <span class="tg-sub" v-if="historyDate">📖 查看 {{ historyDate.slice(4, 6) }}-{{ historyDate.slice(6, 8) }} 本地缓存（data/telegraph/）</span>
        <span class="tg-sub" v-else-if="lastUpdated">更新于 {{ lastUpdated }} · 实时拉取并自动缓存到 data/telegraph/</span>
      </h2>

      <!-- 分类切换 -->
      <div class="stock-tabs" style="margin-bottom: 12px">
        <button
          v-for="c in CATEGORIES"
          :key="c.value"
          :class="{ active: category === c.value }"
          @click="switchCategory(c.value)"
        >
          {{ c.label }}
        </button>
        <button class="tg-refresh" @click="load" :disabled="loading">⟳ 刷新</button>
        <button class="tg-refresh" :class="{ on: autoRefresh }" @click="toggleAuto">
          {{ autoRefresh ? '● 自动刷新中(60s)' : '○ 自动刷新' }}
        </button>
        <span class="tg-stat" v-if="!loading && !error">
          {{ items.length }} 条<template v-if="category === ''"> · 重要 {{ levelACount }} 条</template>
        </span>
      </div>

      <!-- 本地缓存日期（按天回看已加载过的电报） -->
      <div class="tg-history" v-if="historyDates.length">
        <span class="tg-history-label">本地缓存</span>
        <button
          v-for="d in historyDates"
          :key="d"
          class="date-tab"
          :class="{ active: historyDate === d }"
          @click="viewHistory(d)"
        >
          {{ d.slice(4, 6) }}-{{ d.slice(6, 8) }}
        </button>
        <button v-if="historyDate" class="tg-refresh" @click="backToLive">↩ 返回实时</button>
      </div>

      <!-- 多选 + 导出工具栏 -->
      <div class="tg-select-bar" v-if="items.length">
        <label class="tg-check-label">
          <input
            type="checkbox"
            class="tg-check"
            :checked="allSelected"
            :indeterminate.prop="someSelected"
            @change="allSelected ? clearSelect() : selectAll()"
          />
          全选本列表
        </label>
        <span class="tg-sel-count">已选 {{ selectedCount }} 条</span>
        <button class="tg-refresh" @click="selectAll">全选</button>
        <button class="tg-refresh" @click="clearSelect" :disabled="!selectedCount">清空选择</button>
        <button class="tg-refresh tg-export" @click="exportMd" :disabled="!selectedCount">⬇ 导出 Markdown</button>
        <button class="tg-refresh tg-export" @click="exportPdf" :disabled="!selectedCount || pdfExporting">
          {{ pdfExporting ? '导出中…' : '⬇ 导出 PDF' }}
        </button>
      </div>

      <div v-if="loading" class="loading">加载中…</div>
      <div v-else-if="error" class="error">⚠ {{ error }}</div>
      <div v-else-if="!items.length" class="empty">暂无电报</div>

      <!-- 电报列表 -->
      <div v-else class="tg-list">
        <div
          v-for="it in items"
          :key="it.id"
          class="tg-item"
          :class="{ 'tg-red': it.level === 'A', 'tg-not-today': !isToday(it.ctime), 'tg-picked': selectedMap.has(it.id) }"
        >
          <input
            type="checkbox"
            class="tg-check"
            :checked="selectedMap.has(it.id)"
            @change="toggleSelect(it)"
          />
          <div class="tg-time">{{ fmtTime(it.ctime) }}</div>
          <div class="tg-body">
            <div class="tg-title" v-if="it.title">{{ it.title }}</div>
            <div class="tg-brief">
              {{ displayText(it) }}<span
                v-if="isLong(it)"
                class="tg-expand"
                @click="toggleExpand(it.id)"
              >{{ expanded.has(it.id) ? '收起' : '展开全文' }}</span>
            </div>
            <div class="tg-foot" v-if="it.stocks.length || it.plates.length || it.reading_num != null">
              <span v-for="s in it.stocks" :key="s.id" class="tg-stock">
                {{ s.name }}
                <b v-if="s.change_pct != null" :class="s.change_pct >= 0 ? 'up' : 'down'">{{ fmtPct(s.change_pct) }}</b>
              </span>
              <span v-for="p in it.plates" :key="p" class="tg-plate">{{ p }}</span>
              <span v-if="it.reading_num != null" class="tg-reading">👁 {{ fmtReading(it.reading_num) }}</span>
            </div>
          </div>
        </div>

        <button v-if="!historyDate" class="tg-more" @click="loadMore" :disabled="loadingMore">
          {{ loadingMore ? '加载中…' : '加载更早的电报' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tg-sub {
  font-size: 12px;
  color: var(--text-dim);
  font-weight: 400;
  margin-left: 10px;
}
.tg-refresh {
  margin-left: 8px;
}
.tg-refresh.on {
  color: #dc2626;
  border-color: #dc2626;
}
.tg-stat {
  font-size: 12px;
  color: var(--text-dim);
  align-self: center;
  margin-left: 4px;
}
.tg-history {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 10px;
  background: var(--card-2);
  border-radius: 8px;
}
.tg-history-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-dim);
}

/* 多选 + 导出工具栏 */
.tg-select-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 10px;
  background: var(--card-2);
  border-radius: 8px;
}
.tg-check-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text);
  cursor: pointer;
  user-select: none;
}
.tg-check {
  width: 15px;
  height: 15px;
  cursor: pointer;
  accent-color: var(--blue);
  flex: 0 0 auto;
  align-self: center;
}
.tg-sel-count {
  font-size: 12px;
  font-weight: 600;
  color: var(--blue);
  margin: 0 4px 0 8px;
}
.tg-export {
  color: #7c3aed;
  border-color: #e9d5ff;
  background: #f5f3ff;
}
.tg-export:hover:not(:disabled) {
  background: #7c3aed;
  color: #fff;
  border-color: #7c3aed;
}
.tg-export:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.tg-item.tg-picked {
  background: #f5f3ff;
}
.tg-item.tg-picked:hover {
  background: #ede9fe;
}
.tg-list {
  max-height: calc(100vh - 220px);
  overflow-y: auto;
  padding-right: 4px;
}
.tg-item {
  display: flex;
  gap: 14px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  border-radius: 8px;
  transition: background 0.12s;
}
.tg-item:hover {
  background: var(--card-2);
}
.tg-item.tg-not-today {
  opacity: 0.75;
}
.tg-time {
  flex: 0 0 104px;
  font-size: 12.5px;
  color: var(--text-dim);
  font-variant-numeric: tabular-nums;
  padding-top: 2px;
}
.tg-body {
  flex: 1;
  min-width: 0;
}
.tg-red .tg-title,
.tg-red .tg-brief {
  color: #dc2626;
  font-weight: 600;
}
.tg-title {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 3px;
  line-height: 1.5;
}
.tg-brief {
  font-size: 13px;
  color: var(--text);
  line-height: 1.7;
  word-break: break-all;
}
.tg-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}
.tg-stock {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  background: #fff5f5;
  border: 1px solid #fecaca;
  color: #b91c1c;
  border-radius: 6px;
  padding: 1px 8px;
}
.tg-plate {
  font-size: 12px;
  font-weight: 600;
  color: #3a6ea5;
  background: #e0efff;
  border: 1px solid #bcd9f7;
  border-radius: 6px;
  padding: 1px 8px;
}
.tg-reading {
  margin-left: auto;
  font-size: 11.5px;
  color: var(--text-dim);
}
.tg-expand {
  display: inline-block;
  margin-left: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--blue);
  cursor: pointer;
  white-space: nowrap;
}
.tg-expand:hover {
  text-decoration: underline;
}
.tg-more {
  display: block;
  width: 100%;
  margin-top: 12px;
  padding: 10px;
  font-size: 13px;
  color: var(--blue);
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}
.tg-more:hover:not(:disabled) {
  border-color: var(--blue);
  background: #e8f3ff;
}
.tg-more:disabled {
  opacity: 0.5;
  cursor: wait;
}
</style>
