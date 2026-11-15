<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue';
import { fetchTickList, fetchTickData } from '../api.js';

// ECharts 按需引入
import * as echarts from 'echarts/core';
import { LineChart, CandlestickChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
echarts.use([LineChart, CandlestickChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, CanvasRenderer]);

// 单个分时图表面板：独立的日期选择 + 股票勾选 + 图表（可多面板并存对比不同日期）
const props = defineProps({
  dates: { type: Array, default: () => [] },
  refreshKey: { type: Number, default: 0 }, // 父组件下载完成后 +1，触发刷新
  initialDate: { type: String, default: '' },
  closable: { type: Boolean, default: true },
});
const emit = defineEmits(['remove']);

// ===== 日期与股票列表 =====
const date = ref(props.initialDate || (props.dates.length ? props.dates[props.dates.length - 1] : ''));
const groups = ref([]);
const loadingList = ref(false);
const listError = ref('');
const stocks = computed(() =>
  groups.value.flatMap((g) => g.stocks.map((s) => ({ ...s, group: g.group })))
);

async function loadStocks() {
  groups.value = [];
  collapsedGroups.value = new Set();
  allCollapsed.value = false;
  listError.value = '';
  checked.value = new Set();
  chartData.value = {}; // 清缓存（key 不含日期，切日期必须重置）
  chartError.value = '';
  if (!date.value) return;
  loadingList.value = true;
  try {
    const r = await fetchTickList(date.value);
    groups.value = r.groups || [];
  } catch (e) {
    listError.value = e.message;
  } finally {
    loadingList.value = false;
  }
}

watch(date, loadStocks);
watch(() => props.refreshKey, () => loadStocks());
watch(
  () => props.dates,
  (d) => {
    if (!date.value && d.length) date.value = d[d.length - 1];
  }
);
onMounted(loadStocks);

// ===== 分组折叠 =====
const collapsedGroups = ref(new Set());
// 摘要模式：折叠全部时连分组标题行也收起，只留一行概念标签条（点标签展开单个分组）
const allCollapsed = ref(false);
function toggleGroupCollapse(group) {
  const s = new Set(collapsedGroups.value);
  if (s.has(group)) s.delete(group);
  else s.add(group);
  collapsedGroups.value = s;
}
function collapseAllGroups() {
  collapsedGroups.value = new Set(groups.value.map((g) => g.group));
  allCollapsed.value = true; // 概念分组也折叠 → 摘要条模式
}
function expandAllGroups() {
  collapsedGroups.value = new Set();
  allCollapsed.value = false;
}
// 摘要条上点击某个概念 → 退出摘要模式，只展开该组
function expandOneGroup(group) {
  allCollapsed.value = false;
  collapsedGroups.value = new Set(
    groups.value.map((g) => g.group).filter((g) => g !== group)
  );
}

// ===== 分组拖拽排序（localStorage 持久化）=====
const GROUP_ORDER_KEY = 'tick_group_order';
const dragGroup = ref(null);
const dropTarget = ref(null);
const groupOrder = ref(loadGroupOrder());

function loadGroupOrder() {
  try {
    const s = localStorage.getItem(GROUP_ORDER_KEY);
    const arr = JSON.parse(s);
    if (Array.isArray(arr)) return arr.filter((x) => typeof x === 'string');
  } catch { /* ignore */ }
  return [];
}
function saveGroupOrder() {
  try {
    localStorage.setItem(GROUP_ORDER_KEY, JSON.stringify(groupOrder.value));
  } catch { /* ignore */ }
}

const orderedGroups = computed(() => {
  const order = groupOrder.value;
  const idxOf = (g) => {
    const i = order.indexOf(g);
    return i === -1 ? order.length : i;
  };
  return [...groups.value].sort((a, b) => idxOf(a.group) - idxOf(b.group));
});

function onGroupDragStart(e, group) {
  dragGroup.value = group;
  e.dataTransfer.effectAllowed = 'move';
}
function onGroupDragOver(e, group) {
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  dropTarget.value = group;
}
function onGroupDrop(e, targetGroup) {
  e.preventDefault();
  const from = dragGroup.value;
  dragGroup.value = null;
  dropTarget.value = null;
  if (!from || from === targetGroup) return;
  const cur = orderedGroups.value.map((g) => g.group);
  const fromIdx = cur.indexOf(from);
  const toIdx = cur.indexOf(targetGroup);
  if (fromIdx === -1 || toIdx === -1) return;
  cur.splice(toIdx, 0, cur.splice(fromIdx, 1)[0]);
  groupOrder.value = cur;
  saveGroupOrder();
}

// ===== 图表 =====
const checked = ref(new Set());
const chartData = ref({}); // code → { mode, points, prevClose }
const chartLoading = ref(false);
const chartError = ref('');
const chartEl = ref(null);
let chart = null;

const PALETTE = ['#1890ff', '#f5222d', '#52c41a', '#fa8c16', '#722ed1', '#13c2c2', '#eb2f96', '#a0d911'];
const checkedList = computed(() => stocks.value.filter((s) => checked.value.has(s.code)));

function toggleStock(code) {
  const s = new Set(checked.value);
  if (s.has(code)) s.delete(code);
  else s.add(code);
  checked.value = s;
  if (s.size) renderChart();
}

function stockMode(s) {
  return s.modes.includes('minute') ? 'minute' : 'ticks';
}

function fmtAmt(v) {
  if (v == null) return '-';
  return v >= 1e8 ? (v / 1e8).toFixed(2) + '亿' : (v / 1e4).toFixed(0) + '万';
}
function limitPctOf(code) {
  const bare = String(code).replace(/^(sh|sz|bj)/i, '');
  if (/^(30|68)/.test(bare)) return 20;
  if (/^(4|8|92)/.test(bare)) return 30;
  return 10;
}
function limitPrice(prevClose, pct) {
  return Math.round(prevClose * (1 + pct / 100) * 100) / 100;
}

async function ensureData(s) {
  if (chartData.value[s.code]) return chartData.value[s.code];
  const mode = stockMode(s);
  const d = await fetchTickData(date.value, s.code, mode);
  const cols = d.columns;
  const idx = (name) => cols.indexOf(name);
  const pcIdx = idx('昨收');
  const prevClose = pcIdx >= 0 && d.rows.length ? +d.rows[0][pcIdx] || null : null;
  let points;
  if (mode === 'minute') {
    points = d.rows.map((r) => ({
      t: r[idx('时间')].slice(11, 16),
      o: +r[idx('开')], h: +r[idx('高')], l: +r[idx('低')], c: +r[idx('收')],
      v: +r[idx('成交量(股)')],
      a: +r[idx('成交额(元)')],
    }));
  } else {
    const raw = d.rows.map((r) => ({
      t: r[idx('成交时间')].slice(0, 5),
      c: +r[idx('成交价格')],
      v: +r[idx('成交量')],
      a: +r[idx('成交金额')],
      side: r[idx('性质')],
    }));
    const byMin = new Map();
    for (const p of raw) {
      const cur = byMin.get(p.t);
      if (cur) { cur.c = p.c; cur.v += p.v; cur.a += p.a; }
      else byMin.set(p.t, { ...p });
    }
    points = [...byMin.values()].sort((a, b) => a.t.localeCompare(b.t));
  }
  chartData.value[s.code] = { mode, points, prevClose };
  return chartData.value[s.code];
}

async function renderChart() {
  chartError.value = '';
  const list = checkedList.value;
  if (!list.length) return;
  chartLoading.value = true;
  try {
    const datasets = [];
    for (const s of list) {
      datasets.push({ stock: s, data: await ensureData(s) });
    }
    await nextTick();
    draw(datasets);
  } catch (e) {
    chartError.value = e.message;
  } finally {
    chartLoading.value = false;
  }
}

function draw(datasets) {
  if (!chartEl.value) return;
  if (!chart) chart = echarts.init(chartEl.value);
  const single = datasets.length === 1;
  const first = datasets[0];

  // 单只 + 分钟线 → 蜡烛K线 + 成交量 + 成交额
  if (single && first.data.mode === 'minute') {
    const pts = first.data.points;
    const times = pts.map((p) => p.t);
    chart.setOption({
      animation: false,
      title: { text: `${first.stock.name}（${first.stock.code}）${date.value} 分钟K线`, left: 8, textStyle: { fontSize: 13 } },
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' }, valueFormatter: (v) => (v == null ? '-' : String(v)) },
      grid: [
        { left: 64, right: 16, top: 40, height: '46%' },
        { left: 64, right: 16, top: '58%', height: '15%' },
        { left: 64, right: 16, top: '77%', height: '15%' },
      ],
      xAxis: [
        { type: 'category', data: times, gridIndex: 0, axisLabel: { show: false } },
        { type: 'category', data: times, gridIndex: 1, axisLabel: { show: false } },
        { type: 'category', data: times, gridIndex: 2 },
      ],
      yAxis: [
        { scale: true, gridIndex: 0 },
        { min: 0, gridIndex: 1, splitNumber: 2, axisLabel: { formatter: (v) => fmtAmt(v) } },
        { min: 0, gridIndex: 2, splitNumber: 2, axisLabel: { formatter: (v) => fmtAmt(v) } },
      ],
      dataZoom: [{ type: 'inside', xAxisIndex: [0, 1, 2] }],
      series: [
        {
          type: 'candlestick',
          name: first.stock.name,
          data: pts.map((p) => [p.o, p.c, p.l, p.h]),
          itemStyle: { color: '#f5222d', color0: '#52c41a', borderColor: '#f5222d', borderColor0: '#52c41a' },
          ...(first.data.prevClose
            ? [{
                type: 'line',
                markLine: {
                  symbol: 'none', silent: true, lineStyle: { width: 1 },
                  data: (() => {
                    const pc = first.data.prevClose;
                    const lim = limitPctOf(first.stock.code);
                    const up = limitPrice(pc, lim);
                    const down = limitPrice(pc, -lim);
                    return [
                      { yAxis: pc, lineStyle: { color: '#8c8c8c', type: 'dashed' }, label: { formatter: `昨收 ${pc.toFixed(2)}`, position: 'insideEndTop' } },
                      { yAxis: up, lineStyle: { color: '#f5222d', type: 'dotted' }, label: { formatter: `涨停 ${up.toFixed(2)} (+${lim}%)`, position: 'insideEndTop' } },
                      { yAxis: down, lineStyle: { color: '#52c41a', type: 'dotted' }, label: { formatter: `跌停 ${down.toFixed(2)} (-${lim}%)`, position: 'insideEndBottom' } },
                    ];
                  })(),
                },
                data: [],
              }]
            : []),
        },
        { type: 'line', name: '成交量', xAxisIndex: 1, yAxisIndex: 1, data: pts.map((p) => p.v), showSymbol: false, lineStyle: { width: 1 }, areaStyle: { opacity: 0.2 }, color: '#fa8c16' },
        { type: 'line', name: '成交额', xAxisIndex: 2, yAxisIndex: 2, data: pts.map((p) => p.a), showSymbol: false, lineStyle: { width: 1 }, areaStyle: { opacity: 0.2 }, color: '#1890ff' },
      ],
    }, true);
    return;
  }

  // 多只叠加 / 单只分笔 → 涨跌幅%（昨收基准）+ 分时成交额 双图
  const times = [...new Set(datasets.flatMap((d) => d.data.points.map((p) => p.t)))].sort();
  const hasPrevClose = datasets.every((d) => d.data.prevClose);
  const baseLabel = hasPrevClose ? '昨收' : '首价';
  const priceSeries = [];
  const amtSeries = [];
  datasets.forEach((d, i) => {
    const pts = d.data.points;
    const color = PALETTE[i % PALETTE.length];
    const base = d.data.prevClose || (pts[0] ? pts[0].c : 1);
    const pctByT = new Map(pts.map((p) => [p.t, ((p.c - base) / base) * 100]));
    priceSeries.push({
      type: 'line',
      name: `${d.stock.name} ${d.stock.code}`,
      data: times.map((t) => (pctByT.has(t) ? +pctByT.get(t).toFixed(3) : null)),
      connectNulls: true, showSymbol: false, lineStyle: { width: 1.5 }, color,
    });
    const amtByT = new Map(pts.map((p) => [p.t, p.a]));
    amtSeries.push({
      type: 'line',
      name: `${d.stock.name} 成交额`,
      xAxisIndex: 1, yAxisIndex: 1,
      data: times.map((t) => (amtByT.has(t) ? +(amtByT.get(t) / 1e4).toFixed(0) : null)),
      connectNulls: true, showSymbol: false, lineStyle: { width: 1, type: 'dashed' }, color,
    });
  });
  const markLineData = [
    { yAxis: 0, lineStyle: { color: '#8c8c8c', type: 'dashed' }, label: { formatter: '昨收 0%', position: 'insideEndTop' } },
  ];
  if (hasPrevClose) {
    const limits = [...new Set(datasets.map((d) => limitPctOf(d.stock.code)))];
    for (const lim of limits) {
      markLineData.push(
        { yAxis: lim, lineStyle: { color: '#f5222d', type: 'dotted' }, label: { formatter: `涨停 +${lim}%`, position: 'insideEndTop' } },
        { yAxis: -lim, lineStyle: { color: '#52c41a', type: 'dotted' }, label: { formatter: `跌停 -${lim}%`, position: 'insideEndBottom' } }
      );
    }
  }
  priceSeries[0].markLine = { symbol: 'none', silent: true, lineStyle: { width: 1 }, data: markLineData };
  chart.setOption({
    animation: false,
    title: {
      text: single ? `${first.stock.name}（${first.stock.code}）${date.value} 分时走势` : `多股叠加 ${date.value} · 相对${baseLabel}涨跌幅`,
      left: 8, textStyle: { fontSize: 13 },
    },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'cross' },
      formatter: (params) => {
        const lines = [params[0]?.axisValue || ''];
        for (const p of params) {
          const v = p.value == null ? '-' : p.seriesName.includes('成交额') ? p.value + ' 万' : p.value.toFixed(2) + '%';
          lines.push(`${p.marker}${p.seriesName}：${v}`);
        }
        return lines.join('<br>');
      },
    },
    legend: { top: 8, right: 12, type: 'scroll' },
    grid: [
      { left: 64, right: 16, top: 40, height: '52%' },
      { left: 64, right: 16, top: '66%', height: '24%' },
    ],
    xAxis: [
      { type: 'category', data: times, boundaryGap: false, gridIndex: 0, axisLabel: { show: false } },
      { type: 'category', data: times, boundaryGap: false, gridIndex: 1 },
    ],
    yAxis: [
      { min: (v) => Math.min(0, v.min), gridIndex: 0, axisLabel: { formatter: '{value}%' } },
      { min: 0, gridIndex: 1, splitNumber: 2, axisLabel: { formatter: (v) => (v >= 10000 ? (v / 10000).toFixed(1) + '亿' : v + '万') } },
    ],
    dataZoom: [{ type: 'inside', xAxisIndex: [0, 1] }],
    series: [...priceSeries, ...amtSeries],
  }, true);
}

