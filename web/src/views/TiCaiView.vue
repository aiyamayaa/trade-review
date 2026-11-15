<script setup>
import { ref, computed, onMounted, nextTick } from 'vue';
import { fetchTicaiDates, fetchTicaiBoards, fetchTicaiBoard, fetchBoardBlacklist, fetchGranville, fetchTicaiAllTrend, fetchData } from '../api.js';
import { fmtYi, fmtPct, formatDate, gvClass, gvShort } from '../utils.js';
import TrendChart from '../components/TrendChart.vue';

const json = ref(null);
const error = ref('');
const loading = ref(false);
const keyword = ref('');
const sortKey = ref('change_pct');
const sortDir = ref('desc');

// 日期文件
const dateList = ref([]);
const selectedDate = ref(''); // 存文件名

const expandedCode = ref(null);
const boardDetail = ref(null);
const detailLoading = ref(false);
const detailError = ref('');
const reasonOpen = ref({});

// ===== 每日成交额折线图（默认显示 融资融券/深股通/沪股通；题材板块点按钮叠加）=====
const trendDays = ref([]); // [{ date, boards: [{code,name,amount,...}] }]
const fundJson = ref(null); // limit_up_down_data.json（margin/north_flow）
const overlayCodes = ref(new Set()); // 已叠加的题材板块 code
const trendError = ref('');

onMounted(async () => {
  try {
    const t = await fetchTicaiAllTrend();
    trendDays.value = t.days || [];
  } catch (e) {
    trendError.value = '题材趋势加载失败：' + e.message;
  }
  try {
    fundJson.value = await fetchData();
  } catch (e) {
    console.warn('资金面数据加载失败（折线图不显示融资融券/沪深股通）:', e);
  }
});

const trendDates = computed(() => trendDays.value.map((d) => d.date));

// 基准线：融资融券余额 / 沪股通净买 / 深股通净买（日期对齐题材日期，单位亿）
const FUND_COLORS = ['#111827', '#d4380d', '#08979c'];
const baseSeries = computed(() => {
  const fd = fundJson.value?.data || {};
  const defs = [
    { name: '融资融券余额', pick: (m) => m.margin?.total_margin_balance, div: 1e8 },
    { name: '沪股通净买', pick: (m) => m.north_flow?.sh_net_buy, div: 1 },
    { name: '深股通净买', pick: (m) => m.north_flow?.sz_net_buy, div: 1 },
  ];
  return defs
    .map((d, i) => ({
      name: d.name,
      color: FUND_COLORS[i],
      points: trendDates.value.map((date) => {
        const m = fd[date];
        const v = m ? d.pick(m) : null;
        return { x: formatDate(date), y: v != null ? Number(v) / d.div : null };
      }),
    }))
    .filter((s) => s.points.some((p) => p.y != null)); // 停披的（如北向）自动隐藏
});

// 被叠加题材板块的成交额线（单位亿）
const OVERLAY_COLORS = ['#1890ff', '#f5a623', '#52c41a', '#9254de', '#13c2c2', '#eb2f96', '#fa8c16', '#e9a23b'];
const boardAmountByName = computed(() => {
  const m = {}; // name → points
  const idx = new Map(); // code → name
  trendDays.value.forEach((d) => {
    (d.boards || []).forEach((b) => {
      if (b.code) idx.set(b.code, b.name);
      const n = b.name;
      if (!m[n]) m[n] = new Map();
      m[n].set(d.date, b.amount);
    });
  });
  return { map: m, nameByCode: idx };
});
const overlaySeries = computed(() => {
  const { map, nameByCode } = boardAmountByName.value;
  return [...overlayCodes.value]
    .map((code, i) => {
      const name = nameByCode.get(code);
      if (!name || !map[name]) return null;
      return {
        name,
        color: OVERLAY_COLORS[i % OVERLAY_COLORS.length],
        points: trendDates.value.map((date) => {
          const v = map[name].get(date);
          return { x: formatDate(date), y: v != null ? Number(v) / 1e8 : null };
        }),
      };
    })
    .filter(Boolean);
});

