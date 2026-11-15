<script setup>
import { ref, computed, onMounted } from 'vue';
import {
  fetchTicaiDates,
  fetchTicaiBoards,
  fetchTicaiBoardTrend,
  fetchBoardBlacklist,
} from '../api.js';
import { fmtYi, fmtPct, formatDate } from '../utils.js';
import TrendChart from '../components/TrendChart.vue';
import BarTimeChart from '../components/BarTimeChart.vue';
import BarGroupChart from '../components/BarGroupChart.vue';

const json = ref(null);
const error = ref('');
const loading = ref(false);
const dataDate = ref('');
const keyword = ref('');
const sortKey = ref('change_pct');
const sortDir = ref('desc');

const selectedCode = ref(null);
const selectedName = ref('');
const trend = ref(null);
const trendLoading = ref(false);
const trendError = ref('');

// 上色模式 + 缩放
const colorMode = ref('change_pct'); // change_pct | net_inflow
const zoom = ref(1);

const maxAbsPct = computed(() => {
  let m = 0;
  allBoards.value.forEach((b) => {
    if (b.change_pct != null) m = Math.max(m, Math.abs(b.change_pct));
  });
  return m || 1;
});
const maxAbsInflow = computed(() => {
  let m = 0;
  allBoards.value.forEach((b) => {
    if (b.main_net_inflow != null) m = Math.max(m, Math.abs(b.main_net_inflow));
  });
  return m || 1;
});

function boardColor(b) {
  let sign = 0;
  let strength = 0;
  if (colorMode.value === 'net_inflow') {
    const v = b.main_net_inflow;
    if (v == null) return '';
    sign = v >= 0 ? 1 : -1;
    strength = Math.min(1, Math.abs(v) / maxAbsInflow.value);
  } else {
    const v = b.change_pct;
    if (v == null) return '';
    sign = v >= 0 ? 1 : -1;
    strength = Math.min(1, Math.abs(v) / maxAbsPct.value);
  }
  const alpha = 0.06 + strength * 0.4;
  const c = sign >= 0 ? '245, 166, 35' : '82, 196, 26';
  return `rgba(${c}, ${alpha})`;
}

const boardGridStyle = computed(() => ({
  gridTemplateColumns: `repeat(auto-fill, minmax(${Math.round(160 * zoom.value)}px, 1fr))`,
}));
function cellStyle(b) {
  const bg = boardColor(b);
  return bg ? { background: bg } : {};
}

function closeModal() {
  selectedCode.value = null;
  selectedName.value = '';
  trend.value = null;
  trendError.value = '';
}

// ===== 多选（用于多题材趋势）=====
const selectedCodes = ref(new Set());
function isSelected(code) {
  return selectedCodes.value.has(code);
}
function toggleSelect(code) {
  const next = new Set(selectedCodes.value);
  if (next.has(code)) next.delete(code);
  else next.add(code);
  selectedCodes.value = next;
}
function clearSelection() {
  selectedCodes.value = new Set();
}
// 一键选择/取消选择某分类下所有题材
function toggleSelectGroup(g) {
  const codes = [
    ...g.direct.map((b) => b.code),
    ...g.children.flatMap((c) => c.boards.map((b) => b.code)),
  ];
  if (!codes.length) return;
  const next = new Set(selectedCodes.value);
  const allSelected = codes.every((c) => next.has(c));
  if (allSelected) codes.forEach((c) => next.delete(c));
  else codes.forEach((c) => next.add(c));
  selectedCodes.value = next;
}

// ===== 多题材趋势弹窗 =====
const multiModal = ref(false);
const multiLoading = ref(false);
const multiError = ref('');
const multiTrends = ref([]); // [{code, name, trend:[...]}]
const LINE_COLORS = [
  '#1890ff', '#f5a623', '#52c41a', '#9254de',
  '#13c2c2', '#eb2f96', '#fa8c16', '#e9a23b',
];

async function openMultiTrend() {
  const codes = [...selectedCodes.value];
  if (!codes.length) return;
  multiModal.value = true;
  multiLoading.value = true;
  multiError.value = '';
  multiTrends.value = [];
  try {
    const results = [];
    for (const code of codes) {
      const d = await fetchTicaiBoardTrend(code);
      results.push({ code, name: d.name || code, trend: d.trend || [] });
    }
    multiTrends.value = results;
  } catch (e) {
    multiError.value = e.message;
  } finally {
    multiLoading.value = false;
  }
}
function closeMultiModal() {
  multiModal.value = false;
  multiTrends.value = [];
}

