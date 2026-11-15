<script setup>
import { ref, computed, onMounted } from 'vue';
import { fetchConcepts, fetchConceptDetail, exportTablePdf } from '../api.js';

const concepts = ref([]);
const loading = ref(true);
const error = ref(null);
const search = ref('');
const sortKey = ref('company_count');
const sortDir = ref(-1); // -1 降序
const page = ref(1);
const pageSize = 50;

// 成分股弹窗
const modalVisible = ref(false);
const modalLoading = ref(false);
const modalConcept = ref(null);
const modalStocks = ref([]);
const modalIndustries = ref([]); // 关联行业板块（点击跳行业 url）
const stockSearch = ref('');
const stockSortKey = ref('float_mv');
const stockSortDir = ref(-1);

// 排序后的概念列表
const sorted = computed(() => {
  const arr = [...concepts.value];
  const key = sortKey.value;
  const dir = sortDir.value;
  arr.sort((a, b) => {
    const va = a[key] ?? 0;
    const vb = b[key] ?? 0;
    if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir;
    return String(va).localeCompare(String(vb)) * dir;
  });
  return arr;
});

// 搜索过滤
const filtered = computed(() => {
  const q = search.value.trim().toLowerCase();
  if (!q) return sorted.value;
  return sorted.value.filter((c) => c.name.toLowerCase().includes(q) || c.code.includes(q));
});

// 分页
const totalPages = computed(() => Math.ceil(filtered.value.length / pageSize));
const paged = computed(() => {
  const start = (page.value - 1) * pageSize;
  return filtered.value.slice(start, start + pageSize);
});

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
    // 数值比较（去掉"亿"等单位）
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

function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value *= -1;
  } else {
    sortKey.value = key;
    sortDir.value = -1;
  }
}

