<script setup>
import { ref, computed, watch, onMounted } from 'vue';
import { fetchTicaiAllTrend, fetchTicaiBoardDetailTrend, fetchMarketDay } from '../api.js';
import { fmtYi, fmtPct, formatDate } from '../utils.js';
import TrendChart from '../components/TrendChart.vue';

const json = ref(null);
const error = ref('');
const loading = ref(false);
const hoveredBoard = ref('');

// 题材详情弹框
const detailOpen = ref(false);
const detail = ref(null);
const detailLoading = ref(false);
const detailError = ref('');
const selectedDate = ref('');

// 全市场单日行情（点击日期后按需加载）
const marketDay = ref(null);
const marketLoading = ref(false);
const marketError = ref('');

onMounted(load);

async function load() {
  loading.value = true;
  error.value = '';
  try {
    json.value = await fetchTicaiAllTrend();
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

const allDays = computed(() => (json.value?.days || []).map((d) => ({
  date: d.date,
  boards: d.boards || [],
})));

const rangeText = computed(() => {
  if (!allDays.value.length) return '';
  return `${formatDate(allDays.value[0].date)} ~ ${formatDate(allDays.value[allDays.value.length - 1].date)}`;
});

const LINE_COLORS = [
  '#1890ff', '#f5a623', '#52c41a', '#9254de',
  '#13c2c2', '#eb2f96', '#fa8c16', '#e9a23b',
];

// 收集每日按某字段排名 top N 的题材（去重集合，返回 code）
function collectTopCodes(topN, key, abs = false) {
  const set = new Set();
  allDays.value.forEach((d) => {
    d.boards
      .filter((b) => b[key] != null)
      .sort((a, b) => {
        const va = abs ? Math.abs(a[key]) : a[key];
        const vb = abs ? Math.abs(b[key]) : b[key];
        return vb - va;
      })
      .slice(0, topN)
      .forEach((b) => set.add(b.code));
  });
  return [...set];
}

function codeName(code) {
  for (const d of allDays.value) {
    const b = d.boards.find((x) => x.code === code);
    if (b) return b.name;
  }
  return code;
}

// 各题材总成交额变化趋势（亿）
const amtSeries = computed(() =>
  collectTopCodes(8, 'amount').map((code, i) => ({
    name: codeName(code),
    color: LINE_COLORS[i % LINE_COLORS.length],
    points: allDays.value.map((d) => {
      const b = d.boards.find((x) => x.code === code);
      return {
        x: formatDate(d.date),
        y: b?.amount != null ? Number(b.amount) / 1e8 : null,
      };
    }),
  }))
);

// 各题材主力净流入变化趋势（亿）
const netFlowSeries = computed(() =>
  collectTopCodes(8, 'main_net_inflow', true).map((code, i) => ({
    name: codeName(code),
    color: LINE_COLORS[i % LINE_COLORS.length],
    points: allDays.value.map((d) => {
      const b = d.boards.find((x) => x.code === code);
      return {
        x: formatDate(d.date),
        y: b?.main_net_inflow != null ? Number(b.main_net_inflow) / 1e8 : null,
      };
    }),
  }))
);

// 各题材每日涨跌幅变化趋势（%）
const pctSeries = computed(() =>
  collectTopCodes(8, 'change_pct', true).map((code, i) => ({
    name: codeName(code),
    color: LINE_COLORS[i % LINE_COLORS.length],
    points: allDays.value.map((d) => {
      const b = d.boards.find((x) => x.code === code);
      return {
        x: formatDate(d.date),
        y: b?.change_pct != null ? Number(b.change_pct) : null,
      };
    }),
  }))
);

// 每天涨跌幅前5题材（涨 + 跌）
const dailyTop5 = computed(() =>
  allDays.value.map((d) => {
    const entries = d.boards.filter((b) => b.change_pct != null);
    const gain = [...entries]
      .sort((a, b) => b.change_pct - a.change_pct)
      .slice(0, 5);
    const loss = [...entries]
      .sort((a, b) => a.change_pct - b.change_pct)
      .slice(0, 5);
    return { date: d.date, gain, loss };
  })
);

// 每天成交额前5题材
const dailyAmtTop5 = computed(() =>
  allDays.value.map((d) => {
    const top = d.boards
      .filter((b) => b.amount != null)
      .sort((a, b) => b.amount - a.amount)
      .slice(0, 5);
    return { date: d.date, top };
  })
);

// 悬浮高亮
function setHoverBoard(name) {
  hoveredBoard.value = name || '';
}
function tagHlClass(name) {
  if (!hoveredBoard.value) return '';
  return hoveredBoard.value === name ? 'hl' : 'dim';
}

// ===== 题材详情弹框 =====
async function openDetail(code) {
  detailOpen.value = true;
  detailLoading.value = true;
  detailError.value = '';
  detail.value = null;
  selectedDate.value = '';
  marketDay.value = null;
  try {
    const d = await fetchTicaiBoardDetailTrend(code);
    detail.value = d;
    if (d.days && d.days.length) selectedDate.value = d.days[d.days.length - 1].date;
  } catch (e) {
    detailError.value = e.message;
  } finally {
    detailLoading.value = false;
  }
}
function closeDetail() {
  detailOpen.value = false;
  detail.value = null;
  selectedDate.value = '';
  marketDay.value = null;
}

// 加载某日全市场行情
async function loadMarketDay(date) {
  if (!date) return;
  marketLoading.value = true;
  marketError.value = '';
  marketDay.value = null;
  try {
    marketDay.value = await fetchMarketDay(date);
  } catch (e) {
    marketError.value = e.message;
  } finally {
    marketLoading.value = false;
  }
}
// 选中日期变化时自动加载当日全市场行情
watch(selectedDate, (d) => loadMarketDay(d));

// 图1：该题材每日涨跌幅
const detailPctSeries = computed(() => {
  if (!detail.value) return [];
  return [{
    name: '涨跌幅',
    color: '#f5a623',
    points: detail.value.days.map((d) => ({ x: formatDate(d.date), y: d.change_pct })),
  }];
});

// 图2：每日涨跌停数量（涨停 = limit_up_count，跌停 = 跌幅≤-9%统计）
const detailLimitSeries = computed(() => {
  if (!detail.value) return [];
  const days = detail.value.days;
  return [
    { name: '涨停数', color: '#dc2626', points: days.map((d) => ({ x: formatDate(d.date), y: d.limit_up_count })) },
    { name: '跌停数', color: '#16a34a', points: days.map((d) => ({ x: formatDate(d.date), y: d.limit_down_count })) },
  ];
});

// 全市场涨 / 跌超 9% 个股
const marketUp = computed(() =>
  (marketDay.value?.stocks || [])
    .filter((s) => s.change_pct != null && s.change_pct >= 9)
    .sort((a, b) => b.change_pct - a.change_pct)
);
const marketDown = computed(() =>
  (marketDay.value?.stocks || [])
    .filter((s) => s.change_pct != null && s.change_pct <= -9)
    .sort((a, b) => a.change_pct - b.change_pct)
);
</script>

<template>
  <div v-if="loading" class="loading">加载中…</div>
  <div v-else-if="error" class="error">⚠ {{ error }}</div>
  <div v-else>
    <div class="panel">
      <h2>
        题材趋势（{{ rangeText }}）
        <span class="lk-sub">点击「每天涨跌幅前5题材」中的题材，可查看该题材详情</span>
      </h2>

      <div>
        <h3 style="color: var(--blue)">各题材总成交额变化趋势（亿）</h3>
        <TrendChart :series="amtSeries" unit="亿" />
      </div>

      <div style="margin-top: 20px">
        <h3 style="color: var(--red)">各题材主力净流入变化趋势（亿）</h3>
        <TrendChart :series="netFlowSeries" unit="亿" :show-zero-line="true" />
      </div>

      <div style="margin-top: 20px">
        <h3 style="color: var(--gold)">各题材每日涨跌幅变化趋势（%）</h3>
        <TrendChart :series="pctSeries" unit="%" :show-zero-line="true" />
      </div>

      <div style="margin-top: 20px">
        <h3 style="color: var(--red)">每天涨跌幅前5题材（点击查看详情）</h3>
        <div class="tl-wrap">
          <div class="tl">
            <div v-for="d in dailyTop5" :key="d.date" class="tl-col">
              <div class="tl-side tl-gain">
                <span
                  v-for="t in d.gain"
                  :key="'g' + t.code"
                  class="dg-tag clickable"
                  :class="tagHlClass(t.name)"
                  :title="'点击查看 ' + t.name + ' 详情'"
                  @mouseenter="setHoverBoard(t.name)"
                  @mouseleave="setHoverBoard('')"
                  @click="openDetail(t.code)"
                >
                  {{ t.name }} <b class="up">{{ fmtPct(t.change_pct) }}</b>
                </span>
              </div>
              <div class="tl-axis">
                <span class="tl-dot"></span>
                <span class="tl-date">{{ formatDate(d.date) }}</span>
              </div>
              <div class="tl-side tl-loss">
                <span
                  v-for="t in d.loss"
                  :key="'l' + t.code"
                  class="dg-tag clickable"
                  :class="tagHlClass(t.name)"
                  :title="'点击查看 ' + t.name + ' 详情'"
                  @mouseenter="setHoverBoard(t.name)"
                  @mouseleave="setHoverBoard('')"
                  @click="openDetail(t.code)"
                >
                  {{ t.name }} <b class="down">{{ fmtPct(t.change_pct) }}</b>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div style="margin-top: 20px">
        <h3 style="color: var(--blue)">每天成交额前5题材</h3>
        <div class="tl-wrap">
          <div class="tl">
            <div v-for="d in dailyAmtTop5" :key="d.date" class="tl-col">
              <div class="tl-side tl-amt">
                <span
                  v-for="t in d.top"
                  :key="t.code"
                  class="dg-tag"
                  :class="tagHlClass(t.name)"
                  @mouseenter="setHoverBoard(t.name)"
                  @mouseleave="setHoverBoard('')"
                >
                  {{ t.name }} <b class="amt">{{ fmtYi(t.amount) }}</b>
                </span>
              </div>
              <div class="tl-axis">
                <span class="tl-dot"></span>
                <span class="tl-date">{{ formatDate(d.date) }}</span>
              </div>
              <div class="tl-side tl-empty"></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 题材详情弹框 -->
    <div v-if="detailOpen" class="modal-mask" @click.self="closeDetail">
      <div class="modal">
        <div class="modal-head">
          <span v-if="detail">
            {{ detail.name }}
            <span class="dt-sub">成分股 {{ detail.member_count }} 只</span>
          </span>
          <span v-else>题材详情</span>
          <button class="modal-close" @click="closeDetail">✕</button>
        </div>
        <div class="modal-body">
          <div v-if="detailLoading" class="loading">加载中…</div>
          <div v-else-if="detailError" class="error">⚠ {{ detailError }}</div>
          <div v-else-if="detail">
            <!-- 图1：涨跌幅时间轴 -->
            <h3 class="dt-h3">① 每日涨跌幅变化（%）</h3>
            <TrendChart :series="detailPctSeries" unit="%" :show-zero-line="true" />

            <!-- 图2：涨跌停数量趋势 -->
            <h3 class="dt-h3">② 每日涨跌停股票数量</h3>
            <TrendChart :series="detailLimitSeries" unit="家" :digits="0" />

            <!-- 点击日期看明细（全市场准确数据） -->
            <h3 class="dt-h3">③ 点击日期查看当日全市场涨 / 跌超 9% 个股</h3>
            <div class="date-tabs">
              <button
                v-for="d in detail.days"
                :key="d.date"
                class="date-tab"
                :class="{ active: d.date === selectedDate }"
                @click="selectedDate = d.date"
              >
                {{ formatDate(d.date) }}
              </button>
            </div>

            <div v-if="marketLoading" class="loading">加载全市场行情中…</div>
            <div v-else-if="marketError" class="error">⚠ {{ marketError }}</div>
            <template v-else-if="marketDay">
              <div class="dt-day-summary">
                <span>全市场股票 <b>{{ marketDay.stocks.length }}</b> 只</span>
                <span>涨幅 ≥ 9% <b class="up">{{ marketUp.length }}</b> 只</span>
                <span>跌幅 ≤ -9% <b class="down">{{ marketDown.length }}</b> 只</span>
              </div>

              <h4 class="dt-h4 up">涨幅 ≥ 9% 个股（{{ marketUp.length }}）</h4>
              <table v-if="marketUp.length" class="stock-table">
                <thead>
                  <tr>
                    <th class="left">代码</th>
                    <th class="left">名称</th>
                    <th>涨跌幅</th>
                    <th>成交额</th>
                    <th>换手率</th>
                    <th>振幅</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="s in marketUp" :key="'u' + s.code">
                    <td class="left">{{ s.code }}</td>
                    <td class="left">{{ s.name || s.code }}</td>
                    <td class="up">{{ fmtPct(s.change_pct) }}</td>
                    <td>{{ fmtYi(s.amount) }}</td>
                    <td>{{ s.turnover != null ? s.turnover + '%' : '-' }}</td>
                    <td>{{ s.amplitude != null ? s.amplitude + '%' : '-' }}</td>
                  </tr>
                </tbody>
              </table>
              <div v-else class="empty">当日无涨幅 ≥ 9% 个股</div>

              <h4 class="dt-h4 down" style="margin-top: 16px">跌幅 ≤ -9% 个股（{{ marketDown.length }}）</h4>
              <table v-if="marketDown.length" class="stock-table">
                <thead>
                  <tr>
                    <th class="left">代码</th>
                    <th class="left">名称</th>
                    <th>涨跌幅</th>
                    <th>成交额</th>
                    <th>换手率</th>
                    <th>振幅</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="s in marketDown" :key="'d' + s.code">
                    <td class="left">{{ s.code }}</td>
                    <td class="left">{{ s.name || s.code }}</td>
                    <td class="down">{{ fmtPct(s.change_pct) }}</td>
                    <td>{{ fmtYi(s.amount) }}</td>
                    <td>{{ s.turnover != null ? s.turnover + '%' : '-' }}</td>
                    <td>{{ s.amplitude != null ? s.amplitude + '%' : '-' }}</td>
                  </tr>
                </tbody>
              </table>
              <div v-else class="empty">当日无跌幅 ≤ -9% 个股</div>
            </template>
            <div v-else class="empty">
              暂无 {{ selectedDate }} 的全市场行情数据，请运行
              <code>make fetch-market DATE={{ selectedDate }}</code>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dg-tag.clickable {
  cursor: pointer;
}
.dg-tag.clickable:hover {
  border-color: var(--blue);
  background: #e8f3ff;
}
.dt-sub {
  font-size: 13px;
  color: var(--text-dim);
  font-weight: 400;
  margin-left: 8px;
}
.dt-h3 {
  margin: 6px 0 12px;
  font-size: 14px;
  font-weight: 600;
}
.dt-h4 {
  margin: 4px 0 8px;
  font-size: 13px;
  font-weight: 600;
}
.dt-day-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 12.5px;
  color: var(--text-dim);
  padding: 8px 12px;
  background: var(--card-2);
  border-radius: 8px;
  margin-bottom: 12px;
}
.dt-day-summary b {
  font-weight: 700;
}
</style>