// 同类趋势多题材叠加（divide 用于转亿）
function multiSeries(key, divide = 1) {
  return multiTrends.value.map((mt, i) => ({
    name: mt.name,
    color: LINE_COLORS[i % LINE_COLORS.length],
    points: mt.trend.map((t) => ({
      x: formatDate(t.date),
      y: t[key] != null ? Number(t[key]) / divide : null,
    })),
  }));
}
const multiAmountSeries = computed(() => multiSeries('amount', 1e8));
const multiNetFlowSeries = computed(() => multiSeries('main_net_inflow', 1e8));
const multiLimitUpSeries = computed(() => multiSeries('limit_up_count'));
const multiChangeSeries = computed(() => multiSeries('change_pct'));

onMounted(load);

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const res = await fetchTicaiDates();
    // 显式按日期升序，取最新一天
    const dates = (res.dates || []).slice().sort((a, b) => a.date.localeCompare(b.date));
    if (dates.length) {
      dataDate.value = dates[dates.length - 1].date;
      json.value = await fetchTicaiBoards(dates[dates.length - 1].file);
    }
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

const allBoards = computed(() => json.value?.boards || []);

// 脑图分类树（与题材板块页共用 localStorage）
const brainMap = ref(loadBrainMap());
function loadBrainMap() {
  try {
    const s = localStorage.getItem('ticai_brainmap');
    if (s) return JSON.parse(s);
  } catch (e) { /* ignore */ }
  return { trees: [] };
}

const boardMap = computed(() => {
  const m = {};
  allBoards.value.forEach((b) => {
    m[b.code] = b;
  });
  return m;
});

// 已分类题材 code 集合
const assignedCodes = computed(() => {
  const set = new Set();
  brainMap.value.trees.forEach((t) => {
    (t.leaves || []).forEach((c) => set.add(c));
    (t.children || []).forEach((ch) =>
      (ch.leaves || []).forEach((c) => set.add(c))
    );
  });
  return set;
});

const SORT_FIELDS = {
  code: (b) => b.code,
  name: (b) => b.name,
  change_pct: (b) => b.change_pct,
  limit_up_count: (b) => b.limit_up_count,
};
const SORT_LABEL = {
  code: '代码',
  name: '板块',
  change_pct: '涨跌幅',
  limit_up_count: '涨停家数',
};

function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'desc' ? 'asc' : 'desc';
  } else {
    sortKey.value = key;
    sortDir.value = 'desc';
  }
}

const rows = computed(() => {
  let arr = allBoards.value;
  const kw = keyword.value.trim().toLowerCase();
  if (kw) {
    arr = arr.filter(
      (b) =>
        (b.name || '').toLowerCase().includes(kw) ||
        (b.code || '').toLowerCase().includes(kw)
    );
  }
  const f = SORT_FIELDS[sortKey.value] || SORT_FIELDS.change_pct;
  const dir = sortDir.value === 'desc' ? -1 : 1;
  return [...arr].sort((a, b) => {
    const va = f(a);
    const vb = f(b);
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    let cmp;
    if (typeof va === 'string' || typeof vb === 'string') {
      cmp = String(va).localeCompare(String(vb));
    } else {
      cmp = va - vb;
    }
    return cmp * dir;
  });
});

// 对一组 code 做过滤 + 排序，返回 board 数组
function filterSort(codes) {
  const kw = keyword.value.trim().toLowerCase();
  let arr = (codes || []).map((c) => boardMap.value[c]).filter(Boolean);
  if (kw) {
    arr = arr.filter(
      (b) =>
        (b.name || '').toLowerCase().includes(kw) ||
        (b.code || '').toLowerCase().includes(kw)
    );
  }
  const f = SORT_FIELDS[sortKey.value] || SORT_FIELDS.change_pct;
  const dir = sortDir.value === 'desc' ? -1 : 1;
  return [...arr].sort((a, b) => {
    const va = f(a);
    const vb = f(b);
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    let cmp;
    if (typeof va === 'string' || typeof vb === 'string') {
      cmp = String(va).localeCompare(String(vb));
    } else {
      cmp = va - vb;
    }
    return cmp * dir;
  });
}

