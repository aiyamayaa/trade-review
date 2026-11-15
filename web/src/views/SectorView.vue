<script setup>
import { ref, computed, onMounted } from 'vue';
import { fetchSector, fetchData } from '../api.js';
import {
  fmtYi,
  fmtPct,
  formatDate,
  totalBoardOf,
} from '../utils.js';
import StatCard from '../components/StatCard.vue';
import BarChart from '../components/BarChart.vue';
import TrendChart from '../components/TrendChart.vue';

const json = ref(null);
const error = ref('');
const loading = ref(false);
const selected = ref('');

onMounted(load);

async function load() {
  loading.value = true;
  error.value = '';
  try {
    json.value = await fetchSector();
    const ds = Object.keys(json.value.data || {}).sort();
    selected.value = ds[ds.length - 1] || '';
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
  // 资金面数据（融资融券余额 / 沪深股通净买，来自 limit_up_down_data.json），叠加到成交额趋势图
  try {
    fundJson.value = await fetchData();
  } catch (e) {
    console.warn('加载资金面数据失败（趋势图不显示融资融券/沪深股通）:', e);
  }
}

// 资金面趋势（融资融券、沪股通、深股通），日期与板块趋势对齐，单位亿
// 注意单位：margin 存元（÷1e8 转亿）；north_flow 存的就是亿元（直接用）
const fundJson = ref(null);
const FUND_COLORS = ['#111827', '#d4380d', '#08979c'];
const fundSeries = computed(() => {
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
      points: allDays.value.map((day) => {
        const m = fd[day.date];
        const v = m ? d.pick(m) : null;
        return { x: formatDate(day.date), y: v != null ? Number(v) / d.div : null };
      }),
    }))
    // 数据源已停止披露的（全 null，如 2024 年起的北向净买额）自动不显示
    .filter((s) => s.points.some((p) => p.y != null));
});

const meta = computed(() => json.value?.meta || {});
const dates = computed(() =>
  json.value ? Object.keys(json.value.data || {}).sort() : []
);
const dayData = computed(() =>
  json.value && selected.value ? json.value.data[selected.value] || {} : {}
);
const industries = computed(() => Object.keys(dayData.value));

// 当日汇总
const summary = computed(() => {
  let activeCount = 0,
    totalBoard = 0,
    blowSum = 0,
    blowCnt = 0,
    amtSum = 0;
  industries.value.forEach((n) => {
    const s = dayData.value[n];
    const tb = totalBoardOf(s);
    if (tb > 0) activeCount++;
    totalBoard += tb;
    if (s.blow_up_rate != null) {
      blowSum += s.blow_up_rate;
      blowCnt++;
    }
    if (s.total_amount != null) amtSum += s.total_amount;
  });
  return {
    activeCount,
    totalBoard,
    avgBlow: blowCnt ? (blowSum / blowCnt).toFixed(2) + '%' : '-',
    amtSum: fmtYi(amtSum),
  };
});

const byBoard = computed(() =>
  industries.value
    .map((n) => ({ n, s: dayData.value[n] }))
    .sort((a, b) => totalBoardOf(b.s) - totalBoardOf(a.s))
    .slice(0, 12)
    .map((x) => ({ label: x.n, value: totalBoardOf(x.s), color: 'var(--red)' }))
);

const byAmt = computed(() =>
  industries.value
    .map((n) => ({ n, s: dayData.value[n] }))
    .filter((x) => x.s.total_amount != null)
    .sort((a, b) => b.s.total_amount - a.s.total_amount)
    .slice(0, 12)
    .map((x) => ({ label: x.n, value: x.s.total_amount, color: 'var(--blue)' }))
);

