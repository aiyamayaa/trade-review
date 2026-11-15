<script setup>
import { ref, computed, onMounted } from 'vue';
import { fetchIndustryConceptRelations, fetchConceptDetail, exportTablePdf } from '../api.js';

// ===== 数据 =====
const loading = ref(true);
const error = ref(null);
const meta = ref(null);
const search = ref('');
const rawConcepts = ref([]);
const relations = ref([]);

// 概念 → 关联行业聚合（按 overlap 降序），支持搜索过滤，按公司数降序平铺
const conceptTiles = computed(() => {
  const byConcept = new Map(); // conCode -> [{name, code, company_count, overlap}]
  for (const r of relations.value) {
    const key = r.concept.code;
    if (!byConcept.has(key)) byConcept.set(key, []);
    byConcept.get(key).push({
      name: r.industry.name,
      code: r.industry.code,
      company_count: r.industry.company_count,
      overlap: r.overlap,
      url: r.industry.url,
    });
  }
  const q = search.value.trim().toLowerCase();
  return rawConcepts.value
    .map((c) => ({
      ...c,
      industries: (byConcept.get(c.code) || []).sort((a, b) => b.overlap - a.overlap),
    }))
    .filter((c) => !q || c.name.toLowerCase().includes(q) || c.code.includes(q))
    .sort((a, b) => (b.company_count || 0) - (a.company_count || 0));
});

// ===== hover 浮层（跟随鼠标，列出概念关联的行业板块） =====
const hovered = ref(null);
const hoverX = ref(0);
const hoverY = ref(0);
const TIP_W = 300;

