<script setup>
import { ref, computed, onMounted } from 'vue';
import { fetchIndustries, fetchIndustryStocks } from '../api.js';

// ===== 数据 =====
const loading = ref(true);
const error = ref(null);
const meta = ref(null);
const search = ref('');
const rawIndustries = ref([]);
const conceptRelations = ref([]); // [{code, concepts: [{name, code, company_count, overlap}]}]

// 行业 → 关联概念聚合，支持搜索过滤，按成分股数降序平铺
const industryTiles = computed(() => {
  const relMap = new Map();
  for (const r of conceptRelations.value) {
    relMap.set(r.code, r.concepts || []);
  }
  const q = search.value.trim().toLowerCase();
  return rawIndustries.value
    .map((ind) => ({
      ...ind,
      concepts: relMap.get(ind.code) || [],
    }))
    .filter((ind) => !q || ind.name.toLowerCase().includes(q) || ind.code.includes(q))
    .sort((a, b) => (b.company_count || 0) - (a.company_count || 0));
});

// ===== hover 浮层（跟随鼠标，列出行业关联的概念板块） =====
const hovered = ref(null);
const hoverX = ref(0);
const hoverY = ref(0);
const TIP_W = 300;

function onEnter(ind, e) {
  hovered.value = ind;
  moveTip(e);
}
function moveTip(e) {
  const PAD = 16;
  let x = e.clientX + PAD;
  if (x + TIP_W > window.innerWidth - 8) x = e.clientX - TIP_W - PAD;
  const maxH = 340;
  let y = e.clientY + PAD;
  if (y + maxH > window.innerHeight - 8) y = Math.max(8, window.innerHeight - maxH - 16);
  hoverX.value = x;
  hoverY.value = y;
}
function onLeave() {
  hovered.value = null;
}

// ===== 点击弹窗 =====
const modalVisible = ref(false);
const modalLoading = ref(false);
const modalIndustry = ref(null);
const modalStocks = ref([]);
const stockSearch = ref('');
const stockSortKey = ref('float_mv');
const stockSortDir = ref(-1);

async function openIndustry(ind) {
  modalIndustry.value = ind;
  modalVisible.value = true;
  modalLoading.value = true;
  modalStocks.value = [];
  stockSearch.value = '';
  stockSortKey.value = 'float_mv';
  stockSortDir.value = -1;
  try {
    const data = await fetchIndustryStocks(ind.code);
    modalStocks.value = data.stocks || [];
  } catch (e) {
    console.error('加载成分股失败:', e);
  } finally {
    modalLoading.value = false;
  }
}

function closeModal() {
  modalVisible.value = false;
  modalIndustry.value = null;
  modalStocks.value = [];
}

// 成分股排序过滤
const filteredStocks = computed(() => {
  let arr = [...modalStocks.value];
  const q = stockSearch.value.trim().toLowerCase();
  if (q) {
    arr = arr.filter(
      (s) => s.name.toLowerCase().includes(q) || s.code.includes(q)
    );
  }
  const key = stockSortKey.value;
  const dir = stockSortDir.value;
  arr.sort((a, b) => {
    let va = a[key] ?? 0;
    let vb = b[key] ?? 0;
    if (key === 'float_mv' || key === 'float_shares') {
      va = parseNum(va);
      vb = parseNum(vb);
    } else if (key === 'pe') {
      va = parseFloat(va) || 0;
      vb = parseFloat(vb) || 0;
    }
    return (va - vb) * dir;
  });
  return arr;
});

function parseNum(s) {
  if (typeof s === 'number') return s;
  const m = String(s).match(/([\d.]+)/);
  return m ? parseFloat(m[1]) : 0;
}

function toggleStockSort(key) {
  if (stockSortKey.value === key) {
    stockSortDir.value *= -1;
  } else {
    stockSortKey.value = key;
    stockSortDir.value = -1;
  }
}

function stockSortIcon(key) {
  if (stockSortKey.value !== key) return '↕';
  return stockSortDir.value > 0 ? '↑' : '↓';
}