// ===== 当日三个榜单（数值展示）=====
// 成交额前5
const amtTop5 = computed(() =>
  industries.value
    .map((n) => ({ n, s: dayData.value[n] }))
    .filter((x) => x.s.total_amount != null)
    .sort((a, b) => b.s.total_amount - a.s.total_amount)
    .slice(0, 5)
);
// 涨幅前5（含成交额）
const gainTop5 = computed(() =>
  industries.value
    .map((n) => ({ n, s: dayData.value[n] }))
    .filter((x) => x.s.index_change_pct != null)
    .sort((a, b) => b.s.index_change_pct - a.s.index_change_pct)
    .slice(0, 5)
);
// 跌幅前5（含成交额）
const lossTop5 = computed(() =>
  industries.value
    .map((n) => ({ n, s: dayData.value[n] }))
    .filter((x) => x.s.index_change_pct != null)
    .sort((a, b) => a.s.index_change_pct - b.s.index_change_pct)
    .slice(0, 5)
);

// ===== 时间范围趋势（最新日期范围内整体数据）=====
const allDays = computed(() => {
  if (!json.value) return [];
  return dates.value.map((k) => ({ date: k, data: json.value.data[k] || {} }));
});

// 折线颜色板
const LINE_COLORS = [
  '#1890ff', '#f5a623', '#52c41a', '#9254de',
  '#13c2c2', '#eb2f96', '#fa8c16', '#e9a23b',
];

// 收集每日按某字段排名 top N 的板块（去重集合）
function collectTopBoards(topN, key, abs = false) {
  const boardSet = new Set();
  allDays.value.forEach((d) => {
    Object.entries(d.data)
      .filter(([, s]) => s[key] != null)
      .sort((a, b) => {
        const va = abs ? Math.abs(a[1][key]) : a[1][key];
        const vb = abs ? Math.abs(b[1][key]) : b[1][key];
        return vb - va;
      })
      .slice(0, topN)
      .forEach(([n]) => boardSet.add(n));
  });
  return [...boardSet];
}

// 每个板块总成交额变化趋势（取每日成交额 top N 板块，单位：亿）
const boardAmountSeries = computed(() =>
  collectTopBoards(8, 'total_amount').map((name, i) => ({
    name,
    color: LINE_COLORS[i % LINE_COLORS.length],
    points: allDays.value.map((d) => {
      const s = d.data[name];
      return {
        x: formatDate(d.date),
        y: s?.total_amount != null ? Number(s.total_amount) / 1e8 : null,
      };
    }),
  }))
);

// 每天涨跌幅前5板块变化趋势（涨幅前5 + 跌幅前5）
const dailyTop5 = computed(() =>
  allDays.value.map((d) => {
    const entries = Object.entries(d.data).filter(
      ([, s]) => s.index_change_pct != null
    );
    const gain = [...entries]
      .sort((a, b) => b[1].index_change_pct - a[1].index_change_pct)
      .slice(0, 5);
    const loss = [...entries]
      .sort((a, b) => a[1].index_change_pct - b[1].index_change_pct)
      .slice(0, 5);
    return { date: d.date, gain, loss };
  })
);

// 每天成交额前5板块
const dailyAmtTop5 = computed(() =>
  allDays.value.map((d) => {
    const top = Object.entries(d.data)
      .filter(([, s]) => s.total_amount != null)
      .sort((a, b) => b[1].total_amount - a[1].total_amount)
      .slice(0, 5);
    return { date: d.date, top };
  })
);

// 悬浮高亮板块名（在每日涨跌幅前5中高亮同名块）
const hoveredBoard = ref('');
function setHoverBoard(name) {
  hoveredBoard.value = name || '';
}
function tagHlClass(name) {
  if (!hoveredBoard.value) return '';
  return hoveredBoard.value === name ? 'hl' : 'dim';
}

// 每个板块每天涨跌幅变化趋势（取每日涨跌幅波动最大的板块，单位：%）
const boardPctSeries = computed(() =>
  collectTopBoards(8, 'index_change_pct', true).map((name, i) => ({
    name,
    color: LINE_COLORS[i % LINE_COLORS.length],
    points: allDays.value.map((d) => {
      const s = d.data[name];
      return {
        x: formatDate(d.date),
        y: s?.index_change_pct != null ? Number(s.index_change_pct) : null,
      };
    }),
  }))
);

