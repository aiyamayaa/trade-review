<script setup>
import { ref, computed, onMounted } from 'vue';
import { fetchStocks } from '../api.js';

// ===== 数据 =====
const loading = ref(true);
const error = ref(null);
const meta = ref(null);
const allStocks = ref([]);

const search = ref('');
const sortKey = ref('code');
const sortAsc = ref(true);
const page = ref(1);
const PAGE_SIZE = 50;

// 可排序列（前 4 列）
const SORT_COLS = [
  { key: 'code', label: '个股代码' },
  { key: 'name', label: '名称' },
  { key: 'float_mv', label: '流通市值', numeric: true },
  { key: 'pe', label: '市盈率', numeric: true },
];

function numVal(v, isPe) {
  const n = parseFloat(v);
  if (Number.isNaN(n)) return isPe ? Infinity : -1;
  return n;
}

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase();
  let arr = allStocks.value;
  if (q) {
    arr = arr.filter(
      (s) =>
        s.code.includes(q) ||
        (s.name || '').toLowerCase().includes(q) ||
        (s.industries || []).some((i) => (i.name || '').toLowerCase().includes(q)) ||
        (s.concepts || []).some((c) => (c.name || '').toLowerCase().includes(q)),
    );
  }
  const key = sortKey.value;
  const col = SORT_COLS.find((c) => c.key === key);
  const dir = sortAsc.value ? 1 : -1;
  arr = [...arr].sort((a, b) => {
    let va, vb;
    if (col && col.numeric) {
      va = numVal(a[key], key === 'pe');
      vb = numVal(b[key], key === 'pe');
    } else {
      va = String(a[key] || '');
      vb = String(b[key] || '');
    }
    if (va < vb) return -1 * dir;
    if (va > vb) return 1 * dir;
    return 0;
  });
  return arr;
});

const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / PAGE_SIZE)));

const paged = computed(() => {
  const p = Math.min(page.value, totalPages.value);
  return filtered.value.slice((p - 1) * PAGE_SIZE, p * PAGE_SIZE);
});

function toggleSort(key) {
  if (sortKey.value === key) {
    sortAsc.value = !sortAsc.value;
  } else {
    sortKey.value = key;
    sortAsc.value = key === 'code' || key === 'name';
  }
  page.value = 1;
}

