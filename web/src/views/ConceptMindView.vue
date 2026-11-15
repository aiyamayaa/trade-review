<script setup>
import { ref, computed, onMounted } from 'vue';
import { fetchConceptMap } from '../api.js';

// ===== 数据 =====
const concepts = ref([]);
const loading = ref(true);
const error = ref(null);
const viewMode = ref('concept'); // 'concept' = 概念 → 成分股，'stock' = 个股 → 关联概念
const conceptSearch = ref('');
const stockSearch = ref('');

// 从概念数据中提取所有唯一个股
const allStocks = computed(() => {
  const map = new Map(); // code -> { code, name, concepts: [{name, code}] }
  for (const c of concepts.value) {
    for (const s of c.stocks || []) {
      if (map.has(s.code)) {
        map.get(s.code).concepts.push({ name: c.name, code: c.code });
      } else {
        map.set(s.code, { code: s.code, name: s.name, concepts: [{ name: c.name, code: c.code }] });
      }
    }
  }
  return [...map.values()].sort((a, b) => b.concepts.length - a.concepts.length);
});

// 搜索过滤后的个股
const filteredStocks = computed(() => {
  let arr = allStocks.value;
  const q = stockSearch.value.trim().toLowerCase();
  if (q) {
    arr = arr.filter((s) => s.name.toLowerCase().includes(q) || s.code.includes(q));
  }
  return arr;
});

// 搜索过滤后的概念（按成分股数降序）
const filteredConcepts = computed(() => {
  let arr = concepts.value;
  const q = conceptSearch.value.trim().toLowerCase();
  if (q) {
    arr = arr.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.code.includes(q) ||
        (c.stocks || []).some((s) => s.name.toLowerCase().includes(q) || s.code.includes(q)),
    );
  }
  return [...arr].sort((a, b) => (b.stocks?.length || 0) - (a.stocks?.length || 0));
});

// ===== 折叠状态（默认全部折叠） =====
const expandedConcepts = ref(new Set()); // 概念模式：key = 概念 code
const expandedStocks = ref(new Set()); // 个股模式：key = 个股 code

function toggleConcept(code) {
  const s = new Set(expandedConcepts.value);
  if (s.has(code)) s.delete(code);
  else s.add(code);
  expandedConcepts.value = s;
}
function toggleStock(code) {
  const s = new Set(expandedStocks.value);
  if (s.has(code)) s.delete(code);
  else s.add(code);
  expandedStocks.value = s;
}
function expandAll() {
  if (viewMode.value === 'concept') {
    expandedConcepts.value = new Set(filteredConcepts.value.map((c) => c.code));
  } else {
    expandedStocks.value = new Set(filteredStocks.value.map((s) => s.code));
  }
}
function collapseAll() {
  expandedConcepts.value = new Set();
  expandedStocks.value = new Set();
}

// 概念热度分档（按成分股数着色折叠块）
function conceptClass(c) {
  const n = c.stocks?.length || 0;
  if (n >= 200) return 't3';
  if (n >= 60) return 't2';
  if (n >= 20) return 't1';
  return 't0';
}
// 个股按关联概念数分档
function stockClass(s) {
  const n = s.concepts.length;
  if (n >= 5) return 't3';
  if (n >= 3) return 't2';
  if (n === 2) return 't1';
  return 't0';
}

// 概念关联强度：两个概念共同拥有的个股数
function conceptOverlap(c1, c2) {
  const s1 = new Set((c1.stocks || []).map((s) => s.code));
  let count = 0;
  for (const s of c2.stocks || []) {
    if (s1.has(s.code)) count++;
  }
  return count;
}

// 关联矩阵：展示概念之间的共有个股
const overlapMatrix = computed(() => {
  const top = [...concepts.value]
    .filter((c) => (c.stocks || []).length > 0)
    .sort((a, b) => (b.stocks?.length || 0) - (a.stocks?.length || 0))
    .slice(0, 12);
  if (top.length === 0) return { concepts: [], matrix: [] };

  const matrix = top.map((c1) =>
    top.map((c2) => {
      if (c1.code === c2.code) return c1.stocks?.length || 0;
      return conceptOverlap(c1, c2);
    }),
  );
  return { concepts: top, matrix };
});