function onResize() {
  chart && chart.resize();
}
onMounted(() => window.addEventListener('resize', onResize));
onUnmounted(() => {
  window.removeEventListener('resize', onResize);
  chart && chart.dispose();
});

function modeLabel(m) {
  return m === 'ticks' ? '分笔' : '分钟线';
}
</script>

<template>
  <div class="tk-panel">
    <div class="tk-browse-bar">
      <select v-model="date" class="tk-select">
        <option v-for="d in dates" :key="d" :value="d">{{ d.slice(0, 4) }}-{{ d.slice(4, 6) }}-{{ d.slice(6, 8) }}</option>
      </select>
      <button class="tk-btn ghost" @click="loadStocks">↻ 刷新</button>
      <template v-if="groups.length > 1">
        <button class="tk-btn ghost" @click="collapseAllGroups">⊟ 折叠全部</button>
        <button class="tk-btn ghost" @click="expandAllGroups">⊞ 展开全部</button>
      </template>
      <span v-if="loadingList" class="tk-hint">加载中…</span>
      <span v-else class="tk-hint">{{ stocks.length }} 只 · 点分组名折叠/拖拽排序 · 勾选绘图</span>
      <button v-if="closable" class="tk-btn ghost tk-close-btn" title="关闭此图表面板" @click="emit('remove')">✕ 关闭</button>
    </div>
    <div v-if="listError" class="error">⚠ {{ listError }}</div>
    <div v-if="!loadingList && !stocks.length && date" class="empty">该日期暂无数据，先在上方下载</div>

    <!-- 摘要条模式：折叠全部后概念分组也收起，只留一行标签（点标签展开该组） -->
    <div v-if="allCollapsed && orderedGroups.length" class="tk-ac-bar">
      <span class="tk-ac-label">⊟ 已折叠 {{ orderedGroups.length }} 个分组：</span>
      <button
        v-for="g in orderedGroups"
        :key="g.group || '_ungrouped'"
        class="tk-ac-tag"
        :title="`展开「${g.group || '未分组'}」`"
        @click="expandOneGroup(g.group)"
      >{{ g.group || '未分组' }}<i>{{ g.stocks.length }}</i></button>
    </div>

    <!-- 按题材分组展示（点标题折叠，拖标题排序） -->
    <template v-else>
    <div
      v-for="g in orderedGroups"
      :key="g.group || '_ungrouped'"
      class="tk-group-block"
      :class="{ 'tk-group-drop-zone': dropTarget === g.group && dragGroup !== null && dragGroup !== g.group }"
      @dragover="onGroupDragOver($event, g.group)"
      @drop="onGroupDrop($event, g.group)"
      @dragleave="dropTarget === g.group && (dropTarget = null)"
    >
      <div
        class="tk-group-title tk-group-toggle"
        :class="{ 'tk-group-dragging': dragGroup === g.group }"
        draggable="true"
        @dragstart="onGroupDragStart($event, g.group)"
        @dragend="dragGroup = null; dropTarget = null"
        @click="toggleGroupCollapse(g.group)"
      >
        <span class="tk-fold">{{ collapsedGroups.has(g.group) ? '▸' : '▾' }}</span>
        <span class="tk-drag-handle" title="拖拽调整分组顺序">⠿</span>
        {{ g.group || '未分组' }}<span class="tk-group-count">{{ g.stocks.length }} 只</span>
      </div>
      <div v-show="!collapsedGroups.has(g.group)" class="tk-stock-chips">
        <label v-for="s in g.stocks" :key="g.group + s.code" class="tk-chip" :class="{ on: checked.has(s.code) }">
          <input type="checkbox" :checked="checked.has(s.code)" @change="toggleStock(s.code)" />
          {{ s.name }} <span class="tk-chip-code">{{ s.code }}</span>
          <span class="tk-chip-mode">{{ s.modes.map(modeLabel).join('/') }}</span>
        </label>
      </div>
    </div>
    </template>

    <div v-if="chartError" class="error">⚠ {{ chartError }}</div>
    <div v-show="checked.size" class="tk-chart-wrap">
      <div v-if="chartLoading" class="tk-hint" style="padding: 8px">图表加载中…</div>
      <div ref="chartEl" class="tk-chart"></div>
      <div class="tk-hint">单只分钟线 → 蜡烛K线+成交量+成交额；多只或分笔 → 相对昨收涨跌幅% + 分时成交额（滚轮缩放）</div>
    </div>
    <div v-if="!checked.size && stocks.length" class="empty">勾选上方股票开始绘图</div>
  </div>