// 叠加/移除题材板块
function toggleOverlay(board) {
  const s = new Set(overlayCodes.value);
  if (s.has(board.code)) s.delete(board.code);
  else s.add(board.code);
  overlayCodes.value = s;
}
function isOverlaid(code) {
  return overlayCodes.value.has(code);
}

// ===== 葛南维均线打分（data/stocks/granville/{date}.json，按题材文件日期关联）=====
const granville = ref(null); // { exists, date, data }
const granvilleMap = computed(() => {
  const m = {};
  for (const s of granville.value?.data?.stocks || []) m[s.code] = s;
  for (const s of granville.value?.data?.skipped || []) m[s.code] = { skipped: s.skip };
  return m;
});
async function loadGranvilleFor(file) {
  granville.value = null;
  const d = dateList.value.find((x) => x.file === file);
  if (!d) return;
  try {
    granville.value = await fetchGranville(d.date);
  } catch (e) {
    console.warn('葛南维评分加载失败:', e);
  }
}
function gvTitle(code) {
  const g = granvilleMap.value[code];
  if (!g) return '';
  return [`收盘 ${g.close} | MA5 ${g.ma5} | MA20 ${g.ma20} | MA60 ${g.ma60}`, ...(g.signals || [])].join('\n');
}

onMounted(load);

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const res = await fetchTicaiDates();
    dateList.value = res.dates || [];
    // 默认选最新日期
    selectedDate.value = dateList.value.length
      ? dateList.value[dateList.value.length - 1].file
      : '';
    if (selectedDate.value) {
      await loadBoards(selectedDate.value);
    }
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function loadBoards(file) {
  loading.value = true;
  error.value = '';
  expandedCode.value = null;
  boardDetail.value = null;
  reasonOpen.value = {};
  try {
    json.value = await fetchTicaiBoards(file);
    loadGranvilleFor(file); // 后台加载当日葛南维评分（不阻塞板块渲染）
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

function onSelectDate(file) {
  if (file === selectedDate.value) return;
  selectedDate.value = file;
  loadBoards(file);
}

const meta = computed(() => json.value?.meta || {});
const allBoards = computed(() => json.value?.boards || []);

const SORT_FIELDS = {
  code: (b) => b.code,
  change_pct: (b) => b.change_pct,
  main_net_inflow: (b) => b.main_net_inflow,
  amount: (b) => b.amount,
  limit_up_count: (b) => b.limit_up_count,
};
const SORT_LABEL = {
  code: '代码',
  change_pct: '涨跌幅',
  main_net_inflow: '主力净流入',
  amount: '成交额',
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
        (b.code || '').toLowerCase().includes(kw) ||
        (b.lead_stock?.name || '').toLowerCase().includes(kw)
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

async function toggleBoard(b) {
  if (expandedCode.value === b.code) {
    expandedCode.value = null;
    boardDetail.value = null;
    return;
  }
  expandedCode.value = b.code;
  boardDetail.value = null;
  detailError.value = '';
  detailLoading.value = true;
  try {
    boardDetail.value = await fetchTicaiBoard(b.code, selectedDate.value);
  } catch (e) {
    detailError.value = e.message;
  } finally {
    detailLoading.value = false;
  }
}

function toggleReason(code) {
  reasonOpen.value = { ...reasonOpen.value, [code]: !reasonOpen.value[code] };
}

// 格式化辅助
function pctNoSign(v) {
  if (v == null) return '-';
  return Number(v).toFixed(2) + '%';
}
function num2(v) {
  if (v == null) return '-';
  return Number(v).toFixed(2);
}
function pctClass(v) {
  if (v == null) return '';
  return v >= 0 ? 'up' : 'down';
}
function reasonShort(reason) {
  const s = reason || '';
  if (!s) return '-';
  return s.length > 30 ? s.slice(0, 30) + '…' : s;
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

// ===== 脑图（分类树）=====
const brainMap = ref(loadBrainMap());
const editingId = ref(null);
const editText = ref('');
const showPool = ref(false);
const dragCode = ref(null);
const dragFrom = ref(null);
let idSeq = Date.now();

function genId(p) {
  return p + '-' + (idSeq++).toString(36);
}
function loadBrainMap() {
  try {
    const s = localStorage.getItem('ticai_brainmap');
    if (s) return JSON.parse(s);
  } catch (e) { /* ignore */ }
  return { trees: [] };
}
function saveBrainMap() {
  localStorage.setItem('ticai_brainmap', JSON.stringify(brainMap.value));
}

// 题材池 = 未分配到任何树干的题材
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
const poolBoards = computed(() =>
  allBoards.value.filter((b) => !assignedCodes.value.has(b.code))
);

function boardByCode(code) {
  return allBoards.value.find((b) => b.code === code) || null;
}
const boardMap = computed(() => {
  const m = {};
  allBoards.value.forEach((b) => {
    m[b.code] = b;
  });
  return m;
});

// 脑图题材方块按涨跌着色
const maxAbsPct = computed(() => {
  let m = 0;
  allBoards.value.forEach((b) => {
    if (b.change_pct != null) m = Math.max(m, Math.abs(b.change_pct));
  });
  return m || 1;
});
function leafColor(b) {
  if (!b || b.change_pct == null) return undefined;
  const sign = b.change_pct >= 0 ? 1 : -1;
  const strength = Math.min(1, Math.abs(b.change_pct) / maxAbsPct.value);
  const alpha = 0.06 + strength * 0.4;
  const c = sign >= 0 ? '245, 166, 35' : '82, 196, 26';
  return `rgba(${c}, ${alpha})`;
}

// 折叠状态（按节点 id）：默认全部折叠
function buildAllCollapsed() {
  const m = {};
  for (const t of brainMap.value.trees || []) {
    m[t.id] = true;
    for (const ch of t.children || []) m[ch.id] = true;
  }
  return m;
}
const collapsed = ref(buildAllCollapsed());
function toggleCollapse(id) {
  collapsed.value = { ...collapsed.value, [id]: !collapsed.value[id] };
}
function isCollapsed(id) {
  return !!collapsed.value[id];
}
function expandAllNodes() {
  collapsed.value = {};
}
function collapseAllNodes() {
  collapsed.value = buildAllCollapsed();
}

function addTree() {
  brainMap.value.trees.push({
    id: genId('t'),
    name: '新分类',
    leaves: [],
    children: [],
  });
  saveBrainMap();
}
function addChild(tree) {
  tree.children.push({ id: genId('c'), name: '新子分类', leaves: [] });
  saveBrainMap();
}
function moveTreeLeft(index) {
  const trees = brainMap.value.trees;
  if (index <= 0) return;
  [trees[index - 1], trees[index]] = [trees[index], trees[index - 1]];
  saveBrainMap();
}
function moveTreeRight(index) {
  const trees = brainMap.value.trees;
  if (index >= trees.length - 1) return;
  [trees[index], trees[index + 1]] = [trees[index + 1], trees[index]];
  saveBrainMap();
}
function removeTree(treeId) {
  brainMap.value.trees = brainMap.value.trees.filter((t) => t.id !== treeId);
  saveBrainMap();
}
function removeChild(treeId, childId) {
  const tree = brainMap.value.trees.find((t) => t.id === treeId);
  if (tree) tree.children = tree.children.filter((c) => c.id !== childId);
  saveBrainMap();
}
function startEdit(node) {
  editingId.value = node.id;
  editText.value = node.name;
}
function saveEdit(node) {
  node.name = editText.value.trim() || node.name;
  editingId.value = null;
  saveBrainMap();
}
function cancelEdit() {
  editingId.value = null;
}

// 拖动
function onDragStart(e, code, from) {
  dragCode.value = code;
  dragFrom.value = from;
  e.dataTransfer.effectAllowed = 'move';
}
function onDragOver(e) {
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
}
function onDrop(e, target) {
  e.preventDefault();
  if (!dragCode.value) return;
  moveBoard(dragCode.value, dragFrom.value, target);
  dragCode.value = null;
  dragFrom.value = null;
}
function onDragEnd() {
  dragCode.value = null;
  dragFrom.value = null;
}

// 移动题材到目标（target: {treeId, childId|null} 或 'pool'）
function moveBoard(code, from, target) {
  // 1. 从原位置移除
  if (from && from !== 'pool') {
    const tree = brainMap.value.trees.find((t) => t.id === from.treeId);
    if (tree) {
      if (from.childId) {
        const child = tree.children.find((c) => c.id === from.childId);
        if (child) child.leaves = child.leaves.filter((c) => c !== code);
      } else {
        tree.leaves = tree.leaves.filter((c) => c !== code);
      }
    }
  }
  // 2. 加入目标（target='pool' 则只移除）
  if (target !== 'pool') {
    const tree = brainMap.value.trees.find((t) => t.id === target.treeId);
    if (!tree) return;
    if (target.childId) {
      const child = tree.children.find((c) => c.id === target.childId);
      if (child && !child.leaves.includes(code)) child.leaves.push(code);
    } else {
      if (!tree.leaves.includes(code)) tree.leaves.push(code);
    }
  }
  saveBrainMap();
}

// 点击明细 → 展开列表并滚动定位
async function goDetail(code) {
  const b = boardByCode(code);
  if (!b) return;
  if (expandedCode.value !== code) {
    await toggleBoard(b);
  }
  await nextTick();
  const el = document.getElementById('ticai-list');
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// 导出脑图 JSON 到本地
const fileInput = ref(null);
function exportBrainMap() {
  const data = JSON.stringify(brainMap.value, null, 2);
  const blob = new Blob([data], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'ticai_brainmap.json';
  a.click();
  URL.revokeObjectURL(url);
}
function triggerImport() {
  fileInput.value?.click();
}
function importBrainMap(e) {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result);
      if (data && Array.isArray(data.trees)) {
        brainMap.value = data;
        saveBrainMap();
        collapseAllNodes(); // 加载后默认全部折叠
      } else {
        alert('文件格式不正确：缺少 trees 字段');
      }
    } catch (err) {
      alert('解析失败：' + err.message);
    }
  };
  reader.readAsText(file);
  e.target.value = '';
}
</script>

<template>
  <div v-if="loading" class="loading">加载中…</div>
  <div v-else-if="error" class="error">⚠ {{ error }}</div>
  <div v-else>
    <!-- meta -->
    <div class="panel">
      <div class="meta-grid">
        <div class="meta-card">
          <div class="label">数据源</div>
          <div class="value" style="font-size: 13px; font-weight: 400">
            {{ meta.source || '-' }}
          </div>
        </div>
        <div class="meta-card">
          <div class="label">板块类型</div>
          <div class="value">{{ meta.board_type || '-' }}</div>
        </div>
        <div class="meta-card">
          <div class="label">题材板块数</div>
          <div class="value">{{ meta.total ?? allBoards.length }}</div>
        </div>
        <div class="meta-card">
          <div class="label">生成时间</div>
          <div class="value" style="font-size: 13px; font-weight: 400">
            {{ meta.generated_at || '-' }}
          </div>
        </div>
      </div>
    </div>

    <!-- 日期切换 -->
    <div v-if="dateList.length" class="date-tabs">
      <button
        v-for="d in dateList"
        :key="d.file"
        class="date-tab"
        :class="{ active: d.file === selectedDate }"
        @click="onSelectDate(d.file)"
      >
        {{ formatDate(d.date) }}
      </button>
    </div>

    <!-- 脑图（分类树） -->
    <div class="panel">
      <div class="brain-toolbar">
        <h2>题材脑图</h2>
        <div class="brain-actions">
          <button class="tl-btn" @click="expandAllNodes">展开全部</button>
          <button class="tl-btn" @click="collapseAllNodes">折叠全部</button>
          <button class="tl-btn" @click="addTree">+ 添加树干</button>
          <button class="tl-btn" @click="showPool = !showPool">
            {{ showPool ? '收起题材池' : '题材池' }}
          </button>
          <button class="tl-btn" @click="exportBrainMap">存储</button>
          <button class="tl-btn" @click="triggerImport">加载</button>
          <input
            ref="fileInput"
            type="file"
            accept=".json,application/json"
            style="display: none"
            @change="importBrainMap"
          />
        </div>
      </div>

      <div class="brain-wrap">
        <div class="brain-trees">
          <div v-for="(tree, ti) in brainMap.trees" :key="tree.id" class="brain-tree">
            <!-- 树干 -->
            <div class="trunk">
              <span class="fold-btn" @click="toggleCollapse(tree.id)">{{ isCollapsed(tree.id) ? '▸' : '▾' }}</span>
              <span v-if="editingId === tree.id" class="edit-inline">
                <input
                  v-model="editText"
                  @keyup.enter="saveEdit(tree)"
                  @blur="saveEdit(tree)"
                />
              </span>
              <span v-else class="trunk-name" @dblclick="startEdit(tree)">{{ tree.name }}</span>
              <span class="node-actions">
                <button class="node-btn" title="左移" :disabled="ti === 0" @click="moveTreeLeft(ti)">←</button>
                <button class="node-btn" title="右移" :disabled="ti === brainMap.trees.length - 1" @click="moveTreeRight(ti)">→</button>
                <button class="node-btn" title="重命名" @click="startEdit(tree)">✏️</button>
                <button class="node-btn" title="添加子树干" @click="addChild(tree)">+</button>
                <button class="node-btn" title="删除" @click="removeTree(tree.id)">🗑</button>
              </span>
            </div>

            <div v-show="!isCollapsed(tree.id)" class="tree-body">
              <!-- 直接挂树干的题材 -->
              <div
                class="drop-zone trunk-zone"
                @dragover="onDragOver"
                @drop="onDrop($event, { treeId: tree.id, childId: null })"
              >
                <div
                  v-for="code in tree.leaves"
                  :key="code"
                  class="leaf"
                  :style="{ background: leafColor(boardMap[code]) }"
                  draggable="true"
                  @dragstart="onDragStart($event, code, { treeId: tree.id, childId: null })"
                  @dragend="onDragEnd"
                >
                  <div class="leaf-top">
                    <span class="leaf-name">{{ boardMap[code]?.name || code }}</span>
                    <button class="leaf-detail" @click.stop="goDetail(code)">明细</button>
                  </div>
                  <div class="leaf-bottom">
                    <span :class="pctClass(boardMap[code]?.change_pct)">{{ fmtPct(boardMap[code]?.change_pct) }}</span>
                    <span v-if="boardMap[code]?.limit_up_count > 0" class="leaf-limit">涨停 {{ boardMap[code]?.limit_up_count }}</span>
                  </div>
                </div>
                <div v-if="!tree.leaves.length" class="drop-hint">拖入题材</div>
              </div>

              <!-- 子树干 -->
              <div v-for="child in tree.children" :key="child.id" class="branch">
                <div class="branch-head">
                  <span class="fold-btn" @click="toggleCollapse(child.id)">{{ isCollapsed(child.id) ? '▸' : '▾' }}</span>
                  <span v-if="editingId === child.id" class="edit-inline">
                    <input
                      v-model="editText"
                      @keyup.enter="saveEdit(child)"
                      @blur="saveEdit(child)"
                    />
                  </span>
                  <span v-else class="branch-name" @dblclick="startEdit(child)">{{ child.name }}</span>
                  <span class="node-actions">
                    <button class="node-btn" title="重命名" @click="startEdit(child)">✏️</button>
                    <button class="node-btn" title="删除" @click="removeChild(tree.id, child.id)">🗑</button>
                  </span>
                </div>
                <div
                  v-show="!isCollapsed(child.id)"
                  class="drop-zone branch-zone"
                  @dragover="onDragOver"
                  @drop="onDrop($event, { treeId: tree.id, childId: child.id })"
                >
                  <div
                    v-for="code in child.leaves"
                    :key="code"
                    class="leaf"
                    :style="{ background: leafColor(boardMap[code]) }"
                    draggable="true"
                    @dragstart="onDragStart($event, code, { treeId: tree.id, childId: child.id })"
                    @dragend="onDragEnd"
                  >
                    <div class="leaf-top">
                      <span class="leaf-name">{{ boardMap[code]?.name || code }}</span>
                      <button class="leaf-detail" @click.stop="goDetail(code)">明细</button>
                    </div>
                    <div class="leaf-bottom">
                      <span :class="pctClass(boardMap[code]?.change_pct)">{{ fmtPct(boardMap[code]?.change_pct) }}</span>
                      <span v-if="boardMap[code]?.limit_up_count > 0" class="leaf-limit">涨停 {{ boardMap[code]?.limit_up_count }}</span>
                    </div>
                  </div>
                  <div v-if="!child.leaves.length" class="drop-hint">拖入题材</div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="!brainMap.trees.length" class="brain-empty">
            暂无树干，点击「+ 添加树干」创建分类，然后从题材池拖动题材进来
          </div>
        </div>
      </div>

      <!-- 题材池 -->
      <div v-if="showPool" class="pool">
        <div class="pool-head">
          题材池（{{ poolBoards.length }} 个未分类题材，拖到树干/子树干上，或拖回此处取消分类）
        </div>
        <div class="pool-grid" @dragover="onDragOver" @drop="onDrop($event, 'pool')">
          <div
            v-for="b in poolBoards"
            :key="b.code"
            class="leaf"
            :style="{ background: leafColor(b) }"
            draggable="true"
            @dragstart="onDragStart($event, b.code, 'pool')"
            @dragend="onDragEnd"
          >
            <div class="leaf-top">
              <span class="leaf-name">{{ b.name }}</span>
              <button class="leaf-detail" @click.stop="goDetail(b.code)">明细</button>
            </div>
            <div class="leaf-bottom">
              <span :class="pctClass(b.change_pct)">{{ fmtPct(b.change_pct) }}</span>
              <span v-if="b.limit_up_count > 0" class="leaf-limit">涨停 {{ b.limit_up_count }}</span>
            </div>
          </div>
          <div v-if="!poolBoards.length" class="drop-hint">所有题材已分类</div>
        </div>
      </div>
    </div>

    <!-- 搜索 + 排序提示 -->
    <div class="panel">
      <div class="toolbar">
        <input
          v-model="keyword"
          class="search"
          type="text"
          placeholder="搜索板块名称 / 代码 / 领涨股"
        />
        <button
          class="tl-btn"
          :class="{ 'blacklist-active': blacklistEnabled }"
          @click="toggleBlacklist"
        >
          {{ blacklistEnabled ? '取消叠加黑名单' : '叠加黑名单' }}
        </button>
        <span class="toolbar-hint">
          共 {{ rows.length }} 个板块 · 按 {{ SORT_LABEL[sortKey] }}
          {{ sortDir === 'desc' ? '↓' : '↑' }} 排序
        </span>
      </div>
    </div>

    <!-- 板块列表 -->
    <div id="ticai-list" class="panel">
      <h2>题材板块列表</h2>
      <div v-if="blacklistEnabled" class="blacklist-controls">
        <button class="bl-toggle-btn" @click="toggleBlacklistCollapse">
          {{ blacklistCollapsed ? '展开黑名单题材' : '折叠黑名单题材' }}
        </button>
        <span class="bl-hint">已标记 {{ blacklistSet.size }} 个黑名单板块为灰色</span>
      </div>
      <div style="overflow-x: auto">
        <table>
          <thead>
            <tr>
              <th
                class="sortable left"
                :class="{ active: sortKey === 'code' }"
                @click="toggleSort('code')"
              >
                代码<span class="sort-ind">{{ sortKey === 'code' ? (sortDir === 'desc' ? ' ↓' : ' ↑') : '' }}</span>
              </th>
              <th class="left">板块</th>
              <th
                class="sortable"
                :class="{ active: sortKey === 'change_pct' }"
                @click="toggleSort('change_pct')"
              >
                涨跌幅<span class="sort-ind">{{ sortKey === 'change_pct' ? (sortDir === 'desc' ? ' ↓' : ' ↑') : '' }}</span>
              </th>
              <th
                class="sortable left"
                :class="{ active: sortKey === 'main_net_inflow' }"
                @click="toggleSort('main_net_inflow')"
              >
                主力净流入<span class="sort-ind">{{ sortKey === 'main_net_inflow' ? (sortDir === 'desc' ? ' ↓' : ' ↑') : '' }}</span>
              </th>
              <th
                class="sortable left"
                :class="{ active: sortKey === 'amount' }"
                @click="toggleSort('amount')"
              >
                成交额<span class="sort-ind">{{ sortKey === 'amount' ? (sortDir === 'desc' ? ' ↓' : ' ↑') : '' }}</span>
              </th>
              <th
                class="sortable"
                :class="{ active: sortKey === 'limit_up_count' }"
                @click="toggleSort('limit_up_count')"
              >
                涨停家数<span class="sort-ind">{{ sortKey === 'limit_up_count' ? (sortDir === 'desc' ? ' ↓' : ' ↑') : '' }}</span>
              </th>
              <th>涨/跌/平</th>
              <th>成分股</th>
              <th class="left">领涨股</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="b in rows" :key="b.code">
              <tr @click="toggleBoard(b)" :class="{ 'row-open': expandedCode === b.code, 'row-blacklisted': isBlacklisted(b.code), 'row-blacklist-hidden': blacklistEnabled && blacklistCollapsed && isBlacklisted(b.code) }">
                <td class="left">{{ b.code }}</td>
                <td class="left">{{ b.name }}</td>
                <td :class="pctClass(b.change_pct)">{{ fmtPct(b.change_pct) }}</td>
                <td class="left">{{ fmtYi(b.main_net_inflow) }}</td>
                <td class="left">{{ fmtYi(b.amount) }}</td>
                <td :class="b.limit_up_count > 0 ? 'up' : ''">{{ b.limit_up_count || 0 }}</td>
                <td>{{ b.rise_count || 0 }}/{{ b.fall_count || 0 }}/{{ b.flat_count || 0 }}</td>
                <td>{{ b.member_count || 0 }}</td>
                <td class="left">
                  <span v-if="b.lead_stock">
                    {{ b.lead_stock.name }}
                    <span :class="pctClass(b.lead_stock.change_pct)">
                      {{ fmtPct(b.lead_stock.change_pct) }}</span
                    >
                  </span>
                  <span v-else>-</span>
                </td>
                <td>
                  <span class="toggle-btn" @click.stop="toggleBoard(b)">
                    {{ expandedCode === b.code ? '收起 ▾' : '展开 ▸' }}
                  </span>
                  <button
                    class="overlay-btn"
                    :class="{ on: isOverlaid(b.code) }"
                    :title="isOverlaid(b.code) ? '从成交额折线图移除' : '叠加到每日成交额折线图'"
                    @click.stop="toggleOverlay(b)"
                  >{{ isOverlaid(b.code) ? '取消叠加' : '📈 叠加' }}</button>
                </td>
              </tr>
              <tr v-if="expandedCode === b.code" class="detail-row">
                <td colspan="11">
                  <div v-if="detailLoading" class="detail-box">加载成分股中…</div>
                  <div v-else-if="detailError" class="detail-box">⚠ {{ detailError }}</div>
                  <div v-else-if="boardDetail" class="detail-box">
                    <div class="detail-title">
                      {{ boardDetail.name }}（{{ boardDetail.code }}）· 成分股
                      {{ (boardDetail.stocks || []).length }} 只
                      <span v-if="granville && !granville.exists" class="gv-miss-hint">
                        当日葛南维评分未采集，执行 <code>make fetch-granville</code> 后刷新
                      </span>
                    </div>
                    <div class="stock-panel" style="overflow-x: auto">
                      <table class="stock-table">
                        <thead>
                          <tr>
                            <th class="left">代码</th>
                            <th class="left">名称</th>
                            <th>涨跌幅</th>
                            <th>连板</th>
                            <th>葛南维</th>
                            <th>首次涨停</th>
                            <th class="left">封单额</th>
                            <th class="left">主力净流入</th>
                            <th class="left">成交额</th>
                            <th>换手率</th>
                            <th>量比</th>
                            <th>5日涨幅</th>
                            <th>市盈率</th>
                            <th>市净率</th>
                            <th class="left">标签</th>
                            <th class="left">关联理由</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="s in boardDetail.stocks" :key="s.code">
                            <td class="left">{{ s.code }}</td>
                            <td class="left">{{ s.name }}</td>
                            <td :class="pctClass(s.change_pct)">{{ fmtPct(s.change_pct) }}</td>
                            <td :class="s.board > 0 ? 'up' : ''">{{ s.board || 0 }}</td>
                            <td>
                              <span
                                v-if="granvilleMap[s.code] && granvilleMap[s.code].score != null"
                                class="gv-score"
                                :class="gvClass(granvilleMap[s.code].score)"
                                :title="gvTitle(s.code)"
                              >{{ granvilleMap[s.code].score }}·{{ gvShort(granvilleMap[s.code].rating) }}</span>
                              <span
                                v-else-if="granvilleMap[s.code] && granvilleMap[s.code].skipped"
                                class="dim-txt"
                                :title="granvilleMap[s.code].skipped"
                              >次新</span>
                              <span v-else class="dim-txt">-</span>
                            </td>
                            <td>{{ s.first_limit_time || '-' }}</td>
                            <td class="left">{{ fmtYi(s.limit_amount) }}</td>
                            <td class="left">{{ fmtYi(s.main_net_inflow) }}</td>
                            <td class="left">{{ fmtYi(s.amount) }}</td>
                            <td>{{ pctNoSign(s.turnover_rate) }}</td>
                            <td>{{ num2(s.volume_ratio) }}</td>
                            <td :class="pctClass(s.five_day_change)">{{ fmtPct(s.five_day_change) }}</td>
                            <td>{{ num2(s.pe_ratio) }}</td>
                            <td>{{ num2(s.pb_ratio) }}</td>
                            <td class="left">
                              <span v-for="l in s.special_labels || []" :key="l" class="stock-tag">{{ l }}</span>
                              <span v-if="!(s.special_labels || []).length">-</span>
                            </td>
                            <td class="left reason-cell" @click.stop="toggleReason(s.code)">
                              <span v-if="reasonOpen[s.code]">{{ s.relation_reason || '-' }}</span>
                              <span v-else>{{ reasonShort(s.relation_reason) }}</span>
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 每日成交额折线图：默认融资融券/深股通/沪股通，题材板块点「叠加」加入 -->
    <div class="panel">
      <h2>每日成交额趋势（亿）</h2>
      <div class="tk-trend-hint">
        默认显示融资融券余额、沪股通、深股通（若数据源已披露）· 在上方题材列表点「📈 叠加」把板块成交额加入 · 点击图例可开关单条线
        <span v-if="overlayCodes.size" class="tk-overlay-count">已叠加 {{ overlayCodes.size }} 个板块</span>
      </div>
      <div v-if="trendError" class="error">⚠ {{ trendError }}</div>
      <TrendChart
        v-else-if="trendDays.length"
        :series="[...baseSeries, ...overlaySeries]"
        unit="亿"
      />
      <div v-else class="empty">题材趋势数据加载中…</div>
    </div>
  </div>
</template>