// 排序：默认按涨停板数降序
const sortKey = ref('board');
const sortDir = ref('desc'); // 'asc' | 'desc'
const SORT_FIELDS = {
  board: (s) => totalBoardOf(s),
  blow_up_rate: (s) => s.blow_up_rate,
  index_change_pct: (s) => s.index_change_pct,
  volume_ratio: (s) => s.volume_ratio,
  total_amount: (s) => s.total_amount,
};
const SORT_LABEL = {
  board: '涨停板数',
  blow_up_rate: '炸板率',
  index_change_pct: '板块涨幅',
  volume_ratio: '量比',
  total_amount: '成交额',
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
  const arr = industries.value.map((n) => ({ n, s: dayData.value[n] }));
  const f = SORT_FIELDS[sortKey.value] || SORT_FIELDS.board;
  const dir = sortDir.value === 'desc' ? -1 : 1;
  return arr.sort((a, b) => {
    const va = f(a.s);
    const vb = f(b.s);
    // null 永远排到最后
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    return (va - vb) * dir;
  });
});

const sortHint = computed(
  () => `${SORT_LABEL[sortKey.value]} ${sortDir.value === 'desc' ? '↓' : '↑'}`
);

// 展开明细（按行业名记录）
const expanded = ref({});
function toggleExpand(n) {
  expanded.value = { ...expanded.value, [n]: !expanded.value[n] };
}
</script>