// 按脑图结构分组
const groupedBoards = computed(() => {
  const groups = brainMap.value.trees.map((tree) => ({
    id: tree.id,
    name: tree.name,
    direct: filterSort(tree.leaves),
    children: (tree.children || []).map((ch) => ({
      id: ch.id,
      name: ch.name,
      boards: filterSort(ch.leaves),
    })),
  }));
  const unassignedCodes = allBoards.value
    .filter((b) => !assignedCodes.value.has(b.code))
    .map((b) => b.code);
  groups.push({
    id: '__unassigned__',
    name: '未分类',
    direct: filterSort(unassignedCodes),
    children: [],
  });
  return groups;
});

async function selectBoard(b) {
  selectedCode.value = b.code;
  selectedName.value = b.name;
  trend.value = null;
  trendError.value = '';
  trendLoading.value = true;
  try {
    trend.value = await fetchTicaiBoardTrend(b.code);
  } catch (e) {
    trendError.value = e.message;
  } finally {
    trendLoading.value = false;
  }
}

// 趋势数据（跨天）
const trendRows = computed(() => {
  if (!trend.value) return [];
  return trend.value.trend.map((t) => ({
    date: formatDate(t.date),
    change_pct: t.change_pct,
    net_yi: t.main_net_inflow != null ? Number(t.main_net_inflow) / 1e8 : null,
    amount_yi: t.amount != null ? Number(t.amount) / 1e8 : null,
    limit_up: t.limit_up_count,
    rise: t.rise_count,
    fall: t.fall_count,
    flat: t.flat_count,
  }));
});

const changeSeries = computed(() => [
  {
    name: '涨跌幅',
    color: '#1890ff',
    points: trendRows.value.map((r) => ({ x: r.date, y: r.change_pct })),
  },
]);

const netFlowSeries = computed(() => [
  {
    name: '主力净流入',
    color: '#f5a623',
    points: trendRows.value.map((r) => ({ x: r.date, y: r.net_yi })),
  },
]);

const amountSeries = computed(() => [
  {
    name: '成交额',
    color: '#52c41a',
    points: trendRows.value.map((r) => ({ x: r.date, y: r.amount_yi })),
  },
]);

const limitUpPoints = computed(() =>
  trendRows.value.map((r) => ({ x: r.date, y: r.limit_up }))
);

const riseFallGroups = computed(() => [
  {
    label: '上涨',
    color: '#f5a623',
    points: trendRows.value.map((r) => ({ x: r.date, y: r.rise })),
  },
  {
    label: '下跌',
    color: '#52c41a',
    points: trendRows.value.map((r) => ({ x: r.date, y: r.fall })),
  },
  {
    label: '平盘',
    color: '#1890ff',
    points: trendRows.value.map((r) => ({ x: r.date, y: r.flat })),
  },
]);

// 题材板块汇总折叠
const collapsed = ref(true);
function toggleCollapse() {
  collapsed.value = !collapsed.value;
}

// ===== 黑名单叠加 =====
const blacklistEnabled = ref(false);
const blacklistSet = ref(new Set());   // Set<code>
const blacklistCollapsed = ref(true);  // 黑名单题材默认折叠
const blacklistMeta = ref(null);

async function toggleBlacklist() {
  if (!blacklistEnabled.value) {
    // 开启：加载黑名单
    try {
      const res = await fetchBoardBlacklist();
      const codes = new Set((res.blacklist || []).map((b) => b.code));
      blacklistSet.value = codes;
      blacklistMeta.value = res.meta || null;
    } catch (e) {
      console.warn('加载板块黑名单失败:', e);
      blacklistSet.value = new Set();
    }
    blacklistEnabled.value = true;
  } else {
    // 关闭
    blacklistEnabled.value = false;
    blacklistSet.value = new Set();
    blacklistCollapsed.value = true;
  }
}

function isBlacklisted(code) {
  return blacklistEnabled.value && blacklistSet.value.has(code);
}

function toggleBlacklistCollapse() {
  blacklistCollapsed.value = !blacklistCollapsed.value;
}
</script>

