<script setup>
import { ref, computed, onMounted } from 'vue';
import { fetchZtPoolDates, fetchZtPool } from '../api.js';

// 涨停板池页：data/zt_pool/（东财涨停/炸板/跌停三池，make fetch-zt-pool 每日采集）
const dates = ref([]);
const date = ref('');
const data = ref(null);
const loading = ref(false);
const error = ref('');
const pool = ref('涨停'); // 涨停 | 炸板 | 跌停
const sortKey = ref('连板数');

onMounted(async () => {
  try {
    const r = await fetchZtPoolDates();
    dates.value = r.dates || [];
    if (dates.value.length) load(dates.value[0]);
  } catch (e) {
    error.value = e.message;
  }
});

async function load(d) {
  date.value = d;
  loading.value = true;
  error.value = '';
  data.value = null;
  try {
    data.value = await fetchZtPool(d);
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

const fmtDate = (d) => (d && d.length === 8 ? `${d.slice(4, 6)}-${d.slice(6, 8)}` : d);

// 统计卡片
const stats = computed(() => {
  if (!data.value) return null;
  const zt = data.value['涨停'] || [];
  const zb = data.value['炸板'] || [];
  const dtp = data.value['跌停'] || [];
  const maxLbc = zt.length ? Math.max(...zt.map((i) => i['连板数'] || 0)) : 0;
  const totalFund = zt.reduce((s, i) => s + (i['封单资金(亿)'] || 0), 0);
  return { zt: zt.length, zb: zb.length, dtp: dtp.length, maxLbc, totalFund };
});

// 连板结构（如 1板:40只 2板:8只）
const lbcStat = computed(() => {
  const zt = (data.value && data.value['涨停']) || [];
  const m = new Map();
  for (const it of zt) m.set(it['连板数'] || 0, (m.get(it['连板数'] || 0) || 0) + 1);
  return [...m.entries()].sort((a, b) => b[0] - a[0]);
});

// 行业 TOP
const hyTop = computed(() => {
  const zt = (data.value && data.value['涨停']) || [];
  const m = new Map();
  for (const it of zt) {
    const k = it['行业板块'] || '其他';
    m.set(k, (m.get(k) || 0) + 1);
  }
  return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
});

// 当前池列表（涨停按排序键，炸板按炸板次数，跌停按涨跌幅）
const list = computed(() => {
  if (!data.value) return [];
  const items = data.value[pool.value] || [];
  if (pool.value === '涨停') {
    const key = sortKey.value;
    return [...items].sort((a, b) => {
      const va = a[key] ?? 0;
      const vb = b[key] ?? 0;
      if (typeof va === 'string' || typeof vb === 'string') {
        return String(vb).localeCompare(String(va));
      }
      return vb - va;
    });
  }
  if (pool.value === '炸板') return [...items].sort((a, b) => (b['炸板次数'] || 0) - (a['炸板次数'] || 0));
  return [...items].sort((a, b) => (a['涨跌幅%'] || 0) - (b['涨跌幅%'] || 0));
});

const ZT_COLS = ['代码', '名称', '连板数', '几日几板', '首次封板时间', '炸板次数', '封单资金(亿)', '成交额(亿)', '换手率%', '流通市值(亿)', '行业板块', '涨跌幅%'];
const ZB_COLS = ['代码', '名称', '涨跌幅%', '最新价', '炸板次数', '首次封板时间', '最后封板时间', '封单资金(亿)', '换手率%', '行业板块'];
const DT_COLS = ['代码', '名称', '涨跌幅%', '最新价', '换手率%', '流通市值(亿)', '行业板块', '所属市场'];

const cols = computed(() => (pool.value === '涨停' ? ZT_COLS : pool.value === '炸板' ? ZB_COLS : DT_COLS));

const SORTABLE = ['连板数', '封单资金(亿)', '成交额(亿)', '换手率%', '流通市值(亿)', '炸板次数', '涨跌幅%'];
function setSort(k) {
  if (pool.value !== '涨停') return;
  sortKey.value = k;
}
function numClass(k, v) {
  if (k === '涨跌幅%') return v >= 0 ? 'up' : 'down';
  return '';
}
</script>

<template>
  <div>
    <div class="panel" v-if="loading && !data">
      <div class="loading">加载中…</div>
    </div>
    <div class="panel" v-else-if="error">
      <div class="error">⚠ {{ error }}</div>
    </div>
    <div class="panel" v-else-if="!data">
      <div class="empty">
        暂无涨停池数据，请运行
        <code>make fetch-zt-pool</code>
        采集（东财接口仅返回当日数据，需每天执行积累）
      </div>
    </div>
    <template v-else>
      <!-- 统计卡片 -->
      <div class="panel">
        <h2>
          涨停板池（{{ data.meta.date }}）
          <span class="zp-sub">东财数据 · make fetch-zt-pool 每日采集</span>
        </h2>
        <div class="stat-grid" style="margin-bottom: 14px">
          <div class="stat-card red">
            <div class="stat-label">涨停</div>
            <div class="stat-value">{{ stats.zt }}</div>
            <div class="stat-sub">最高 {{ stats.maxLbc }} 连板</div>
          </div>
          <div class="stat-card gold">
            <div class="stat-label">炸板</div>
            <div class="stat-value">{{ stats.zb }}</div>
            <div class="stat-sub">涨停打开</div>
          </div>
          <div class="stat-card green">
            <div class="stat-label">跌停</div>
            <div class="stat-value">{{ stats.dtp }}</div>
          </div>
          <div class="stat-card blue">
            <div class="stat-label">封单资金合计</div>
            <div class="stat-value">{{ stats.totalFund.toFixed(1) }}<span class="zp-unit">亿</span></div>
          </div>
        </div>

        <!-- 连板结构 + 行业TOP -->
        <div class="zp-rows">
          <div class="zp-row">
            <span class="zp-row-label">连板结构</span>
            <span v-for="[k, v] in lbcStat" :key="k" class="ct-item" :class="k >= 3 ? 'ct-rank2' : 'ct-rank4'">
              {{ k }}板 <b>{{ v }}</b> 只
            </span>
          </div>
          <div class="zp-row">
            <span class="zp-row-label">行业 TOP</span>
            <span v-for="[k, v] in hyTop" :key="k" class="con-tag">{{ k }} {{ v }}</span>
          </div>
        </div>

        <!-- 日期切换 -->
        <div class="date-tabs" style="margin-top: 14px">
          <button
            v-for="d in dates"
            :key="d"
            class="date-tab"
            :class="{ active: d === date }"
            @click="load(d)"
          >
            {{ fmtDate(d) }}
          </button>
        </div>
      </div>

      <!-- 明细表 -->
      <div class="panel">
        <div class="toolbar">
          <div class="stock-tabs">
            <button :class="{ active: pool === '涨停' }" @click="pool = '涨停'">涨停（{{ stats.zt }}）</button>
            <button :class="{ active: pool === '炸板' }" @click="pool = '炸板'">炸板（{{ stats.zb }}）</button>
            <button :class="{ active: pool === '跌停' }" @click="pool = '跌停'">跌停（{{ stats.dtp }}）</button>
          </div>
          <span class="toolbar-hint" v-if="pool === '涨停'">点击表头排序（当前：{{ sortKey }}）</span>
        </div>

        <div style="overflow-x: auto">
          <table class="stock-table">
            <thead>
              <tr>
                <th
                  v-for="c in cols"
                  :key="c"
                  class="left"
                  :class="{ sortable: pool === '涨停' && SORTABLE.includes(c), active: sortKey === c }"
                  @click="pool === '涨停' && SORTABLE.includes(c) && setSort(c)"
                >
                  {{ c }}<span v-if="sortKey === c" class="sort-ind"> ▼</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="it in list" :key="it['代码']">
                <td v-for="c in cols" :key="c" class="left" :class="numClass(c, it[c])">
                  {{ it[c] }}
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="!list.length" class="empty">当日无{{ pool }}股</div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.zp-sub {
  font-size: 12px;
  color: var(--text-dim);
  font-weight: 400;
  margin-left: 10px;
}
.zp-unit {
  font-size: 13px;
  margin-left: 2px;
}
.zp-rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.zp-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.zp-row-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-dim);
  margin-right: 4px;
  white-space: nowrap;
}
th.sortable {
  cursor: pointer;
}
th.sortable:hover {
  color: var(--blue);
}
th.active {
  color: var(--blue);
}
</style>