function fmtPe(v) {
  const n = parseFloat(v);
  if (isNaN(n)) return '-';
  return n.toFixed(2);
}

// 行业热度分档（按成分股数）
function tileClass(ind) {
  const n = ind.company_count || 0;
  if (n >= 200) return 't3';
  if (n >= 80) return 't2';
  if (n >= 30) return 't1';
  return 't0';
}

onMounted(async () => {
  try {
    const data = await fetchIndustries();
    rawIndustries.value = data.industries || [];
    conceptRelations.value = data.conceptRelations || [];
    meta.value = data.meta || null;
  } catch (e) {
    error.value = e.message || '加载行业板块数据失败';
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="ind-view">
    <!-- 工具栏 -->
    <div class="panel">
      <div class="toolbar">
        <span class="toolbar-title">行业</span>
        <input class="search" v-model="search" placeholder="搜索行业名称/代码..." style="max-width: 220px" />
        <span class="toolbar-hint" v-if="meta">
          {{ industryTiles.length }} 个行业 · {{ meta.total_stocks || 0 }} 只个股
        </span>
        <span class="toolbar-hint" style="margin-left: auto">悬浮查看关联概念，点击查看详情</span>
      </div>
    </div>

    <!-- 行业平铺 -->
    <div class="tiles" v-if="!loading && !error">
      <div
        v-for="ind in industryTiles"
        :key="ind.code"
        class="tile"
        :class="tileClass(ind)"
        @mouseenter="onEnter(ind, $event)"
        @mousemove="moveTip($event)"
        @mouseleave="onLeave"
        @click="openIndustry(ind)"
      >
        <div class="tile-name" :title="ind.name">{{ ind.name }}</div>
        <div class="tile-meta">
          <span class="tile-count">{{ ind.company_count }} 只</span>
          <span class="tile-cons" v-if="ind.concepts.length">{{ ind.concepts.length }} 概念</span>
        </div>
      </div>
      <div v-if="!industryTiles.length" class="empty">无匹配行业</div>
    </div>

    <div class="loading" v-if="loading">加载中...</div>
    <div class="error" v-if="error">{{ error }}</div>

    <!-- hover 浮层：行业关联的概念板块列表 -->
    <Teleport to="body">
      <div class="ind-tip" v-if="hovered" :style="{ left: hoverX + 'px', top: hoverY + 'px' }">
        <div class="ind-tip-head">
          <span class="ind-tip-name">{{ hovered.name }}</span>
          <span class="ind-tip-code">{{ hovered.code }}</span>
        </div>
        <div class="ind-tip-sub">
          {{ hovered.company_count }} 只成分股 · 关联 {{ hovered.concepts.length }} 个概念
        </div>
        <div class="ind-tip-list" v-if="hovered.concepts.length">
          <div v-for="con in hovered.concepts.slice(0, 12)" :key="con.code" class="ind-tip-row">
            <span class="ind-tip-con">{{ con.name }}</span>
            <span class="ind-tip-ov">{{ con.overlap }} 只</span>
          </div>
          <div v-if="hovered.concepts.length > 12" class="ind-tip-more">
            …共关联 {{ hovered.concepts.length }} 个概念
          </div>
        </div>
        <div v-else class="ind-tip-none">暂无关联概念</div>
        <div class="ind-tip-click">点击查看详情</div>
      </div>
    </Teleport>

    <!-- 点击弹窗：关联概念 + 成分股（均可点击跳转） -->
    <div class="modal-mask" v-if="modalVisible" @click.self="closeModal">
      <div class="modal" style="width: min(1100px, 96vw)">
        <div class="modal-head">
          <span>
            <a
              v-if="modalIndustry?.url"
              :href="modalIndustry.url"
              target="_blank"
              class="industry-title-link"
              :title="'打开同花顺行业板块页'"
            >{{ modalIndustry?.name }} ↗</a>
            <template v-else>{{ modalIndustry?.name }}</template>
            — 详情
          </span>
          <button class="modal-close" @click="closeModal">✕</button>
        </div>
        <div class="modal-body">
          <div class="modal-split">
            <!-- 左侧：关联概念列表（点击跳概念板块页） -->
            <div class="modal-left">
              <div class="modal-section-title">关联概念（{{ modalIndustry?.concepts?.length || 0 }}）</div>
              <div class="con-list" v-if="modalIndustry?.concepts?.length">
                <a
                  v-for="con in modalIndustry.concepts"
                  :key="con.code"
                  :href="con.url"
                  target="_blank"
                  class="con-row"
                  :title="`${con.name} · 共 ${con.company_count} 只 · 重叠 ${con.overlap} 只`"
                >
                  <span class="con-name">{{ con.name }}</span>
                  <span class="con-ov">{{ con.overlap }} 只共有</span>
                  <span class="con-cnt">{{ con.company_count }} 只</span>
                </a>
              </div>
              <div v-else class="con-none">暂无关联概念</div>
            </div>
            <!-- 右侧：成分股 -->
            <div class="modal-right">
              <div class="modal-section-title">
                成分股（{{ modalIndustry?.company_count || 0 }}）
                <input
                  class="search stock-search"
                  v-model="stockSearch"
                  placeholder="搜索股票..."
                  style="max-width: 160px; margin-left: 8px"
                />
              </div>
              <div v-if="modalLoading" style="text-align: center; padding: 32px; color: var(--text-dim)">
                加载中...
              </div>
              <div v-else style="overflow-x: auto; max-height: 60vh">
                <table class="stock-table">
                  <thead>
                    <tr>
                      <th class="left" style="width: 36px">#</th>
                      <th class="left sortable" @click="toggleStockSort('code')">
                        代码 <span class="sort-ind">{{ stockSortIcon('code') }}</span>
                      </th>
                      <th class="left sortable" @click="toggleStockSort('name')">
                        名称 <span class="sort-ind">{{ stockSortIcon('name') }}</span>
                      </th>
                      <th class="sortable" @click="toggleStockSort('float_shares')">
                        流通股 <span class="sort-ind">{{ stockSortIcon('float_shares') }}</span>
                      </th>
                      <th class="sortable" @click="toggleStockSort('float_mv')">
                        流通市值 <span class="sort-ind">{{ stockSortIcon('float_mv') }}</span>
                      </th>
                      <th class="sortable" @click="toggleStockSort('pe')">
                        市盈率 <span class="sort-ind">{{ stockSortIcon('pe') }}</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(s, i) in filteredStocks" :key="s.code">
                      <td class="left">{{ i + 1 }}</td>
                      <td>
                        <a :href="s.url" target="_blank" class="stock-code-link" :title="'打开同花顺个股页'">{{ s.code }}</a>
                      </td>
                      <td class="left">
                        <a :href="s.url" target="_blank" class="stock-name-link" :title="'打开同花顺个股页'">{{ s.name }}</a>
                      </td>
                      <td>{{ s.float_shares }}</td>
                      <td>{{ s.float_mv }}</td>
                      <td :class="{ up: parseFloat(s.pe) > 0, down: parseFloat(s.pe) < 0 }">
                        {{ fmtPe(s.pe) }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ind-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.toolbar-title {
  font-weight: 700;
  font-size: 14px;
  color: var(--text);
  white-space: nowrap;
}

/* ===== 行业平铺 ===== */
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 10px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 14px;
}

.tile {
  border-radius: 10px;
  padding: 10px 12px;
  cursor: pointer;
  transition: transform 0.12s, box-shadow 0.12s;
  border: 1px solid transparent;
  min-width: 0;
}

.tile:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12);
  border-color: currentColor;
  z-index: 2;
}

/* 热度分档（成分股越多越深） */
.tile.t0 {
  background: #f0fdf4;
  color: #15803d;
}
.tile.t1 {
  background: #dcfce7;
  color: #166534;
}
.tile.t2 {
  background: #bbf7d0;
  color: #14532d;
}
.tile.t3 {
  background: #86efac;
  color: #052e16;
}

.tile-name {
  font-size: 13px;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tile-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 5px;
  font-size: 11px;
  opacity: 0.82;
}

.tile-count {
  font-weight: 600;
}

.tile-cons {
  padding: 0 6px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.55);
}