</template>

<style scoped>
.tk-panel {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px;
  margin-bottom: 14px;
  background: var(--card);
}
.tk-browse-bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }
.tk-select {
  font-size: 12.5px; padding: 7px 10px; border: 1px solid var(--border);
  border-radius: 8px; background: var(--card-2); color: var(--text); cursor: pointer;
}
.tk-btn {
  font-size: 12.5px; font-weight: 600; color: #fff; background: var(--blue);
  border: none; border-radius: 8px; padding: 8px 18px; cursor: pointer; white-space: nowrap;
}
.tk-btn:hover:not(:disabled) { filter: brightness(1.08); }
.tk-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.tk-btn.ghost { background: var(--card-2); color: var(--text-dim); border: 1px solid var(--border); padding: 6px 12px; }
.tk-close-btn { color: #dc2626; border-color: #fecaca; margin-left: auto; }
.tk-close-btn:hover { background: #fef2f2; }
.tk-hint { font-size: 11.5px; color: var(--text-dim); margin-top: 8px; }
/* 折叠全部的摘要条 */
.tk-ac-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  padding: 8px 10px; background: var(--card-2);
  border: 1px dashed var(--border); border-radius: 10px;
}
.tk-ac-label { font-size: 12px; color: var(--text-dim); }
.tk-ac-tag {
  font-size: 12px; color: var(--text); background: #fff;
  border: 1px solid var(--border); border-radius: 14px;
  padding: 3px 10px; cursor: pointer; transition: all 0.15s;
}
.tk-ac-tag i { font-style: normal; font-size: 10px; color: var(--text-dim); margin-left: 3px; }
.tk-ac-tag:hover { color: var(--blue); border-color: var(--blue); background: #e8f3ff; }
.tk-group-block { margin-bottom: 12px; }
.tk-group-title {
  font-size: 12.5px; font-weight: 700; color: var(--text); margin-bottom: 6px;
  display: flex; align-items: center; gap: 8px;
}
.tk-group-title::before { content: ''; width: 3px; height: 13px; background: var(--blue); border-radius: 2px; }
.tk-group-toggle { cursor: pointer; user-select: none; }
.tk-group-toggle:hover { color: var(--blue); }
.tk-group-count { font-size: 11px; font-weight: 400; color: var(--text-dim); }
.tk-fold { font-size: 10px; color: var(--text-dim); width: 12px; display: inline-block; }
.tk-drag-handle { font-size: 11px; color: var(--text-dim); cursor: grab; }
.tk-drag-handle:active { cursor: grabbing; }
.tk-group-dragging { opacity: 0.4; }
.tk-group-drop-zone { outline: 2px dashed var(--blue); outline-offset: 2px; border-radius: 6px; }
.tk-stock-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.tk-chip {
  display: inline-flex; align-items: center; gap: 5px; font-size: 12.5px;
  padding: 5px 12px; border: 1px solid var(--border); border-radius: 16px;
  background: var(--card-2); cursor: pointer; user-select: none;
}
.tk-chip.on { border-color: var(--blue); color: var(--blue); background: #e8f3ff; }
.tk-chip input { margin: 0; }
.tk-chip-code { font-size: 11px; color: var(--text-dim); }
.tk-chip.on .tk-chip-code { color: var(--blue); }
.tk-chip-mode { font-size: 10px; color: #b45309; background: #fef3c7; border-radius: 8px; padding: 0 6px; }
.tk-chart-wrap { border: 1px solid var(--border); border-radius: 10px; padding: 8px; background: #fff; }
.tk-chart { width: 100%; height: 500px; }
</style>