function onEnter(con, e) {
  hovered.value = con;
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
const modalConcept = ref(null);
const modalStocks = ref([]);
const stockSearch = ref('');
const stockSortKey = ref('float_mv');
const stockSortDir = ref(-1);

async function openConcept(con) {
  modalConcept.value = con;
  modalVisible.value = true;
  modalLoading.value = true;
  modalStocks.value = [];
  stockSearch.value = '';
  stockSortKey.value = 'float_mv';
  stockSortDir.value = -1;
  try {
    // 详情接口：stocks 含个股页 url（industries 直接用 tile 聚合数据）
    const data = await fetchConceptDetail(con.code);
    modalStocks.value = data.stocks || [];
  } catch (e) {
    console.error('加载概念详情失败:', e);
  } finally {
    modalLoading.value = false;
  }
}

function closeModal() {
  modalVisible.value = false;
  modalConcept.value = null;
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

// ===== 一键导出 PDF（当前搜索/排序后的成分股视图） =====
const exportingPdf = ref(false);
async function exportPdf() {
  if (exportingPdf.value || !modalConcept.value) return;
  exportingPdf.value = true;
  try {
    const name = modalConcept.value.name || modalConcept.value.code;
    const columns = ['#', '代码', '名称', '流通股', '流通市值', '市盈率'];
    const rows = filteredStocks.value.map((s, i) => [
      i + 1, s.code, s.name, s.float_shares ?? '-', s.float_mv ?? '-', fmtPe(s.pe),
    ]);
    const meta = `共 ${rows.length} 只 · 导出于 ${new Date().toLocaleString('zh-CN')}`;
    await exportTablePdf(`${name} 概念成分股明细`, columns, rows, meta);
  } catch (e) {
    alert('导出失败：' + e.message);
  } finally {
    exportingPdf.value = false;
  }
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

// 概念热度分档（按成分股数）
function tileClass(c) {
  const n = c.company_count || 0;
  if (n >= 200) return 't3';
  if (n >= 60) return 't2';
  if (n >= 20) return 't1';
  return 't0';
}

onMounted(async () => {
  try {
    const data = await fetchIndustryConceptRelations(1);
    rawConcepts.value = data.concepts || [];
    relations.value = data.relations || [];
    meta.value = data.meta || null;
  } catch (e) {
    error.value = e.message || '加载行业-概念关联数据失败';
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="ic-view">
    <!-- 工具栏 -->
    <div class="panel">
      <div class="toolbar">
<span class="toolbar-title">概念</span>
        <input class="search" v-model="search" placeholder="搜索概念名称/代码..." style="max-width: 220px" />
        <span class="toolbar-hint" v-if="meta">
          {{ conceptTiles.length }} 个概念 · {{ meta.industry_count }} 个行业 · {{ meta.relation_count }} 条关联
        </span>
        <span class="toolbar-hint" style="margin-left: auto">悬浮查看关联行业，点击查看详情</span>
      </div>
    </div>

    <!-- 概念平铺 -->
    <div class="tiles" v-if="!loading && !error">
      <div
        v-for="c in conceptTiles"
        :key="c.code"
        class="tile"
        :class="tileClass(c)"
        @mouseenter="onEnter(c, $event)"
        @mousemove="moveTip($event)"
        @mouseleave="onLeave"
        @click="openConcept(c)"
      >
        <div class="tile-name" :title="c.name">{{ c.name }}</div>
        <div class="tile-meta">
          <span class="tile-count">{{ c.company_count }} 只</span>
          <span class="tile-inds" v-if="c.industries.length">{{ c.industries.length }} 行业</span>
        </div>
      </div>
      <div v-if="!conceptTiles.length" class="empty">无匹配概念</div>
    </div>

    <div class="loading" v-if="loading">加载中...</div>
    <div class="error" v-if="error">{{ error }}</div>

    <!-- hover 浮层：概念关联的行业板块列表 -->
    <Teleport to="body">
      <div class="ic-tip" v-if="hovered" :style="{ left: hoverX + 'px', top: hoverY + 'px' }">
        <div class="ic-tip-head">
          <span class="ic-tip-name">{{ hovered.name }}</span>
          <span class="ic-tip-code">{{ hovered.code }}</span>
        </div>
        <div class="ic-tip-sub">
          {{ hovered.company_count }} 只成分股 · 关联 {{ hovered.industries.length }} 个行业
        </div>
        <div class="ic-tip-list" v-if="hovered.industries.length">
          <div v-for="ind in hovered.industries.slice(0, 12)" :key="ind.code" class="ic-tip-row">
            <span class="ic-tip-ind">{{ ind.name }}</span>
            <span class="ic-tip-ov">{{ ind.overlap }} 只</span>
          </div>
          <div v-if="hovered.industries.length > 12" class="ic-tip-more">
            …共关联 {{ hovered.industries.length }} 个行业
          </div>
        </div>
        <div v-else class="ic-tip-none">暂无关联行业</div>
        <div class="ic-tip-click">点击查看详情</div>
      </div>
    </Teleport>

    <!-- 点击弹窗：关联行业 + 成分股（均可点击跳转） -->
    <div class="modal-mask" v-if="modalVisible" @click.self="closeModal">
      <div class="modal" style="width: min(1100px, 96vw)">
        <div class="modal-head">
          <span>
            <a
              v-if="modalConcept?.url"
              :href="modalConcept.url"
              target="_blank"
              class="concept-title-link"
              :title="'打开同花顺概念板块页'"
            >{{ modalConcept?.name }} ↗</a>
            <template v-else>{{ modalConcept?.name }}</template>
            — 详情
          </span>
          <div class="modal-head-actions">
            <a
              v-if="modalConcept?.url"
              :href="modalConcept.url"
              target="_blank"
              class="modal-open-btn"
              title="在新标签页打开同花顺概念板块"
            >打开概念页 ↗</a>
            <button class="modal-close" @click="closeModal">✕</button>
          </div>
        </div>
        <div class="modal-body">
          <div class="modal-split">
            <!-- 左侧：关联行业列表（点击跳行业板块页） -->
            <div class="modal-left">
              <div class="modal-section-title">关联行业（{{ modalConcept?.industries?.length || 0 }}）</div>
              <div class="ind-list" v-if="modalConcept?.industries?.length">
                <a
                  v-for="ind in modalConcept.industries"
                  :key="ind.code"
                  :href="ind.url"
                  target="_blank"
                  class="ind-row"
                  :title="`${ind.name} · 共 ${ind.company_count} 只 · 重叠 ${ind.overlap} 只`"
                >
                  <span class="ind-name">{{ ind.name }}</span>
                  <span class="ind-ov">{{ ind.overlap }} 只共有</span>
                  <span class="ind-cnt">{{ ind.company_count }} 只</span>
                </a>
              </div>
              <div v-else class="ind-none">暂无关联行业</div>
            </div>
            <!-- 右侧：成分股（点击代码/名称跳个股页） -->
            <div class="modal-right">
              <div class="modal-section-title">
                成分股（{{ modalConcept?.company_count || 0 }}）
                <input
                  class="search stock-search"
                  v-model="stockSearch"
                  placeholder="搜索股票..."
                  style="max-width: 160px; margin-left: 8px"
                />
                <button class="pdf-btn" :disabled="exportingPdf || !filteredStocks.length" @click="exportPdf" title="将当前列表（含搜索/排序结果）导出为 PDF">
                  {{ exportingPdf ? '生成中…' : '⬇ 导出PDF' }}
                </button>
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
.ic-view {
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

/* 弹窗标题/成分股链接 */
.concept-title-link {
  color: var(--blue);
  text-decoration: none;
  font-weight: 700;
}
.concept-title-link:hover {
  text-decoration: underline;
}
.modal-head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.modal-open-btn {
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  background: var(--blue);
  text-decoration: none;
  padding: 5px 14px;
  border-radius: 14px;
  transition: all 0.15s;
  white-space: nowrap;
}
.modal-open-btn:hover {
  filter: brightness(1.08);
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.35);
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

/* ===== 概念平铺 ===== */
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
  background: #faf5ff;
  color: #7c3aed;
}
.tile.t1 {
  background: #f3e8ff;
  color: #6d28d9;
}
.tile.t2 {
  background: #ede2fe;
  color: #5b21b6;
}
.tile.t3 {
  background: #ddd0fb;
  color: #4c1d95;
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

.tile-inds {
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
.ic-tip {
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

.ic-tip-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.ic-tip-name {
  font-size: 15px;
  font-weight: 700;
}

.ic-tip-code {
  font-size: 11px;
  opacity: 0.65;
  font-family: 'SF Mono', Menlo, monospace;
}

.ic-tip-sub {
  font-size: 11px;
  opacity: 0.75;
  margin: 4px 0 8px;
}

.ic-tip-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-height: 240px;
  overflow: hidden;
}

.ic-tip-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
}

.ic-tip-ind {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ic-tip-ov {
  font-weight: 600;
  color: #93c5fd;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.ic-tip-more {
  text-align: center;
  opacity: 0.6;
  margin-top: 4px;
  font-size: 11px;
}

.ic-tip-none {
  opacity: 0.6;
  text-align: center;
  padding: 10px 0;
}

.ic-tip-click {
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
/* 导出 PDF 按钮 */
.pdf-btn {
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  background: #16a34a;
  border: none;
  border-radius: 8px;
  padding: 5px 14px;
  cursor: pointer;
  white-space: nowrap;
  margin-left: 8px;
  transition: all 0.15s;
}
.pdf-btn:hover:not(:disabled) {
  filter: brightness(1.08);
  box-shadow: 0 2px 8px rgba(22, 163, 74, 0.35);
}
.pdf-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.stock-search {
  font-size: 12px !important;
  padding: 4px 8px !important;
}

.ind-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 60vh;
  overflow-y: auto;
}

.ind-row {
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

.ind-row:hover {
  border-color: var(--blue);
  transform: translateX(2px);
}

.ind-name {
  flex: 1;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ind-ov {
  color: var(--blue);
  font-weight: 600;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.ind-cnt {
  color: var(--text-dim);
  font-size: 11px;
  white-space: nowrap;
}

.ind-none {
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