.empty {
  grid-column: 1 / -1;
  text-align: center;
  padding: 60px;
  color: var(--text-dim);
  font-size: 13px;
}

.loading,
.error {
  text-align: center;
  padding: 60px;
  color: var(--text-dim);
}

.error {
  color: #dc2626;
}

/* ===== hover 浮层 ===== */
.ind-tip {
  position: fixed;
  width: 300px;
  background: rgba(28, 32, 45, 0.95);
  color: #fff;
  border-radius: 12px;
  padding: 12px 14px;
  font-size: 12px;
  pointer-events: none;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
  z-index: 1200;
}

.ind-tip-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.ind-tip-name {
  font-size: 15px;
  font-weight: 700;
}

.ind-tip-code {
  font-size: 11px;
  opacity: 0.65;
  font-family: 'SF Mono', Menlo, monospace;
}

.ind-tip-sub {
  font-size: 11px;
  opacity: 0.75;
  margin: 4px 0 8px;
}

.ind-tip-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-height: 240px;
  overflow: hidden;
}

.ind-tip-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
}

.ind-tip-con {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ind-tip-ov {
  font-weight: 600;
  color: #86efac;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.ind-tip-more {
  text-align: center;
  opacity: 0.6;
  margin-top: 4px;
  font-size: 11px;
}

.ind-tip-none {
  opacity: 0.6;
  text-align: center;
  padding: 10px 0;
}

.ind-tip-click {
  text-align: center;
  opacity: 0.5;
  margin-top: 8px;
  font-size: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  padding-top: 6px;
}

/* ===== 弹窗 ===== */
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.modal {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.25);
  max-height: 88vh;
  display: flex;
  flex-direction: column;
}

