<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { fetchLhbLive, fetchLhbDates, fetchLhbSnapshots, fetchLhbSnapshot } from '../api.js';

// 实时龙虎榜页：开盘啦盘中资金排行（scripts/fetch_lhb_realtime.py）
// 注意：不是交易所收盘后披露的正式龙虎榜，而是盘中主力净流入/涨幅/成交的实时排行（线索，不等于游资席位已买入）。
// 每次"拉取最新"都会落盘到 data/lhb_realtime/{日期}/{HHMM}.json，盘后可按时间点回看。

const mode = ref('live'); // live | snapshot
const snap = ref(null);
const loading = ref(false);
const error = ref('');
const hasCred = ref(true);

// 拉取参数
const pages = ref(1);
const useRange = ref(false);
const rStart = ref('0925');
const rEnd = ref('0930');

// 自动刷新（接口建议间隔 ≥ 3~5 秒，这里最小 10 秒）
const autoRefresh = ref(false);
const interval = ref(30);
let timer = null;

// 快照回看
const dates = ref([]);
const histDate = ref('');
const snapshots = ref([]);
const histId = ref('');

// 本页排序
const sortKey = ref('net_inflow');
const sortDesc = ref(true);

onMounted(async () => {
  await loadDates();
  live();
});
onBeforeUnmount(stopTimer);

async function loadDates() {
  try {
    const r = await fetchLhbDates();
    dates.value = r.dates || [];
    hasCred.value = r.has_credentials;
  } catch { /* 不影响主流程 */ }
}