<template>
  <div v-if="loading" class="loading">加载中…</div>
  <div v-else-if="error" class="error">⚠ {{ error }}</div>
  <div v-else>
    <!-- 搜索 + 排序 -->
    <div class="panel">
      <div class="toolbar">
        <input
          v-model="keyword"
          class="search"
          type="text"
          placeholder="搜索板块名称 / 代码"
        />
        <select v-model="sortKey" class="sort-select" @change="sortDir = 'desc'">
          <option value="change_pct">按涨跌幅</option>
          <option value="code">按代码</option>
          <option value="name">按名称</option>
          <option value="limit_up_count">按涨停家数</option>
        </select>
        <button
          class="sort-dir-btn"
          @click="sortDir = sortDir === 'desc' ? 'asc' : 'desc'"
        >
          {{ sortDir === 'desc' ? '↓ 降序' : '↑ 升序' }}
        </button>
        <select v-model="colorMode" class="sort-select">
          <option value="change_pct">按涨跌幅上色</option>
          <option value="net_inflow">按资金流上色</option>
        </select>
        <label class="zoom-label">
          缩放
          <input v-model.number="zoom" type="range" min="0.6" max="1.6" step="0.1" />
        </label>
        <button
          class="tl-btn"
          :disabled="!selectedCodes.size"
          @click="openMultiTrend"
        >
          查看趋势{{ selectedCodes.size ? ` (${selectedCodes.size})` : '' }}
        </button>
        <button v-if="selectedCodes.size" class="sort-dir-btn" @click="clearSelection">
          清除选择
        </button>
        <button
          class="sort-dir-btn"
          :class="{ 'blacklist-active': blacklistEnabled }"
          @click="toggleBlacklist"
        >
          {{ blacklistEnabled ? '取消叠加黑名单' : '叠加黑名单' }}
        </button>
        <span class="toolbar-hint">
          数据日期 {{ formatDate(dataDate) }} · 共 {{ rows.length }} 个板块
        </span>
      </div>
    </div>

    <!-- 按脑图分类分区展示 -->
    <div class="panel">
      <h2 class="collapsible-header" @click="toggleCollapse">
        <span class="collapse-icon">{{ collapsed ? '▸' : '▾' }}</span>
        题材板块汇总
      </h2>
      <div v-if="blacklistEnabled && !collapsed" class="blacklist-controls">
        <button class="bl-toggle-btn" @click="toggleBlacklistCollapse">
          {{ blacklistCollapsed ? '展开黑名单题材' : '折叠黑名单题材' }}
        </button>
        <span class="bl-hint">已标记 {{ blacklistSet.size }} 个黑名单板块为灰色</span>
      </div>

      <div v-show="!collapsed">
      <div
        v-for="g in groupedBoards"
        :key="g.id"
        class="summary-group"
        v-show="g.direct.length || g.children.some((c) => c.boards.length)"
      >
        <div class="summary-group-title">
          <span class="sg-title-text">{{ g.name }}</span>
          <button class="sg-select-all" @click="toggleSelectGroup(g)">全选</button>
        </div>

        <!-- 直接挂树干的题材 -->
        <div v-if="g.direct.length" class="board-grid" :style="boardGridStyle">
          <div
            v-for="b in g.direct"
            :key="b.code"
            class="board-cell"
            :class="{
              active: selectedCode === b.code,
              selected: isSelected(b.code),
              blacklisted: isBlacklisted(b.code),
              'blacklist-hidden': blacklistEnabled && blacklistCollapsed && isBlacklisted(b.code),
            }"
            :style="cellStyle(b)"
            @click="selectBoard(b)"
          >
            <span
              class="bc-check"
              :class="{ checked: isSelected(b.code) }"
              @click.stop="toggleSelect(b.code)"
              >{{ isSelected(b.code) ? '✓' : '' }}</span
            >
            <div class="bc-name" :title="b.name">{{ b.name }}</div>
            <div class="bc-code">{{ b.code }}</div>
            <div class="bc-stats">
              <span :class="b.change_pct == null ? '' : b.change_pct >= 0 ? 'up' : 'down'">
                {{ fmtPct(b.change_pct) }}
              </span>
              <span :class="b.limit_up_count > 0 ? 'up' : ''">
                涨停 {{ b.limit_up_count || 0 }}
              </span>
            </div>
            <div class="bc-members">{{ b.member_count || 0 }} 只成分股</div>
          </div>
        </div>

        <!-- 子树干 -->
        <div
          v-for="ch in g.children"
          :key="ch.id"
          class="summary-subgroup"
          v-show="ch.boards.length"
        >
          <div class="summary-subgroup-title">{{ ch.name }}</div>
          <div class="board-grid" :style="boardGridStyle">
            <div
              v-for="b in ch.boards"
              :key="b.code"
              class="board-cell"
              :class="{
                active: selectedCode === b.code,
                selected: isSelected(b.code),
                blacklisted: isBlacklisted(b.code),
                'blacklist-hidden': blacklistEnabled && blacklistCollapsed && isBlacklisted(b.code),
              }"
              :style="cellStyle(b)"
              @click="selectBoard(b)"
            >
              <span
                class="bc-check"
                :class="{ checked: isSelected(b.code) }"
                @click.stop="toggleSelect(b.code)"
                >{{ isSelected(b.code) ? '✓' : '' }}</span
              >
              <div class="bc-name" :title="b.name">{{ b.name }}</div>
              <div class="bc-code">{{ b.code }}</div>
              <div class="bc-stats">
                <span :class="b.change_pct == null ? '' : b.change_pct >= 0 ? 'up' : 'down'">
                  {{ fmtPct(b.change_pct) }}
                </span>
                <span :class="b.limit_up_count > 0 ? 'up' : ''">
                  涨停 {{ b.limit_up_count || 0 }}
                </span>
              </div>
              <div class="bc-members">{{ b.member_count || 0 }} 只成分股</div>
            </div>
          </div>
        </div>
      </div>
      </div>
    </div>
    <div v-if="selectedCode" class="modal-mask" @click.self="closeModal">
      <div class="modal">
        <div class="modal-head">
          <span>板块趋势：{{ selectedName }}（{{ selectedCode }}）</span>
          <button class="modal-close" title="关闭" @click="closeModal">✕</button>
        </div>
        <div class="modal-body">
          <div v-if="trendLoading" class="loading">加载趋势中…</div>
          <div v-else-if="trendError" class="error">⚠ {{ trendError }}</div>
          <div v-else-if="trend && trendRows.length" class="trend-stack">
            <div>
              <h3 style="color: var(--blue)">每天涨跌幅变化（%）</h3>
              <TrendChart :series="changeSeries" unit="%" :show-zero-line="true" />
            </div>
            <div>
              <h3 style="color: var(--red)">每天主力净流入流出变化（亿）</h3>
              <TrendChart :series="netFlowSeries" unit="亿" :show-zero-line="true" />
            </div>
            <div>
              <h3 style="color: var(--green)">每天成交额变化（亿）</h3>
              <TrendChart :series="amountSeries" unit="亿" />
            </div>
            <div>
              <h3 style="color: var(--gold)">每天涨停家数变化</h3>
              <BarTimeChart :points="limitUpPoints" color="#f5a623" />
            </div>
            <div>
              <h3 style="color: var(--text)">每天涨跌平数据</h3>
              <BarGroupChart :groups="riseFallGroups" />
            </div>
          </div>
          <div v-else class="empty">该板块暂无跨天数据</div>
        </div>
      </div>
    </div>

    <!-- 多题材趋势（弹窗） -->
    <div v-if="multiModal" class="modal-mask" @click.self="closeMultiModal">
      <div class="modal">
        <div class="modal-head">
          <span>题材趋势对比（{{ multiTrends.length }} 个题材）</span>
          <button class="modal-close" title="关闭" @click="closeMultiModal">✕</button>
        </div>
        <div class="modal-body">
          <div v-if="multiLoading" class="loading">加载趋势中…</div>
          <div v-else-if="multiError" class="error">⚠ {{ multiError }}</div>
          <div v-else-if="multiTrends.length" class="trend-stack">
            <div>
              <h3 style="color: var(--blue)">总成交额变化趋势（亿）</h3>
              <TrendChart :series="multiAmountSeries" unit="亿" />
            </div>
            <div>
              <h3 style="color: var(--red)">主力净流入变化趋势（亿）</h3>
              <TrendChart :series="multiNetFlowSeries" unit="亿" :show-zero-line="true" />
            </div>
            <div>
              <h3 style="color: var(--gold)">每天涨停家数变化趋势</h3>
              <TrendChart :series="multiLimitUpSeries" unit="家" />
            </div>
            <div>
              <h3 style="color: var(--green)">每天涨跌幅变化趋势（%）</h3>
              <TrendChart :series="multiChangeSeries" unit="%" :show-zero-line="true" />
            </div>
          </div>
          <div v-else class="empty">没有选中的题材</div>
        </div>
      </div>
    </div>
  </div>
</template>