function sortIcon(key) {
  if (sortKey.value !== key) return '↕';
  return sortDir.value > 0 ? '↑' : '↓';
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

async function openConcept(c) {
  modalConcept.value = c;
  modalVisible.value = true;
  modalLoading.value = true;
  modalStocks.value = [];
  modalIndustries.value = [];
  stockSearch.value = '';
  try {
    const data = await fetchConceptDetail(c.code);
    modalStocks.value = data.stocks || [];
    modalIndustries.value = data.industries || [];
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
  modalIndustries.value = [];
}

function fmtPe(v) {
  const n = parseFloat(v);
  if (isNaN(n)) return '-';
  return n.toFixed(2);
}

function fmtCount(n) {
  if (n == null) return '-';
  return n;
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

onMounted(async () => {
  try {
    const data = await fetchConcepts();
    concepts.value = data.concepts || [];
  } catch (e) {
    error.value = e.message || '加载概念板块数据失败';
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="concept-view">
    <!-- 统计概览 -->
    <div class="panel" v-if="!loading && !error">
      <h2>同花顺概念板块</h2>
      <div class="stat-grid" style="margin-top: 12px">
        <div class="stat-card blue">
          <div class="stat-label">概念板块数</div>
          <div class="stat-value">{{ concepts.length }}</div>
        </div>
        <div class="stat-card gold">
          <div class="stat-label">含资金流板块</div>
          <div class="stat-value">{{ concepts.filter(c => c.company_count > 0).length }}</div>
        </div>
        <div class="stat-card green">
          <div class="stat-label">总成分股数</div>
          <div class="stat-value">70,264</div>
        </div>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="panel" v-if="!loading && !error">
      <div class="toolbar">
        <input
          class="search"
          v-model="search"
          placeholder="搜索概念板块名称或编号..."
        />
        <span class="toolbar-hint">共 {{ filtered.length }} 个板块</span>
      </div>
    </div>

    <!-- 概念列表 -->
    <div class="panel" v-if="!loading && !error">
      <div style="overflow-x: auto">
        <table>
          <thead>
            <tr>
              <th class="left" style="width: 40px">#</th>
              <th class="left sortable" @click="toggleSort('name')">
                概念名称 <span class="sort-ind">{{ sortIcon('name') }}</span>
              </th>
              <th class="sortable" @click="toggleSort('code')">
                编号 <span class="sort-ind">{{ sortIcon('code') }}</span>
              </th>
              <th class="sortable" @click="toggleSort('company_count')">
                公司家数 <span class="sort-ind">{{ sortIcon('company_count') }}</span>
              </th>
              <th style="width: 80px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(c, i) in paged" :key="c.code">
              <td class="left">{{ (page - 1) * pageSize + i + 1 }}</td>
              <td class="left">
                <a :href="c.url" target="_blank" class="concept-link">{{ c.name }}</a>
              </td>
              <td style="font-family: 'SF Mono', Menlo, monospace; font-size: 12px">{{ c.code }}</td>
              <td>{{ fmtCount(c.company_count) }}</td>
              <td>
                <button class="toggle-btn" @click="openConcept(c)">成分股</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <!-- 分页 -->
      <div class="pager" v-if="totalPages > 1">
        <button class="page-btn" :disabled="page <= 1" @click="page--">‹ 上一页</button>
        <span class="page-info">{{ page }} / {{ totalPages }}</span>
        <button class="page-btn" :disabled="page >= totalPages" @click="page++">下一页 ›</button>
      </div>
    </div>

    <!-- 加载 / 错误 -->
    <div class="loading" v-if="loading">加载中...</div>
    <div class="error" v-if="error">{{ error }}</div>

    <!-- 成分股弹窗 -->
    <div class="modal-mask" v-if="modalVisible" @click.self="closeModal">
      <div class="modal" style="width: min(900px, 100%)">
        <div class="modal-head">
          <span>
            <a v-if="modalConcept?.url" :href="modalConcept.url" target="_blank" class="concept-link">
              {{ modalConcept?.name }} ↗
            </a>
            <template v-else>{{ modalConcept?.name }}</template>
            — 成分股明细
          </span>
          <button class="modal-close" @click="closeModal">✕</button>
        </div>
        <div class="modal-body">
          <!-- 关联行业板块（点击跳行业详情页） -->
          <div class="modal-sec">
            <span class="modal-sec-title">关联行业板块（{{ modalIndustries.length }}）</span>
            <div class="ind-pills">
              <a
                v-for="ind in modalIndustries"
                :key="ind.code"
                :href="ind.url"
                target="_blank"
                class="ind-pill"
                :title="`${ind.name} · 重叠 ${ind.overlap} 只 / 共 ${ind.company_count} 只`"
              >{{ ind.name }} <b>{{ ind.overlap }}</b></a>
              <span v-if="!modalIndustries.length && !modalLoading" class="dim">无</span>
            </div>
          </div>
          <div class="toolbar" style="margin-bottom: 12px">
            <input
              class="search"
              v-model="stockSearch"
              placeholder="搜索股票名称或代码..."
            />
            <button class="pdf-btn" :disabled="exportingPdf || !filteredStocks.length" @click="exportPdf" title="将当前列表（含搜索/排序结果）导出为 PDF">
              {{ exportingPdf ? '生成中…' : '⬇ 导出PDF' }}
            </button>
            <span class="toolbar-hint">共 {{ filteredStocks.length }} 只 · 点击代码/名称跳同花顺个股页</span>
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
                    <a :href="s.url" target="_blank" class="code-link" :title="'打开同花顺个股页'">{{ s.code }}</a>
                  </td>
                  <td class="left">
                    <a :href="s.url" target="_blank" class="name-link" :title="'打开同花顺个股页'">{{ s.name }}</a>
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
</template>

<style scoped>
.concept-link {
  color: var(--blue);
  text-decoration: none;
  font-weight: 600;
}
.concept-link:hover {
  text-decoration: underline;
}
/* 弹窗: 关联行业板块 pill 区 */
.modal-sec {
  margin-bottom: 12px;
}
.modal-sec-title {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-dim);
  margin-bottom: 6px;
}
.ind-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.ind-pill {
  font-size: 11.5px;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 999px;
  text-decoration: none;
  color: #105cb3;
  border: 1px solid #9dcbfb;
  background: #f0f7ff;
  transition: all 0.12s;
}
.ind-pill b {
  font-weight: 800;
  opacity: 0.75;
  margin-left: 2px;
}
.ind-pill:hover {
  transform: translateY(-1px);
  box-shadow: 0 3px 8px rgba(0, 0, 0, 0.12);
}
/* 成分股代码/名称链接 */
.code-link {
  font-family: 'SF Mono', Menlo, monospace;
  font-size: 12px;
  color: var(--blue);
  text-decoration: none;
  font-weight: 600;
}
.code-link:hover {
  text-decoration: underline;
}
.name-link {
  color: var(--text);
  text-decoration: none;
  font-weight: 600;
}
.name-link:hover {
  color: var(--blue);
  text-decoration: underline;
}
.dim {
  color: var(--text-dim);
  font-size: 12px;
}
/* 导出 PDF 按钮 */
.pdf-btn {
  font-size: 12.5px;
  font-weight: 600;
  color: #fff;
  background: #16a34a;
  border: none;
  border-radius: 8px;
  padding: 7px 16px;
  cursor: pointer;
  white-space: nowrap;
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
.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 16px;
}
.page-btn {
  border: 1px solid var(--border);
  background: var(--card-2);
  color: var(--text-dim);
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}
.page-btn:hover:not(:disabled) {
  border-color: var(--blue);
  color: var(--blue);
}
.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.page-info {
  font-size: 13px;
  color: var(--text-dim);
}
</style>