<template>
  <div v-if="loading" class="loading">加载中…</div>
  <div v-else-if="error" class="error">⚠ {{ error }}</div>
  <div v-else-if="Object.keys(dayData).length">
    <!-- meta -->
    <div class="panel">
      <div class="meta-grid">
        <div class="meta-card">
          <div class="label">数据说明</div>
          <div class="value" style="font-size: 13px; font-weight: 400">
            {{ meta.description || '-' }}
          </div>
        </div>
        <div class="meta-card">
          <div class="label">数据范围</div>
          <div class="value">{{ meta.data_range || '-' }}</div>
        </div>
        <div class="meta-card">
          <div class="label">申万活跃行业</div>
          <div class="value">{{ meta.active_sw_industries ?? '-' }}</div>
        </div>
        <div class="meta-card">
          <div class="label">同花顺行业</div>
          <div class="value">{{ meta.active_ths_industries ?? '-' }}</div>
        </div>
      </div>
    </div>

    <!-- 时间范围趋势 -->
    <div class="panel">
      <h2>时间范围趋势（{{ formatDate(dates[0]) }} ~ {{ formatDate(dates[dates.length - 1]) }}）</h2>
      <div>
        <h3 style="color: var(--blue)">各板块总成交额变化趋势（亿）· 含融资融券/沪深股通</h3>
        <TrendChart :series="[...boardAmountSeries, ...fundSeries]" unit="亿" />
      </div>
      <div style="margin-top: 20px">
        <h3 style="color: var(--red)">每天涨跌幅前5板块变化趋势</h3>
        <div class="tl-wrap">
          <div class="tl">
            <div v-for="d in dailyTop5" :key="d.date" class="tl-col">
              <div class="tl-side tl-gain">
                <span
                  v-for="t in d.gain"
                  :key="'g' + t[0]"
                  class="dg-tag"
                  :class="tagHlClass(t[0])"
                  @mouseenter="setHoverBoard(t[0])"
                  @mouseleave="setHoverBoard('')"
                >
                  {{ t[0] }} <b class="up">{{ fmtPct(t[1].index_change_pct) }}</b>
                </span>
              </div>
              <div class="tl-axis">
                <span class="tl-dot"></span>
                <span class="tl-date">{{ formatDate(d.date) }}</span>
              </div>
              <div class="tl-side tl-loss">
                <span
                  v-for="t in d.loss"
                  :key="'l' + t[0]"
                  class="dg-tag"
                  :class="tagHlClass(t[0])"
                  @mouseenter="setHoverBoard(t[0])"
                  @mouseleave="setHoverBoard('')"
                >
                  {{ t[0] }} <b class="down">{{ fmtPct(t[1].index_change_pct) }}</b>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div style="margin-top: 20px">
        <h3 style="color: var(--blue)">每天成交额前5板块</h3>
        <div class="tl-wrap">
          <div class="tl">
            <div v-for="d in dailyAmtTop5" :key="d.date" class="tl-col">
              <div class="tl-side tl-amt">
                <span
                  v-for="t in d.top"
                  :key="t[0]"
                  class="dg-tag"
                  :class="tagHlClass(t[0])"
                  @mouseenter="setHoverBoard(t[0])"
                  @mouseleave="setHoverBoard('')"
                >
                  {{ t[0] }} <b class="amt">{{ fmtYi(t[1].total_amount) }}</b>
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

      <div style="margin-top: 20px">
        <h3 style="color: var(--gold)">各板块每日涨跌幅变化趋势（%）</h3>
        <TrendChart :series="boardPctSeries" unit="%" :show-zero-line="true" />
      </div>
    </div>

    <!-- 日期切换 -->
    <div class="date-tabs">
      <button
        v-for="d in dates"
        :key="d"
        class="date-tab"
        :class="{ active: d === selected }"
        @click="selected = d"
      >
        {{ formatDate(d) }}
      </button>
    </div>

    <!-- 当日汇总 -->
    <div class="panel">
      <h2>当日汇总（{{ formatDate(selected) }}）</h2>
      <div class="stat-grid">
        <StatCard label="活跃板块(有涨停)" :value="summary.activeCount" accent="red" />
        <StatCard label="涨停板总数" :value="summary.totalBoard" accent="red" />
        <StatCard label="平均炸板率" :value="summary.avgBlow" accent="gold" />
        <StatCard label="板块总成交额" :value="summary.amtSum" accent="blue" />
      </div>
    </div>

    <!-- TOP 条形图 -->
    <div class="grid-2">
      <div class="panel">
        <h2 style="color: var(--red)">涨停板数 TOP 12</h2>
        <BarChart :items="byBoard" :value-fmt="(v) => v + ' 只'" color="var(--red)" />
      </div>
      <div class="panel">
        <h2 style="color: var(--blue)">板块成交额 TOP 12</h2>
        <BarChart :items="byAmt" :value-fmt="(v) => fmtYi(v)" color="var(--blue)" />
      </div>
    </div>

    <!-- 当日榜单（数值展示） -->
    <div class="panel">
      <h2>当日榜单（{{ formatDate(selected) }}）</h2>
      <div class="rank-3col">
        <div class="rank-col">
          <h3 style="color: var(--blue)">成交额前 5</h3>
          <div class="rank-list">
            <div v-for="(x, i) in amtTop5" :key="x.n" class="rank-item">
              <span class="rank-no">{{ i + 1 }}</span>
              <span class="rank-name">{{ x.n }}</span>
              <span class="rank-val">{{ fmtYi(x.s.total_amount) }}</span>
            </div>
          </div>
        </div>
        <div class="rank-col">
          <h3 style="color: var(--red)">涨幅前 5（含成交额）</h3>
          <div class="rank-list">
            <div v-for="(x, i) in gainTop5" :key="x.n" class="rank-item">
              <span class="rank-no">{{ i + 1 }}</span>
              <span class="rank-name">{{ x.n }}</span>
              <span class="rank-val up">{{ fmtPct(x.s.index_change_pct) }}</span>
              <span class="rank-sub">{{ fmtYi(x.s.total_amount) }}</span>
            </div>
          </div>
        </div>
        <div class="rank-col">
          <h3 style="color: var(--green)">跌幅前 5（含成交额）</h3>
          <div class="rank-list">
            <div v-for="(x, i) in lossTop5" :key="x.n" class="rank-item">
              <span class="rank-no">{{ i + 1 }}</span>
              <span class="rank-name">{{ x.n }}</span>
              <span class="rank-val down">{{ fmtPct(x.s.index_change_pct) }}</span>
              <span class="rank-sub">{{ fmtYi(x.s.total_amount) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 行业明细表 -->
    <div class="panel">
      <h2>行业明细（{{ formatDate(selected) }}，当前按 {{ sortHint }} 排序）</h2>
      <div style="overflow-x: auto">
        <table>
          <thead>
            <tr>
              <th class="left">行业</th>
              <th>首板</th>
              <th>2板</th>
              <th>3板</th>
              <th>4板+</th>
              <th>最高连板</th>
              <th
                class="sortable"
                :class="{ active: sortKey === 'blow_up_rate' }"
                @click="toggleSort('blow_up_rate')"
              >
                炸板率<span class="sort-ind">{{ sortKey === 'blow_up_rate' ? (sortDir === 'desc' ? ' ↓' : ' ↑') : '' }}</span>
              </th>
              <th
                class="sortable"
                :class="{ active: sortKey === 'index_change_pct' }"
                @click="toggleSort('index_change_pct')"
              >
                板块涨幅<span class="sort-ind">{{ sortKey === 'index_change_pct' ? (sortDir === 'desc' ? ' ↓' : ' ↑') : '' }}</span>
              </th>
              <th
                class="sortable"
                :class="{ active: sortKey === 'volume_ratio' }"
                @click="toggleSort('volume_ratio')"
              >
                量比<span class="sort-ind">{{ sortKey === 'volume_ratio' ? (sortDir === 'desc' ? ' ↓' : ' ↑') : '' }}</span>
              </th>
              <th
                class="sortable left"
                :class="{ active: sortKey === 'total_amount' }"
                @click="toggleSort('total_amount')"
              >
                成交额<span class="sort-ind">{{ sortKey === 'total_amount' ? (sortDir === 'desc' ? ' ↓' : ' ↑') : '' }}</span>
              </th>
              <th class="left">最高连板个股</th>
              <th class="left">龙虎净买</th>
              <th>上榜</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="r in rows" :key="r.n">
              <tr>
                <td
                  class="left"
                  @mouseenter="setHoverBoard(r.n)"
                  @mouseleave="setHoverBoard('')"
                >
                  {{ r.n }}
                </td>
                <td>{{ r.s.board_1 || 0 }}</td>
                <td>{{ r.s.board_2 || 0 }}</td>
                <td>{{ r.s.board_3 || 0 }}</td>
                <td>{{ r.s.board_4 || 0 }}</td>
                <td>{{ r.s.max_board_height || 0 }}</td>
                <td>
                  {{
                    r.s.blow_up_rate == null ? '-' : r.s.blow_up_rate.toFixed(2) + '%'
                  }}
                </td>
                <td
                  :class="
                    r.s.index_change_pct == null
                      ? ''
                      : r.s.index_change_pct >= 0
                      ? 'up'
                      : 'down'
                  "
                >
                  {{
                    r.s.index_change_pct == null
                      ? '-'
                      : fmtPct(r.s.index_change_pct)
                  }}
                </td>
                <td
                  :class="
                    r.s.volume_ratio == null
                      ? ''
                      : r.s.volume_ratio >= 1
                      ? 'up'
                      : 'down'
                  "
                >
                  {{ r.s.volume_ratio == null ? '-' : r.s.volume_ratio.toFixed(2) }}
                </td>
                <td class="left">
                  {{ r.s.total_amount == null ? '-' : fmtYi(r.s.total_amount) }}
                </td>
                <td class="left clickable" :class="{ open: expanded[r.n] }">
                  <span class="toggle-btn" @click.stop="toggleExpand(r.n)">
                    {{ expanded[r.n] ? '收起 ▾' : '展开 ▸' }}
                  </span>
                </td>
                <td class="left">
                  {{ r.s.lhb_net_buy == null ? '-' : fmtYi(r.s.lhb_net_buy) }}
                </td>
                <td>{{ r.s.lhb_stock_count || 0 }}</td>
              </tr>
              <tr v-if="expanded[r.n]" class="detail-row">
                <td colspan="13">
                  <div class="detail-box">
                    <div class="detail-title">
                      {{ r.n }} · 最高连板明细（高度 {{ r.s.max_board_height || 0 }} 板）
                    </div>
                    <div v-if="(r.s.max_board_stocks || []).length" class="detail-list">
                      <div
                        v-for="s in r.s.max_board_stocks"
                        :key="s"
                        class="detail-item"
                      >
                        <span class="code">{{ s.split(' ')[0] }}</span>
                        <span class="nm">{{ s.split(' ').slice(1).join(' ') }}</span>
                      </div>
                    </div>
                    <div v-else class="detail-empty">无最高连板个股</div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