.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
  font-size: 15px;
  font-weight: 700;
}

.modal-close {
  border: none;
  background: none;
  font-size: 18px;
  cursor: pointer;
  color: var(--text-dim);
  padding: 4px 8px;
  border-radius: 6px;
}

.modal-close:hover {
  background: var(--card-2);
  color: var(--text);
}

.modal-body {
  padding: 16px 20px;
  overflow-y: auto;
}

.modal-split {
  display: flex;
  gap: 20px;
}

.modal-left {
  width: 280px;
  flex-shrink: 0;
}

.modal-right {
  flex: 1;
  min-width: 0;
}

.modal-section-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
}

.stock-search {
  font-size: 12px !important;
  padding: 4px 8px !important;
}

.con-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 60vh;
  overflow-y: auto;
}

.con-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 8px;
  background: var(--card-2);
  font-size: 12px;
  text-decoration: none;
  color: inherit;
  transition: all 0.12s;
  border: 1px solid transparent;
}

.con-row:hover {
  border-color: var(--blue);
  transform: translateX(2px);
}

/* 弹窗标题/成分股链接 */
.industry-title-link {
  color: var(--blue);
  text-decoration: none;
  font-weight: 700;
}
.industry-title-link:hover {
  text-decoration: underline;
}
.stock-code-link {
  font-family: 'SF Mono', Menlo, monospace;
  font-size: 12px;
  color: var(--blue);
  text-decoration: none;
  font-weight: 600;
}
.stock-code-link:hover {
  text-decoration: underline;
}
.stock-name-link {
  color: var(--text);
  text-decoration: none;
  font-weight: 600;
}
.stock-name-link:hover {
  color: var(--blue);
  text-decoration: underline;
}

.con-name {
  flex: 1;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.con-ov {
  color: var(--blue);
  font-weight: 600;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.con-cnt {
  color: var(--text-dim);
  font-size: 11px;
  white-space: nowrap;
}

.con-none {
  color: var(--text-dim);
  font-size: 12px;
  text-align: center;
  padding: 24px 0;
}

.sort-ind {
  font-size: 10px;
  opacity: 0.5;
}

th.sortable {
  cursor: pointer;
  user-select: none;
}

th.sortable:hover {
  color: var(--blue);
}

.stock-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.stock-table th,
.stock-table td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.up {
  color: var(--rise);
}

.down {
  color: var(--fall);
}
</style>