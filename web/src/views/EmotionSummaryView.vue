<script setup>
import { ref, computed, onMounted } from 'vue';
import { fetchData } from '../api.js';
import { fmtYi, formatDate } from '../utils.js';
import LineChart from '../components/LineChart.vue';
import BarTimeChart from '../components/BarTimeChart.vue';
import BarGroupChart from '../components/BarGroupChart.vue';

const json = ref(null);
const error = ref('');
const loading = ref(false);

onMounted(load);

async function load() {
  loading.value = true;
  error.value = '';
  try {
    json.value = await fetchData();
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

const dates = computed(() =>
  json.value ? Object.keys(json.value.data || {}).sort() : []
);

const days = computed(() => {
  if (!json.value) return [];
  const d = json.value.data || {};
  return dates.value.map((k) => ({ date: k, ...d[k] }));
});

// 提取各指标序列
function series(key, transform) {
  const t = transform || ((v) => v);
  return days.value
    .map((d) => ({ x: formatDate(d.date), y: t(d[key]) }))
    .filter((p) => p.y != null && p.y !== undefined);
}

function pctSeries(key) { return series(key, (v) => Number(v)); }
function countSeries(key) { return series(key, (v) => Number(v ?? 0)); }

// 指标分组
const limitUpSeries = computed(() => countSeries('limit_up_count'));
const limitDownSeries = computed(() => countSeries('limit_down_count'));
const blowUpCountSeries = computed(() => countSeries('blow_up_count'));
const blowUpRateSeries = computed(() => pctSeries('blow_up_rate'));
const maxBoardSeries = computed(() => countSeries('max_consecutive_board'));

const progression1to2 = computed(() =>
  countSeries('board_progression', (v) => v?.['1to2'] ?? 0)
);
const progression2to3 = computed(() =>
  countSeries('board_progression', (v) => v?.['2to3'] ?? 0)
);
const progression3to4 = computed(() =>
  countSeries('board_progression', (v) => v?.['3to4'] ?? 0)
);
const progression4to5 = computed(() =>
  countSeries('board_progression', (v) => v?.['4to5'] ?? 0)
);

// 指数
const indexNames = ['上证指数', '深证成指', '创业板指'];
const indexColors = { 上证指数: '#1890ff', 深证成指: '#f5a623', 创业板指: '#722ed1' };
const indexPctSeries = computed(() =>
  indexNames.map((name) => ({
    name,
    color: indexColors[name],
    points: days.value
      .map((d) => ({
        x: formatDate(d.date),
        y:
          d.indices?.[name]?.pct_change != null
            ? Number(d.indices[name].pct_change)
            : null,
      }))
      .filter((p) => p.y != null),
  }))
);

// 融资余额（亿元）
const marginTotalSeries = computed(() =>
  series(
    'margin',
    (v) =>
      v?.total_margin_balance != null
        ? Number(v.total_margin_balance) / 1e8
        : null
  )
);

// 北向资金合计净买（亿元）
const northTotalSeries = computed(() =>
  series(
    'north_flow',
    (v) =>
      v?.total_net_buy != null ? Number(v.total_net_buy) / 1e8 : null
  )
);
</script>

<template>
  <div v-if="loading" class="loading">加载中…</div>
  <div v-else-if="error" class="error">⚠ {{ error }}</div>
  <div v-else-if="days.length">
    <!-- meta -->
    <div class="panel">
      <div class="meta-grid">
        <div class="meta-card">
          <div class="label">数据范围</div>
          <div class="value">{{ json.meta?.data_range || '-' }}</div>
        </div>
        <div class="meta-card">
          <div class="label">交易日数</div>
          <div class="value">{{ dates.length }} 天</div>
        </div>
        <div class="meta-card">
          <div class="label">日期区间</div>
          <div class="value" style="font-size: 13px; font-weight: 400">
            {{ formatDate(dates[0]) }} ~ {{ formatDate(dates[dates.length - 1]) }}
          </div>
        </div>
      </div>
    </div>

    <!-- ====== 涨跌停核心 ====== -->
    <div class="panel">
      <h2>涨停 / 跌停 / 炸板 家数</h2>
      <LineChart
        :series="[
          { name: '涨停', points: limitUpSeries, color: '#f5a623' },
          { name: '跌停', points: limitDownSeries, color: '#52c41a' },
          { name: '炸板', points: blowUpCountSeries, color: '#1890ff' },
        ]"
      />
    </div>

    <div class="grid-2">
      <div class="panel">
        <h2>炸板率 (%)</h2>
        <LineChart :series="[{ name: '炸板率', points: blowUpRateSeries, color: '#e9a23b' }]" />
      </div>
      <div class="panel">
        <h2>最高连板高度</h2>
        <BarTimeChart :points="maxBoardSeries" color="#f5a623" />
      </div>
    </div>

    <!-- ====== 连板进阶 ====== -->
    <div class="panel">
      <h2>连板进阶成功数</h2>
      <BarGroupChart
        :groups="[
          { label: '1进2', points: progression1to2, color: '#1890ff' },
          { label: '2进3', points: progression2to3, color: '#f5a623' },
          { label: '3进4', points: progression3to4, color: '#52c41a' },
          { label: '4进5', points: progression4to5, color: '#e9a23b' },
        ]"
      />
    </div>

    <!-- ====== 三大指数 ====== -->
    <div class="panel">
      <h2>三大指数日涨跌幅 (%)</h2>
      <LineChart :series="indexPctSeries" :show-zero-line="true" />
    </div>

    <!-- ====== 资金面 ====== -->
    <div class="grid-2">
      <div class="panel">
        <h2>融资余额合计（亿）</h2>
        <LineChart :series="[{ name: '融资余额', points: marginTotalSeries, color: '#1890ff' }]" />
      </div>
      <div class="panel">
        <h2>北向资金合计净买（亿）</h2>
        <BarTimeChart :points="northTotalSeries" color="#52c41a" :show-zero-line="true" />
      </div>
    </div>
  </div>
</template>