onMounted(async () => {
  try {
    const data = await fetchConceptMap();
    concepts.value = data.concepts || [];
  } catch (e) {
    error.value = e.message || '加载概念映射数据失败';
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="mind-view">
    <!-- 工具栏 -->
    <div class="panel">
      <div class="toolbar">
        <div class="view-switch" style="margin-bottom: 0">
          <button :class="{ active: viewMode === 'concept' }" @click="viewMode = 'concept'">
            概念 → 成分股
          </button>
          <button :class="{ active: viewMode === 'stock' }" @click="viewMode = 'stock'">
            个股 → 概念
          </button>
        </div>
        <input
          class="search"
          v-if="viewMode === 'concept'"
          v-model="conceptSearch"
          placeholder="搜索概念 / 个股名称或代码..."
          style="max-width: 260px"
        />
        <input
          class="search"
          v-else
          v-model="stockSearch"
          placeholder="搜索个股名称或代码..."
          style="max-width: 260px"
        />
        <button class="toggle-btn" @click="expandAll">全部展开</button>
        <button class="toggle-btn" @click="collapseAll">全部折叠</button>
        <span class="toolbar-hint" style="margin-left: auto">
          <template v-if="viewMode === 'concept'">
            {{ filteredConcepts.length }} 个概念 · {{ concepts.length ? concepts.reduce((s, c) => s + (c.stocks?.length || 0), 0) : 0 }} 只成分股
          </template>
          <template v-else>
            {{ filteredStocks.length }} 只个股（按关联概念数降序）
          </template>
        </span>
      </div>
    </div>

    <div class="loading" v-if="loading">加载中...</div>
    <div class="error" v-if="error">{{ error }}</div>

    <!-- 主区域：折叠列表 + 关联矩阵 -->
    <div class="main-layout" v-if="!loading && !error">
      <!-- 折叠列表 -->
      <div class="fold-list">
        <!-- 概念模式：概念折叠块 → 成分股 -->
        <template v-if="viewMode === 'concept'">
          <div
            v-for="c in filteredConcepts"
            :key="c.code"
            class="fold-block"
            :class="conceptClass(c)"
          >
            <div class="fold-head" @click="toggleConcept(c.code)">
              <span class="fold-arrow" :class="{ open: expandedConcepts.has(c.code) }">▶</span>
              <span class="fold-name">{{ c.name }}</span>
              <span class="fold-count">{{ c.stocks?.length || 0 }} 只</span>
            </div>
            <div v-if="expandedConcepts.has(c.code)" class="fold-body">
              <span
                v-for="s in c.stocks || []"
                :key="s.code"
                class="stock-pill"
                :title="`${s.name} ${s.code}`"
              >
                <b>{{ s.name }}</b>
                <i>{{ s.code }}</i>
              </span>
              <span v-if="!(c.stocks || []).length" class="empty-hint">无成分股数据</span>
            </div>
          </div>
          <div v-if="!filteredConcepts.length" class="empty-hint">无匹配概念</div>
        </template>

        <!-- 个股模式：个股折叠块 → 关联概念 -->
        <template v-else>
          <div
            v-for="s in filteredStocks"
            :key="s.code"
            class="fold-block"
            :class="stockClass(s)"
          >
            <div class="fold-head" @click="toggleStock(s.code)">
              <span class="fold-arrow" :class="{ open: expandedStocks.has(s.code) }">▶</span>
              <span class="fold-name">{{ s.name }}</span>
              <span class="fold-code">{{ s.code }}</span>
              <span class="fold-count" :class="{ hot: s.concepts.length >= 3 }">
                {{ s.concepts.length }} 概念
              </span>
            </div>
            <div v-if="expandedStocks.has(s.code)" class="fold-body">
              <span v-for="c in s.concepts" :key="c.code" class="concept-pill">
                {{ c.name }}
              </span>
              <span v-if="!s.concepts.length" class="empty-hint">无关联概念</span>
            </div>
          </div>
          <div v-if="!filteredStocks.length" class="empty-hint">无匹配个股</div>
        </template>
      </div>

      <!-- 侧边：概念关联矩阵 -->
      <div class="side-panel">
        <div class="side-section" v-if="overlapMatrix.concepts.length > 0">
          <h3>概念关联矩阵（TOP12）</h3>
          <p class="side-desc">数值为两个概念共同拥有的个股数</p>
          <div class="matrix-wrap">
            <table class="matrix-table">
              <thead>
                <tr>
                  <th></th>
                  <th v-for="c in overlapMatrix.concepts" :key="c.code" class="matrix-th">
                    <span :title="c.name">{{ c.name.slice(0, 4) }}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, i) in overlapMatrix.matrix" :key="i">
                  <td class="matrix-td-label" :title="overlapMatrix.concepts[i].name">
                    {{ overlapMatrix.concepts[i].name.slice(0, 4) }}
                  </td>
                  <td
                    v-for="(val, j) in row"
                    :key="j"
                    class="matrix-td"
                    :class="{ diag: i === j, overlap: i !== j && val > 0 }"
                    :style="{ opacity: i === j ? 0.4 : Math.min(1, val / 30 + 0.3) }"
                  >
                    {{ i === j ? '' : val || '' }}
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
.main-layout {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 16px;
  align-items: start;
}

@media (max-width: 1000px) {
  .main-layout {
    grid-template-columns: 1fr;
  }
}

/* ===== 折叠列表 ===== */
.fold-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 14px;
  max-height: 82vh;
  overflow-y: auto;
}

.fold-block {
  border-radius: 10px;
  border: 1px solid var(--border);
  overflow: hidden;
}

.fold-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  cursor: pointer;
  user-select: none;
  transition: filter 0.12s;
}