async function live() {
  mode.value = 'live';
  histId.value = '';
  loading.value = true;
  error.value = '';
  try {
    snap.value = await fetchLhbLive({
      pages: pages.value,
      start: useRange.value ? rStart.value : '',
      end: useRange.value ? rEnd.value : '',
    });
    hasCred.value = snap.value.has_credentials ?? hasCred.value;
    if (snap.value.saved) loadDates();
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function pickDate(d) {
  stopAuto();
  mode.value = 'snapshot';
  histDate.value = d;
  histId.value = '';
  snap.value = null;
  error.value = '';
  try {
    const r = await fetchLhbSnapshots(d);
    snapshots.value = r.snapshots || [];
    if (snapshots.value.length) pickSnapshot(snapshots.value[0].id);
  } catch (e) {
    error.value = e.message;
  }
}

async function pickSnapshot(id) {
  histId.value = id;
  loading.value = true;
  error.value = '';
  try {
    snap.value = await fetchLhbSnapshot(histDate.value, id);
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

function toggleAuto() {
  if (autoRefresh.value) return stopAuto();
  autoRefresh.value = true;
  mode.value = 'live';
  live();
  timer = setInterval(live, Math.max(10, interval.value) * 1000);
}
function stopAuto() {
  autoRefresh.value = false;
  stopTimer();
}
function stopTimer() {
  if (timer) { clearInterval(timer); timer = null; }
}

function setSort(k) {
  if (sortKey.value === k) sortDesc.value = !sortDesc.value;
  else { sortKey.value = k; sortDesc.value = true; }
}

const items = computed(() => {
  const list = [...(snap.value?.items || [])];
  const k = sortKey.value;
  const num = (v) => {
    const n = Number(v);
    return isFinite(n) ? n : -Infinity;
  };
  list.sort((a, b) => (sortDesc.value ? num(b[k]) - num(a[k]) : num(a[k]) - num(b[k])));
  return list;
});

function fmtMoney(v) {
  const n = Number(v);
  if (v == null || v === '' || !isFinite(n)) return v ?? '-';
  const a = Math.abs(n);
  if (a >= 1e8) return (n / 1e8).toFixed(2) + ' 亿';
  if (a >= 1e4) return (n / 1e4).toFixed(0) + ' 万';
  return n.toFixed(0);
}
function fmtPct(v) {
  const n = Number(v);
  if (v == null || v === '' || !isFinite(n)) return v ?? '-';
  return (n > 0 ? '+' : '') + n.toFixed(2) + '%';
}
function cls(v) {
  const n = Number(v);
  if (!isFinite(n) || n === 0) return '';
  return n > 0 ? 'up' : 'down';
}
const fmtVal = (v) => (v == null || v === '' ? '-' : v);

const COLS = [
  { k: 'code', label: '代码', left: true },
  { k: 'name', label: '名称', left: true },
  { k: 'plate', label: '板块', left: true },
  { k: 'price', label: '现价' },
  { k: 'pct', label: '涨幅', sort: true },
  { k: 'amount', label: '成交额', sort: true },
  { k: 'net_inflow', label: '主力净额', sort: true },
  { k: 'net_ratio', label: '净流占比', sort: true },
  { k: 'board_desc', label: '连板说明', left: true },
  { k: 'popularity', label: '人气值', sort: true },
];
</script>

<template>
  <div>
    <div class="panel">
      <h2>
        实时龙虎榜
        <span class="lh-sub">开盘啦盘中资金排行 · 每次拉取自动落盘到 data/lhb_realtime/，盘后可回看</span>
      </h2>

      <div class="lh-note">
        ⓘ 这是<b>盘中实时资金排行</b>，不是交易所收盘后披露的正式龙虎榜；仅作线索，不等于游资席位已买入。
        仅在交易日盘中有数据，周末/非交易时段返回空列表属正常。
      </div>

      <div v-if="!hasCred" class="lh-warn">
        ⚠ 后端未检测到开盘啦凭证（项目根 <code>.env</code> 的 <code>KPL_USER_ID</code> / <code>KPL_TOKEN</code>）。
        文档说明部分版本/权限需要认证，若拉取为空请在 .env 填写后<b>重启 web 服务</b>。已落盘的快照仍可回看。
      </div>

      <!-- 控制栏 -->
      <div class="lh-bar">
        <button class="lh-btn primary" :disabled="loading" @click="live">⟳ 拉取最新</button>
        <label class="lh-field">
          页数
          <select v-model.number="pages" class="sort-select">
            <option :value="1">1页(60条)</option>
            <option :value="2">2页(120条)</option>
            <option :value="3">3页(180条)</option>
            <option :value="5">5页(300条)</option>
          </select>
        </label>
        <label class="lh-field">
          <input type="checkbox" v-model="useRange" /> 区间
          <input v-model="rStart" class="lh-time" maxlength="4" placeholder="0925" :disabled="!useRange" />
          ~
          <input v-model="rEnd" class="lh-time" maxlength="4" placeholder="0930" :disabled="!useRange" />
          <span class="lh-hint">HHMM</span>
        </label>
        <button class="lh-btn" :class="{ on: autoRefresh }" @click="toggleAuto">
          {{ autoRefresh ? '● 自动刷新中' : '○ 自动刷新' }}
        </button>
        <label class="lh-field" v-if="!autoRefresh">
          间隔
          <select v-model.number="interval" class="sort-select">
            <option :value="10">10s</option>
            <option :value="30">30s</option>
            <option :value="60">60s</option>
          </select>
        </label>
      </div>

      <!-- 快照回看 -->
      <div class="lh-hist" v-if="dates.length">
        <span class="lh-hist-label">快照回看</span>
        <button
          v-for="d in dates"
          :key="d"
          class="date-tab"
          :class="{ active: mode === 'snapshot' && histDate === d }"
          @click="pickDate(d)"
        >
          {{ d.slice(5) }}
        </button>
        <button v-if="mode === 'snapshot'" class="lh-btn" @click="live">↩ 返回实时</button>
      </div>
      <div class="lh-hist" v-if="mode === 'snapshot' && snapshots.length">
        <span class="lh-hist-label">{{ histDate.slice(5) }} 时间点</span>
        <button
          v-for="s in snapshots"
          :key="s.id"
          class="date-tab"
          :class="{ active: histId === s.id }"
          @click="pickSnapshot(s.id)"
        >
          {{ s.time }}{{ s.range ? '（' + s.range + '）' : '' }}
        </button>
      </div>

      <div v-if="loading && !snap" class="loading">加载中…</div>
      <div v-else-if="error" class="error">⚠ {{ error }}</div>
      <template v-else-if="snap">
        <div class="stat-grid" style="margin-bottom: 14px">
          <div class="stat-card blue">
            <div class="stat-label">数据时点</div>
            <div class="stat-value" style="font-size: 18px">{{ snap.day }} {{ snap.time }}</div>
            <div class="stat-sub">
              {{ mode === 'snapshot' ? '本地快照' : '在线拉取' }}{{ snap.saved ? ' · 已落盘' : '' }}{{ snap.range ? ' · 区间 ' + snap.range : '' }}
            </div>
          </div>
          <div class="stat-card red">
            <div class="stat-label">本次条数</div>
            <div class="stat-value">{{ snap.items.length }}</div>
            <div class="stat-sub">接口总数 Count={{ fmtVal(snap.count) }}</div>
          </div>
        </div>

        <div v-if="snap.empty || !snap.items.length" class="empty">
          列表为空：可能是非交易日 / 非交易时段 / 账户无权限{{ hasCred ? '' : ' / 未配置凭证' }}。实时数据仅在交易日盘中有效。
        </div>
        <div v-else style="overflow-x: auto">
          <table class="stock-table">
            <thead>
              <tr>
                <th
                  v-for="c in COLS"
                  :key="c.k"
                  :class="{ left: c.left, sortable: c.sort, active: sortKey === c.k }"
                  @click="c.sort && setSort(c.k)"
                >
                  {{ c.label }}<span v-if="sortKey === c.k" class="sort-ind"> {{ sortDesc ? '▼' : '▲' }}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(it, i) in items" :key="(it.code || '') + i">
                <td class="left">{{ fmtVal(it.code) }}</td>
                <td class="left"><b>{{ fmtVal(it.name) }}</b></td>
                <td class="left">{{ fmtVal(it.plate) }}</td>
                <td>{{ fmtVal(it.price) }}</td>
                <td :class="cls(it.pct)">{{ fmtPct(it.pct) }}</td>
                <td>{{ fmtMoney(it.amount) }}</td>
                <td :class="cls(it.net_inflow)">{{ fmtMoney(it.net_inflow) }}</td>
                <td :class="cls(it.net_ratio)">{{ fmtVal(it.net_ratio) }}</td>
                <td class="left">{{ fmtVal(it.board_desc) }}</td>
                <td>{{ fmtVal(it.popularity) }}</td>
              </tr>
            </tbody>
          </table>
          <div class="lh-foot">
            ⓘ 列含义按接口文档下标约定（0代码 1名称 4板块 5现价 6涨幅 7成交额 13主力净额 19净流占比 23连板说明 58人气值），
            为应用侧接口，字段可能调整；原始数组完整保存在快照 JSON 的 raw 字段中可回查。涨幅/净额的单位以真实数据为准，首次使用请与 App 对照确认。
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.lh-sub {
  font-size: 12px;
  color: var(--text-dim);
  font-weight: 400;
  margin-left: 10px;
}
.lh-note {
  font-size: 12.5px;
  line-height: 1.7;
  color: #1e40af;
  background: #eff6ff;
  border-left: 4px solid #2563eb;
  padding: 8px 14px;
  margin-bottom: 12px;
  border-radius: 0 6px 6px 0;
}
.lh-warn {
  font-size: 12.5px;
  line-height: 1.7;
  color: #7a5b12;
  background: #fff8e6;
  border: 1px solid #f0d9a6;
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 12px;
}
.lh-warn code {
  background: #fff;
  border: 1px solid #f0d9a6;
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 12px;
}
.lh-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
  padding: 8px 10px;
  background: var(--card-2);
  border-radius: 8px;
}
.lh-field {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-dim);
}
.lh-time {
  width: 52px;
  padding: 5px 6px;
  font-size: 12px;
  text-align: center;
  border: 1px solid var(--border);
  border-radius: 6px;
  outline: none;
}
.lh-time:focus {
  border-color: var(--blue);
}
.lh-time:disabled {
  background: #f3f4f6;
}
.lh-hint {
  font-size: 11px;
}
.lh-btn {
  font-size: 12px;
  color: var(--blue);
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 6px 14px;
  cursor: pointer;
}
.lh-btn:hover:not(:disabled) {
  border-color: var(--blue);
  background: #e8f3ff;
}
.lh-btn.primary {
  color: #fff;
  background: var(--blue);
  border-color: var(--blue);
}
.lh-btn.primary:hover:not(:disabled) {
  background: #1677d9;
}
.lh-btn.on {
  color: #dc2626;
  border-color: #dc2626;
}
.lh-btn:disabled {
  opacity: 0.5;
  cursor: wait;
}
.lh-hist {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.lh-hist-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-dim);
}
.lh-foot {
  margin-top: 12px;
  font-size: 11.5px;
  color: var(--text-dim);
  line-height: 1.7;
}
th.sortable {
  cursor: pointer;
}
th.sortable:hover,
th.active {
  color: var(--blue);
}
</style>