onMounted(async () => {
  try {
    const d = await fetchStocks();
    meta.value = d.meta || null;
    allStocks.value = d.stocks || [];
  } catch (e) {
    error.value = e.message || '加载个股信息失败';
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="si-view">
    <!-- 统计卡 -->
    <div class="panel" v-if="meta">
      <div class="stats">
        <div class="stat">
          <span class="stat-num">{{ meta.stock_count }}</span>
          <span class="stat-label">总个股</span>
        </div>
        <div class="stat">
          <span class="stat-num">{{ meta.stock_count - (meta.stats?.no_industry || 0) }}</span>
          <span class="stat-label">有行业归属</span>
        </div>
        <div class="stat">
          <span class="stat-num">{{ meta.stock_count - (meta.stats?.no_concept || 0) }}</span>
          <span class="stat-label">有概念关联</span>
        </div>
        <div class="stat">
          <span class="stat-num">{{ meta.stats?.multi_industry ?? '-' }}</span>
          <span class="stat-label">多行业归属</span>
        </div>
        <div class="stat-time">数据生成于 {{ meta.generated_at }}</div>
      </div>
    </div>

    <!-- 工具栏 + 表格 -->
    <div class="panel">
      <div class="toolbar">
        <span class="toolbar-title">个股信息</span>
        <input class="search" v-model="search" @input="page = 1" placeholder="搜索代码 / 名称 / 行业 / 概念..." />
        <span class="toolbar-hint">{{ filtered.length }} 只</span>
      </div>

      <div class="loading" v-if="loading">加载中...</div>
      <div class="error" v-if="error">{{ error }}</div>

      <table v-if="!loading && !error" class="si-table">
        <thead>
          <tr>
            <th
              v-for="col in SORT_COLS"
              :key="col.key"
              :class="{ active: sortKey === col.key, left: !col.numeric }"
              @click="toggleSort(col.key)"
            >
              {{ col.label }}
              <span v-if="sortKey === col.key" class="arrow">{{ sortAsc ? '↑' : '↓' }}</span>
            </th>
            <th class="left pills-col">关联行业板块</th>
            <th class="left pills-col">关联概念板块</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in paged" :key="s.code">
            <td>
              <a :href="s.url" target="_blank" class="code-link mono" :title="'打开同花顺个股页'">{{ s.code }}</a>
            </td>
            <td class="left">
              <a :href="s.url" target="_blank" class="name-link" :title="'打开同花顺个股页'">{{ s.name }}</a>
            </td>
            <td>{{ s.float_mv || '-' }}</td>
            <td :class="parseFloat(s.pe) < 0 ? 'neg' : ''">{{ s.pe || '-' }}</td>
            <td class="left pills-cell">
              <template v-if="s.industries.length">
                <a
                  v-for="ind in s.industries"
                  :key="ind.name"
                  :href="ind.url"
                  target="_blank"
                  class="pill ind"
                  :title="`${ind.name} · ${ind.company_count ?? '-'} 只成分股`"
                >{{ ind.name }}</a>
              </template>
              <span v-else class="dim">-</span>
            </td>
            <td class="left pills-cell">
              <template v-if="s.concepts.length">
                <a
                  v-for="con in s.concepts"
                  :key="con.name"
                  :href="con.url"
                  target="_blank"
                  class="pill con"
                  :title="`${con.name} · ${con.company_count ?? '-'} 只成分股`"
                >{{ con.name }}</a>
              </template>
              <span v-else class="dim">-</span>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 分页 -->
      <div class="pager" v-if="!loading && !error && totalPages > 1">
        <button :disabled="page <= 1" @click="page--">‹ 上一页</button>
        <span class="page-info">第 {{ page }} / {{ totalPages }} 页</span>
        <button :disabled="page >= totalPages" @click="page++">下一页 ›</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.si-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 统计卡 */
.stats {
  display: flex;
  align-items: center;
  gap: 32px;
  flex-wrap: wrap;
}
.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.stat-num {
  font-size: 22px;
  font-weight: 800;
  color: var(--blue);
  font-variant-numeric: tabular-nums;
}
.stat-label {
  font-size: 12px;
  color: var(--text-dim);
}
.stat-time {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-dim);
}

/* 工具栏 */
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.toolbar-title {
  font-weight: 700;
  font-size: 14px;
}
.toolbar-hint {
  font-size: 12px;
  color: var(--text-dim);
}

/* 表格 */
.si-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.si-table th {
  position: sticky;
  top: 0;
  background: var(--card);
  z-index: 1;
  font-size: 11.5px;
  color: var(--text-dim);
  font-weight: 600;
  text-align: right;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}
.si-table th.pills-col {
  cursor: default;
  min-width: 220px;
}
.si-table th.left,
.si-table td.left {
  text-align: left;
}
.si-table th.active {
  color: var(--blue);
}
.si-table th:hover:not(.pills-col) {
  color: var(--blue);
}
.arrow {
  font-size: 10px;
}
.si-table tbody tr {
  transition: background 0.1s;
}
.si-table tbody tr:hover {
  background: var(--card-2);
}
.si-table td {
  padding: 8px 10px;
  text-align: right;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  vertical-align: middle;
}

.mono {
  font-family: 'SF Mono', Menlo, monospace;
  font-size: 11.5px;
}
.dim {
  color: var(--text-dim);
}
.neg {
  color: var(--green);
}
.code-link {
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

/* 行业/概念 pill 平铺 */
.pills-cell {
  white-space: normal !important;
  min-width: 200px;
  max-width: 420px;
}
.pill {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 1px 9px;
  border-radius: 999px;
  text-decoration: none;
  border: 1px solid;
  margin: 1px 2px;
  white-space: nowrap;
  transition: all 0.12s;
}
.pill.ind {
  color: #105cb3;
  border-color: #9dcbfb;
  background: #f0f7ff;
}
.pill.con {
  color: #6d28d9;
  border-color: #c4a3e9;
  background: #f5ebfc;
}
.pill:hover {
  transform: translateY(-1px);
  box-shadow: 0 3px 8px rgba(0, 0, 0, 0.12);
}

/* 分页 */
.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  margin-top: 14px;
}
.pager button {
  font-size: 12px;
  padding: 5px 14px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--card-2);
  cursor: pointer;
  color: var(--text-dim);
  font-weight: 600;
}
.pager button:hover:not(:disabled) {
  color: #fff;
  background: var(--blue);
  border-color: var(--blue);
}
.pager button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.page-info {
  font-size: 12px;
  color: var(--text-dim);
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
</style>