.fold-head:hover {
  filter: brightness(0.96);
}

/* 热度分档底色 */
.fold-block.t0 .fold-head {
  background: #faf5ff;
}
.fold-block.t1 .fold-head {
  background: #f3e8ff;
}
.fold-block.t2 .fold-head {
  background: #ede2fe;
}
.fold-block.t3 .fold-head {
  background: #ddd0fb;
}

.fold-block.t0 .fold-name {
  color: #7c3aed;
}
.fold-block.t1 .fold-name {
  color: #6d28d9;
}
.fold-block.t2 .fold-name {
  color: #5b21b6;
}
.fold-block.t3 .fold-name {
  color: #4c1d95;
}

.fold-arrow {
  display: inline-block;
  font-size: 10px;
  color: var(--text-dim);
  transition: transform 0.18s;
  width: 14px;
  text-align: center;
}
.fold-arrow.open {
  transform: rotate(90deg);
}

.fold-name {
  font-size: 13px;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.fold-code {
  font-family: 'SF Mono', Menlo, monospace;
  font-size: 11px;
  color: var(--text-dim);
}

.fold-count {
  margin-left: auto;
  font-size: 11.5px;
  font-weight: 700;
  color: var(--text-dim);
  background: rgba(255, 255, 255, 0.6);
  border-radius: 10px;
  padding: 1px 9px;
  white-space: nowrap;
}

.fold-count.hot {
  color: #dc2626;
  background: #fee2e2;
}

.fold-body {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 12px 10px 34px;
  background: #fff;
  border-top: 1px dashed var(--border);
}

.stock-pill {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  font-size: 12px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 2px 10px;
}
.stock-pill b {
  font-weight: 600;
}
.stock-pill i {
  font-style: normal;
  font-size: 10.5px;
  color: var(--text-dim);
  font-family: 'SF Mono', Menlo, monospace;
}

.concept-pill {
  display: inline-block;
  font-size: 11.5px;
  font-weight: 600;
  color: #1890ff;
  background: #e8f3ff;
  border: 1px solid #bcd9f7;
  border-radius: 999px;
  padding: 2px 10px;
}

.empty-hint {
  color: var(--text-dim);
  font-size: 12.5px;
  padding: 40px;
  text-align: center;
  width: 100%;
}

/* ===== 侧边面板 ===== */
.side-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.side-section {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 16px;
}

.side-section h3 {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
}

.side-desc {
  font-size: 12px;
  color: var(--text-dim);
  margin: 0 0 10px;
}

/* 关联矩阵 */
.matrix-wrap {
  overflow-x: auto;
}

.matrix-table {
  font-size: 11px;
  width: auto;
}

.matrix-table th,
.matrix-table td {
  padding: 4px 6px;
  text-align: center;
  border: none;
  font-size: 11px;
}

.matrix-th {
  font-weight: 600;
  color: var(--blue);
  cursor: default;
}

.matrix-th span {
  display: inline-block;
  max-width: 36px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.matrix-td-label {
  font-weight: 600;
  color: var(--blue);
  text-align: right !important;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 40px;
}

.matrix-td {
  color: var(--text-dim);
  font-weight: 500;
  border-radius: 4px;
}

.matrix-td.diag {
  background: rgba(24, 144, 255, 0.08);
}

.matrix-td.overlap {
  color: #d97706;
  font-weight: 700;
}

.view-switch {
  display: flex;
  gap: 8px;
  margin-bottom: 0;
}

.view-switch button {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-dim);
  cursor: pointer;
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: var(--card-2);
  transition: all 0.15s;
}

.view-switch button:hover {
  border-color: var(--blue);
}

.view-switch button.active {
  color: #fff;
  background: var(--blue);
  border-color: var(--blue);
}
</style>
