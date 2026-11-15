<script setup>
import { ref, computed, watch, onMounted } from 'vue';
import { fetchData, fetchStockMap, fetchStockUrls, streamStockAnalysis, fetchGranville } from '../api.js';
import {
  fmtYi,
  fmtYi2,
  fmtVol,
  fmtPct,
  formatDate,
  classifyStage,
  STAGE_COLORS,
  renderMarkdown,
  gvClass,
  gvShort,
} from '../utils.js';
import StatCard from '../components/StatCard.vue';
import BarChart from '../components/BarChart.vue';
import AiAnalysisPanel from './AiAnalysisPanel.vue';
import LimitUpAiAnalysis from './LimitUpAiAnalysis.vue';

const json = ref(null);
const error = ref('');
const loading = ref(false);
const selected = ref('');

// 个股 → { industry, concepts[] } 反向索引（data/meta 全量表，思维导图的概念/行业以此为准）
const stockMap = ref(null);
// 个股 URL 映射（code → url，从 ths_stock_info.json 加载）
const stockUrlMap = ref({});
onMounted(async () => {
  try {
    stockMap.value = (await fetchStockMap()).map || {};
  } catch (e) {
    console.warn('个股归属映射加载失败，回退到本地脑图/akshare 行业:', e);
  }
  try {
    stockUrlMap.value = (await fetchStockUrls()).urls || {};
  } catch (e) {
    console.warn('个股URL映射加载失败:', e);
  }
});

// 获取个股URL，无则返回空
function stockUrl(code) {
  return stockUrlMap.value[code] || '';
}

onMounted(load);

async function load() {
  loading.value = true;
  error.value = '';
  try {
    json.value = await fetchData();
    const ds = Object.keys(json.value.data || {}).sort();
    selected.value = ds[ds.length - 1] || '';
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

const meta = computed(() => json.value?.meta || {});
const dates = computed(() =>
  json.value ? Object.keys(json.value.data || {}).sort() : []
);
const day = computed(() =>
  json.value && selected.value ? json.value.data[selected.value] : null
);

// 周期阶段（数据未直接给出，前端按规则计算）
const stage = computed(() => {
  if (!day.value) return null;
  return classifyStage(day.value.max_consecutive_board || 0, day.value.blow_up_rate ?? 0);
});

// 连板数分布
const boardDist = computed(() => {
  if (!day.value) return [];
  const d = day.value.board_distribution || {};
  return Object.keys(d)
    .sort((a, b) => a - b)
    .map((k) => ({ label: k + '板', value: d[k], color: 'var(--red)' }));
});

const indices = computed(() => {
  if (!day.value?.indices) return [];
  return Object.entries(day.value.indices).map(([name, v]) => ({ name, ...v }));
});

const progression = computed(() => day.value?.board_progression || null);
const sectors = computed(() => day.value?.sectors || null);

// 涨停股信息列表（Wind+iFinD，仅最新交易日有）
const stockInfo = computed(() => day.value?.limit_up_stock_info || []);

// 涨停/跌停/炸板个股明细（akshare，每天都有）
const limitUpStocks = computed(() => day.value?.limit_up_stocks || []);
const limitDownStocks = computed(() => day.value?.limit_down_stocks || []);
const blowUpStocks = computed(() => day.value?.blow_up_stocks || []);
const stockTab = ref('up'); // up | down | blow

// ===== 葛南维均线打分（data/stocks/granville/{date}.json，每日 make fetch-granville 采集）=====
const granville = ref(null); // { exists, date, data }
// code → 评分（含次新跳过项 { skipped }），供涨停表格/题材成分股关联
const granvilleMap = computed(() => {
  const m = {};
  for (const s of granville.value?.data?.stocks || []) m[s.code] = s;
  for (const s of granville.value?.data?.skipped || []) m[s.code] = { skipped: s.skip };
  return m;
});
// 当日有涨停股但评分未采集 → 表头提示
const granvilleMissing = computed(
  () => granville.value && !granville.value.exists && limitUpStocks.value.length > 0
);
watch(selected, (d) => loadGranville(d), { immediate: true });

async function loadGranville(date) {
  granville.value = null;
  if (!date) return;
  try {
    granville.value = await fetchGranville(date);
  } catch (e) {
    console.warn('葛南维评分加载失败:', e);
  }
}

// 悬浮提示：均线概览 + 信号明细
function gvTitle(code) {
  const g = granvilleMap.value[code];
  if (!g) return '';
  return [`收盘 ${g.close} | MA5 ${g.ma5} | MA20 ${g.ma20} | MA60 ${g.ma60}`, ...(g.signals || [])].join('\n');
}

// 封单金额 TOP20 涨停股 × 葛南维打分（独立面板用）
const gvExpanded = ref(null);
function toggleGvExpand(code) {
  gvExpanded.value = gvExpanded.value === code ? null : code;
}
const granvilleTop20 = computed(() => {
  if (!granville.value?.exists) return [];
  const ups = [...limitUpStocks.value]
    .sort((a, b) => (b.seal_amount || 0) - (a.seal_amount || 0))
    .slice(0, 20);
  return ups.map((s) => ({ ...s, gv: granvilleMap.value[s.code] || null }));
});

// TOP20 面板排序：连板/封单金额/收盘/MA5/MA20/MA60/分数/评级（默认封单金额降序）
const gvSort = ref('seal_amount');
const gvSortAsc = ref(false);
const GV_RATING_ORDER = { 强烈买入: 5, 推荐买入: 4, 观望: 3, 回避: 2, 强烈回避: 1 };
function gvSortVal(r) {
  const k = gvSort.value;
  if (k === 'board') return r.board || 1;
  if (k === 'seal_amount') return r.seal_amount || 0;
  if (k === 'rating') return GV_RATING_ORDER[gvShort(r.gv?.rating)] || 0;
  // close / ma5 / ma20 / ma60 / score（无评分的排最后）
  return r.gv && r.gv[k] != null ? r.gv[k] : -Infinity;
}
const sortedGranvilleTop20 = computed(() => {
  const dir = gvSortAsc.value ? 1 : -1;
  return [...granvilleTop20.value].sort((a, b) => (gvSortVal(a) - gvSortVal(b)) * dir);
});
function toggleGvSort(key) {
  if (gvSort.value === key) {
    gvSortAsc.value = !gvSortAsc.value;
  } else {
    gvSort.value = key;
    gvSortAsc.value = false;
  }
}

// ===== 个股 AI 分析（内联展开） =====
const analyzingStock = ref(null); // { code, name } | null
const stockOutput = ref('');
const stockThinking = ref('');
const stockShowThinking = ref(false);
const stockStatus = ref('');
const stockError = ref('');
const stockElapsed = ref(0);
const stockToolCalls = ref([]);
let stockElapsedTimer = null;
let stockAborter = null;

const STOCK_TOOL_LABELS = {
  WebSearch: '联网搜索', web_search: '联网搜索',
  WebFetch: '抓取网页', web_fetch: '抓取网页',
  Read: '读取文件', Grep: '检索内容', Bash: '执行命令',
};

function stopStockAnalysis() {
  if (stockAborter) stockAborter.abort();
  clearInterval(stockElapsedTimer);
  analyzingStock.value = null;
  stockStatus.value = '已停止';
}

function analyzeStock(stock) {
  if (analyzingStock.value) return; // 同时只分析一只
  stockOutput.value = '';
  stockThinking.value = '';
  stockError.value = '';
  stockToolCalls.value = [];
  stockStatus.value = `正在分析 ${stock.name}（${stock.code}）明日/后日上涨概率…`;
  stockElapsed.value = 0;
  stockShowThinking.value = true;
  clearInterval(stockElapsedTimer);
  stockElapsedTimer = setInterval(() => { stockElapsed.value += 1; }, 1000);
  analyzingStock.value = { code: stock.code, name: stock.name };

  stockAborter = streamStockAnalysis(stock, {}, (ev, data) => {
    if (ev === 'status') {
      if (data.message) stockStatus.value = data.message;
    } else if (ev === 'heartbeat') {
      if (data.message && !stockOutput.value && !stockThinking.value) stockStatus.value = data.message;
    } else if (ev === 'text') {
      stockOutput.value += data.text;
    } else if (ev === 'thinking') {
      stockThinking.value += data.text;
    } else if (ev === 'tool_use') {
      stockToolCalls.value.unshift({ label: STOCK_TOOL_LABELS[data.name] || data.name });
      if (stockToolCalls.value.length > 10) stockToolCalls.value.length = 10;
    } else if (ev === 'error') {
      stockError.value = data.error || 'AI 分析失败';
    } else if (ev === 'done') {
      clearInterval(stockElapsedTimer);
      if (!stockOutput.value && !stockError.value) stockStatus.value = '分析完成';
    }
  });
}

function fmtTime(t) {
  if (!t) return '-';
  const s = String(t);
  if (s.length === 6) return `${s.slice(0, 2)}:${s.slice(2, 4)}:${s.slice(4, 6)}`;
  return s;
}

// 脑图分类树（与题材脑图共用 localStorage）
const brainMap = ref(loadBrainMap());
function loadBrainMap() {
  try {
    const s = localStorage.getItem('ticai_brainmap');
    if (s) return JSON.parse(s);
  } catch (e) { /* ignore */ }
  return { trees: [] };
}

// 查找个股所属的概念分类：
// 1) 优先 data/meta 全量表（ths_concept_info.json 反向索引，取首个=当日热门概念）
// 2) 回退到本地题材脑图（localStorage）
function findCategory(code, industry) {
  const meta = stockMap.value && stockMap.value[code];
  if (meta && meta.concepts && meta.concepts.length) return meta.concepts[0];
  for (const tree of brainMap.value.trees) {
    if ((tree.leaves || []).includes(code)) return tree.name;
    for (const ch of (tree.children || [])) {
      if ((ch.leaves || []).includes(code)) return `${tree.name} > ${ch.name}`;
    }
    if (industry) {
      if (tree.name.includes(industry) || industry.includes(tree.name)) {
        return tree.name;
      }
      for (const ch of (tree.children || [])) {
        if (ch.name.includes(industry) || industry.includes(ch.name)) {
          return `${tree.name} > ${ch.name}`;
        }
      }
    }
  }
  return '';
}

// 个股行业：优先 meta 行业全量表（同花顺行业板块），回退 akshare 的 industry 字段
function stockIndustryOf(s) {
  const meta = stockMap.value && stockMap.value[s.code];
  return (meta && meta.industry) || s.industry || '其他行业';
}

// ===== 概念分类：单元格平铺全部概念 tag，悬浮某概念时全表同概念高亮 =====
const hoveredConcept = ref(null);

// 个股全部概念列表（优先 meta 概念全量表，回退脑图单概念）
function stockConceptsList(s) {
  const meta = stockMap.value && stockMap.value[s.code];
  const list = (meta && meta.concepts) || [];
  if (list.length) return list;
  const single = findCategory(s.code, s.industry);
  return single ? [single] : [];
}

// ===== 个股明细：涨停/跌停/炸板 关联概念 TOP5 统计 =====
// 统计一组股票各自关联的概念出现次数，取 TOP N
function topConceptsOf(stocks, n = 5) {
  const counter = new Map();
  for (const s of stocks) {
    const meta = stockMap.value && stockMap.value[s.code];
    const list = (meta && meta.concepts) || [];
    for (const c of list) {
      counter.set(c, (counter.get(c) || 0) + 1);
    }
  }
  return [...counter.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, n)
    .map(([name, count]) => ({ name, count }));
}
// 当前 tab（涨停/跌停/炸板）对应的概念 TOP5
const stockConceptTop = computed(() => {
  if (stockTab.value === 'down') return topConceptsOf(limitDownStocks.value);
  if (stockTab.value === 'blow') return topConceptsOf(blowUpStocks.value);
  return topConceptsOf(limitUpStocks.value);
});

// ===== 点击 TOP5 概念 → 高亮表格中关联该概念的股票 =====
const selectedTopConcept = ref(null);
function toggleTopConcept(name) {
  selectedTopConcept.value = selectedTopConcept.value === name ? null : name;
}
// 当前生效的概念（hover 概念 tag 优先，其次点击选中的 TOP5 概念）
const activeConcept = computed(() => hoveredConcept.value || selectedTopConcept.value);

// ===== 跌停/炸板：成交量、总市值字段存在才显示对应列 =====
const downHasAmount = computed(() => limitDownStocks.value.some((s) => s.amount));
const downHasMv = computed(() => limitDownStocks.value.some((s) => s.total_mv));
const blowHasAmount = computed(() => blowUpStocks.value.some((s) => s.amount));
const blowHasMv = computed(() => blowUpStocks.value.some((s) => s.total_mv));

// ===== 涨停个股表格排序 =====
const upSort = ref('seal_amount'); // seal_amount | total_mv | amount | first_limit_time | board | granville
const upSortAsc = ref(false);

// 排序字段取值（首次涨停时间按 HHMMSS 数字比较，空值排最后）
function sortVal(s, key) {
  if (key === 'granville') {
    const g = granvilleMap.value[s.code];
    return g && g.score != null ? g.score : -99999;
  }
  if (key === 'first_limit_time') {
    const t = String(s[key] || '');
    return t ? Number(t) : 999999;
  }
  const n = Number(s[key]);
  return Number.isFinite(n) ? n : -1;
}

const sortedLimitUpStocks = computed(() => {
  const arr = [...limitUpStocks.value];
  const key = upSort.value;
  arr.sort((a, b) => {
    const va = sortVal(a, key);
    const vb = sortVal(b, key);
    return upSortAsc.value ? va - vb : vb - va;
  });
  return arr;
});

function toggleSort(key) {
  if (upSort.value === key) {
    upSortAsc.value = !upSortAsc.value;
  } else {
    upSort.value = key;
    // 首次涨停时间默认早→晚（升序，早盘封板更强势）；其余默认降序
    upSortAsc.value = key === 'first_limit_time';
  }
}

// 从一条涨停股信息里按关键字模糊找字段值（兼容 iFinD 列名变化）
function findField(info, keyword) {
  if (!info) return null;
  for (const k of Object.keys(info)) {
    if (k.includes(keyword)) return info[k];
  }
  return null;
}
function pctText(v) {
  if (v == null || v === '') return '-';
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  return (n > 0 ? '+' : '') + n.toFixed(2) + '%';
}

// 板块排行（转成 stat-card 需要的简洁字段）
function enrichList(list) {
  return (list || []).map((s, i) => ({
    rank: i + 1,
    name: s['板块'],
    pct: s['涨跌幅'],
    netIn: s['净流入'],
    leadName: s['领涨股'],
    leadPct: s['领涨股-涨跌幅'],
  }));
}
const top5Rows = computed(() => enrichList(sectors.value?.top5));
const bottom5Rows = computed(() => enrichList(sectors.value?.bottom5));
</script>

<template>
  <div v-if="loading" class="loading">加载中…</div>
  <div v-else-if="error" class="error">⚠ {{ error }}</div>
  <div v-else-if="day">
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
          <div class="label">交易日数</div>
          <div class="value">{{ meta.total_trading_days ?? '-' }}</div>
        </div>
        <div class="meta-card">
          <div class="label">生成时间</div>
          <div class="value" style="font-size: 13px; font-weight: 400">
            {{ meta.generated_at || '-' }}
          </div>
        </div>
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

    <!-- 涨跌停核心 -->
    <div class="panel">
      <h2>涨跌停核心</h2>
      <div class="stat-grid">
        <StatCard label="涨停家数" :value="day.limit_up_count ?? '-'" accent="red" />
        <StatCard label="跌停家数" :value="day.limit_down_count ?? '-'" accent="green" />
        <StatCard label="炸板家数" :value="day.blow_up_count ?? '-'" accent="gold" />
        <StatCard label="炸板率" :value="(day.blow_up_rate ?? 0) + '%'" accent="gold" />
        <StatCard
          label="最高连板"
          :value="day.max_consecutive_board ?? '-'"
          accent="red"
        />
      </div>
      <div v-if="day.max_consecutive_stocks?.length" style="margin-top: 12px">
        <span class="stat-label">最高连板个股：</span>
        <span
          v-for="s in day.max_consecutive_stocks"
          :key="s"
          class="stock-tag"
          >{{ s }}</span
        >
      </div>
    </div>

    <!-- AI 市场分析：一键按钮 + 流式输出 + 追问 -->
    <AiAnalysisPanel />

    <!-- 涨停/跌停/炸板个股明细（akshare） -->
    <div class="panel">
      <h2>个股明细
        <span v-if="granvilleMissing" class="gv-miss-hint">
          当日葛南维评分未采集，执行 <code>make fetch-granville</code> 后刷新
        </span>
      </h2>
      <div class="stock-tabs">
        <button :class="{ active: stockTab === 'up' }" @click="stockTab = 'up'">
          涨停 {{ limitUpStocks.length }}
        </button>
        <button :class="{ active: stockTab === 'down' }" @click="stockTab = 'down'">
          跌停 {{ limitDownStocks.length }}
        </button>
        <button :class="{ active: stockTab === 'blow' }" @click="stockTab = 'blow'">
          炸板 {{ blowUpStocks.length }}
        </button>
      </div>
      <!-- 当前 tab 的关联概念 TOP5 统计（点击概念高亮表格中关联该概念的股票） -->
      <div class="concept-top-bar" v-if="stockConceptTop.length">
        <span class="ct-label">关联概念 TOP{{ stockConceptTop.length }}</span>
        <span
          v-for="(c, i) in stockConceptTop"
          :key="c.name"
          class="ct-item"
          :class="['ct-rank' + (i + 1), { selected: c.name === selectedTopConcept }]"
          :title="`${c.name}：${stockTab === 'up' ? '涨停' : stockTab === 'down' ? '跌停' : '炸板'}股中 ${c.count} 只关联，点击高亮`"
          @click="toggleTopConcept(c.name)"
        >
          <i>{{ i + 1 }}</i>{{ c.name }}<b>{{ c.count }}只</b>
        </span>
        <button v-if="selectedTopConcept" class="ct-clear" @click="selectedTopConcept = null">
          ✕ 取消高亮（{{ selectedTopConcept }}）
        </button>
        <span class="ct-hint">点击概念高亮关联个股</span>
      </div>
      <div style="overflow: auto; max-height: 480px">
        <div v-if="stockTab === 'up'">
          <table>
            <thead>
              <tr>
                <th class="left" style="cursor:pointer" @click="toggleSort('board')">连板 <span v-if="upSort==='board'" class="up-grid-arrow">{{ upSortAsc ? '↑' : '↓' }}</span></th>
                <th class="left">代码</th>
                <th class="left">名称</th>
                <th>涨跌幅</th>
                <th class="left" style="cursor:pointer" @click="toggleSort('seal_amount')">封单金额 <span v-if="upSort==='seal_amount'" class="up-grid-arrow">{{ upSortAsc ? '↑' : '↓' }}</span></th>
                <th class="left" style="cursor:pointer" @click="toggleSort('amount')">成交金额 <span v-if="upSort==='amount'" class="up-grid-arrow">{{ upSortAsc ? '↑' : '↓' }}</span></th>
                <th class="left" style="cursor:pointer" @click="toggleSort('total_mv')">总市值 <span v-if="upSort==='total_mv'" class="up-grid-arrow">{{ upSortAsc ? '↑' : '↓' }}</span></th>
                <th class="left" style="cursor:pointer" @click="toggleSort('first_limit_time')">首次涨停 <span v-if="upSort==='first_limit_time'" class="up-grid-arrow">{{ upSortAsc ? '↑' : '↓' }}</span></th>
                <th class="left">所属行业</th>
                <th class="left">概念分类</th>
                <th class="left" style="cursor:pointer" @click="toggleSort('granville')">葛南维 <span v-if="upSort==='granville'" class="up-grid-arrow">{{ upSortAsc ? '↑' : '↓' }}</span></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="s in sortedLimitUpStocks"
                :key="s.code"
                :class="{ 'row-hl': selectedTopConcept && stockConceptsList(s).includes(selectedTopConcept) }"
              >
                <td class="left">
                  <button
                    class="ai-analyze-btn"
                    :class="{ active: analyzingStock && analyzingStock.code === s.code }"
                    :disabled="analyzingStock && analyzingStock.code !== s.code"
                    title="AI 分析该股明日/后日上涨概率"
                    @click.stop="analyzeStock(s)"
                  >🤖</button>
                  <b v-if="s.board > 1" class="up-tree-board">{{ s.board }}板</b><span v-else>1板</span>
                </td>
                <td class="left">{{ s.code }}</td>
                <td class="left">
                  <a v-if="stockUrl(s.code)" :href="stockUrl(s.code)" target="_blank" rel="noopener" class="stock-link">{{ s.name }}</a>
                  <span v-else>{{ s.name }}</span>
                </td>
                <td class="up">{{ fmtPct(s.change_pct) }}</td>
                <td>{{ fmtYi(s.seal_amount) }}</td>
                <td>{{ fmtYi(s.amount) }}</td>
                <td>{{ fmtYi(s.total_mv) }}</td>
                <td>{{ fmtTime(s.first_limit_time) }}</td>
                <td class="left">{{ stockIndustryOf(s) }}</td>
                <td class="left td-concepts-flat">
                  <span
                    v-for="c in stockConceptsList(s)"
                    :key="c"
                    class="con-tag"
                    :class="{ hl: c === activeConcept, dim: activeConcept && c !== activeConcept }"
                    @mouseenter="hoveredConcept = c"
                    @mouseleave="hoveredConcept = null"
                  >{{ c }}</span>
                  <span v-if="!stockConceptsList(s).length" class="dim-txt">-</span>
                </td>
                <td class="left">
                  <span
                    v-if="granvilleMap[s.code] && granvilleMap[s.code].score != null"
                    class="gv-score"
                    :class="gvClass(granvilleMap[s.code].score)"
                    :title="gvTitle(s.code)"
                  >{{ granvilleMap[s.code].score }}·{{ gvShort(granvilleMap[s.code].rating) }}</span>
                  <span
                    v-else-if="granvilleMap[s.code] && granvilleMap[s.code].skipped"
                    class="dim-txt"
                    :title="granvilleMap[s.code].skipped"
                  >次新</span>
                  <span v-else class="dim-txt">-</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 个股 AI 分析内联面板 -->
        <div v-if="analyzingStock || stockOutput || stockError" class="stock-ai-panel">
          <div class="stock-ai-head">
            <span class="stock-ai-title">
              🤖 AI 分析 · {{ analyzingStock ? analyzingStock.name : '' }}（{{ analyzingStock ? analyzingStock.code : '' }}）
              <template v-if="analyzingStock"> · 明日/后日上涨概率</template>
            </span>
            <button v-if="analyzingStock" class="ai-stop-btn" @click="stopStockAnalysis">■ 停止</button>
          </div>
          <div v-if="stockStatus" class="stock-ai-status">
            <span class="luai-spin"></span>{{ stockStatus }}
            <span v-if="stockToolCalls.length" class="stock-ai-tools">· 🔧 {{ stockToolCalls[0].label }}中…（累计 {{ stockToolCalls.length }} 次）</span>
            <span class="stock-ai-elapsed">· ⏱ {{ stockElapsed }} 秒</span>
          </div>
          <div v-if="stockError" class="stock-ai-error">{{ stockError }}</div>
          <div v-if="stockThinking" class="stock-ai-thinking">
            <button class="tg-btn" @click="stockShowThinking = !stockShowThinking">
              {{ stockShowThinking ? '▾' : '▸' }} 思考过程{{ analyzingStock ? '（进行中…）' : '' }}
            </button>
            <pre v-if="stockShowThinking && stockThinking" class="thinking-text">{{ stockThinking }}</pre>
          </div>
          <div v-if="stockOutput" class="md-body" v-html="renderMarkdown(stockOutput)"></div>
          <div v-else-if="analyzingStock && !stockOutput && !stockError" class="stock-ai-empty">
            AI 正在联网核实涨停细节 / 题材催化 / 资金流向 / 基本面，分析结果将在这里实时输出…
          </div>
        </div>

        <table v-else-if="stockTab === 'down'">
          <thead>
            <tr>
              <th class="left">代码</th>
              <th class="left">名称</th>
              <th>涨跌幅</th>
              <th class="left">行业</th>
              <th>最新价</th>
              <th>换手率</th>
              <th v-if="downHasAmount">成交金额</th>
              <th v-if="downHasMv">总市值</th>
              <th class="left">概念分类</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="s in limitDownStocks"
              :key="s.code"
              :class="{ 'row-hl': selectedTopConcept && stockConceptsList(s).includes(selectedTopConcept) }"
            >
              <td class="left">{{ s.code }}</td>
              <td class="left">
                <a v-if="stockUrl(s.code)" :href="stockUrl(s.code)" target="_blank" rel="noopener" class="stock-link">{{ s.name }}</a>
                <span v-else>{{ s.name }}</span>
              </td>
              <td class="down">{{ fmtPct(s.change_pct) }}</td>
              <td class="left">{{ stockIndustryOf(s) }}</td>
              <td>{{ s.last_price ?? '-' }}</td>
              <td>{{ s.turnover_rate != null ? s.turnover_rate + '%' : '-' }}</td>
              <td v-if="downHasAmount">{{ fmtYi(s.amount) }}</td>
              <td v-if="downHasMv">{{ fmtYi(s.total_mv) }}</td>
              <td class="left td-concepts-flat">
                <span
                  v-for="c in stockConceptsList(s)"
                  :key="c"
                  class="con-tag"
                  :class="{ hl: c === activeConcept, dim: activeConcept && c !== activeConcept }"
                  @mouseenter="hoveredConcept = c"
                  @mouseleave="hoveredConcept = null"
                >{{ c }}</span>
                <span v-if="!stockConceptsList(s).length" class="dim-txt">-</span>
              </td>
            </tr>
          </tbody>
        </table>
        <table v-else>
          <thead>
            <tr>
              <th class="left">代码</th>
              <th class="left">名称</th>
              <th>涨跌幅</th>
              <th class="left">行业</th>
              <th>首次涨停</th>
              <th>炸板次数</th>
              <th v-if="blowHasAmount">成交金额</th>
              <th v-if="blowHasMv">总市值</th>
              <th class="left">概念分类</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="s in blowUpStocks"
              :key="s.code"
              :class="{ 'row-hl': selectedTopConcept && stockConceptsList(s).includes(selectedTopConcept) }"
            >
              <td class="left">{{ s.code }}</td>
              <td class="left">
                <a v-if="stockUrl(s.code)" :href="stockUrl(s.code)" target="_blank" rel="noopener" class="stock-link">{{ s.name }}</a>
                <span v-else>{{ s.name }}</span>
              </td>
              <td :class="s.change_pct >= 0 ? 'up' : 'down'">{{ fmtPct(s.change_pct) }}</td>
              <td class="left">{{ stockIndustryOf(s) }}</td>
              <td>{{ fmtTime(s.first_limit_time) }}</td>
              <td>{{ s.blow_times || 0 }}</td>
              <td v-if="blowHasAmount">{{ fmtYi(s.amount) }}</td>
              <td v-if="blowHasMv">{{ fmtYi(s.total_mv) }}</td>
              <td class="left td-concepts-flat">
                <span
                  v-for="c in stockConceptsList(s)"
                  :key="c"
                  class="con-tag"
                  :class="{ hl: c === activeConcept, dim: activeConcept && c !== activeConcept }"
                  @mouseenter="hoveredConcept = c"
                  @mouseleave="hoveredConcept = null"
                >{{ c }}</span>
                <span v-if="!stockConceptsList(s).length" class="dim-txt">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 封单 TOP20 葛南维打分（每日 make fetch-granville 采集，点击行展开信号明细） -->
    <div class="panel" v-if="granville && granville.exists && granvilleTop20.length">
      <h2>封单 TOP20 葛南维打分</h2>
      <div class="gv-sub">
        按封单金额取前 20 只涨停股 × 葛南维均线评分 · 点击行展开信号明细 · 采集于
        {{ granville.data.generated_at }}
      </div>
      <div style="overflow-x: auto">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th class="left">名称</th>
              <th class="left">代码</th>
              <th style="cursor:pointer" @click="toggleGvSort('board')">连板 <span v-if="gvSort==='board'" class="up-grid-arrow">{{ gvSortAsc ? '↑' : '↓' }}</span></th>
              <th class="left" style="cursor:pointer" @click="toggleGvSort('seal_amount')">封单金额 <span v-if="gvSort==='seal_amount'" class="up-grid-arrow">{{ gvSortAsc ? '↑' : '↓' }}</span></th>
              <th style="cursor:pointer" @click="toggleGvSort('close')">收盘 <span v-if="gvSort==='close'" class="up-grid-arrow">{{ gvSortAsc ? '↑' : '↓' }}</span></th>
              <th style="cursor:pointer" @click="toggleGvSort('ma5')">MA5 <span v-if="gvSort==='ma5'" class="up-grid-arrow">{{ gvSortAsc ? '↑' : '↓' }}</span></th>
              <th style="cursor:pointer" @click="toggleGvSort('ma20')">MA20 <span v-if="gvSort==='ma20'" class="up-grid-arrow">{{ gvSortAsc ? '↑' : '↓' }}</span></th>
              <th style="cursor:pointer" @click="toggleGvSort('ma60')">MA60 <span v-if="gvSort==='ma60'" class="up-grid-arrow">{{ gvSortAsc ? '↑' : '↓' }}</span></th>
              <th style="cursor:pointer" @click="toggleGvSort('score')">分数 <span v-if="gvSort==='score'" class="up-grid-arrow">{{ gvSortAsc ? '↑' : '↓' }}</span></th>
              <th class="left" style="cursor:pointer" @click="toggleGvSort('rating')">评级 <span v-if="gvSort==='rating'" class="up-grid-arrow">{{ gvSortAsc ? '↑' : '↓' }}</span></th>
              <th class="left">建议</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(r, i) in sortedGranvilleTop20" :key="r.code">
              <tr
                class="gv-row"
                :class="{ 'gv-open': gvExpanded === r.code }"
                @click="toggleGvExpand(r.code)"
              >
                <td>{{ i + 1 }}</td>
                <td class="left">{{ r.name }}</td>
                <td class="left">{{ r.code }}</td>
                <td>{{ r.board || 1 }}板</td>
                <td>{{ fmtYi(r.seal_amount) }}</td>
                <td v-if="r.gv && r.gv.score != null">{{ r.gv.close }}</td>
                <td v-else class="dim-txt" :title="r.gv ? r.gv.skipped : '未采集'">{{ r.gv ? '次新' : '-' }}</td>
                <td v-if="r.gv && r.gv.score != null">{{ r.gv.ma5 }}</td><td v-else>-</td>
                <td v-if="r.gv && r.gv.score != null">{{ r.gv.ma20 }}</td><td v-else>-</td>
                <td v-if="r.gv && r.gv.score != null">{{ r.gv.ma60 }}</td><td v-else>-</td>
                <td v-if="r.gv && r.gv.score != null" class="gv-score" :class="gvClass(r.gv.score)">{{ r.gv.score }}</td>
                <td v-else>-</td>
                <td class="left" v-if="r.gv && r.gv.score != null">{{ gvShort(r.gv.rating) }}</td>
                <td class="left dim-txt" v-else>未打分</td>
                <td class="left" v-if="r.gv && r.gv.score != null">
                  <span :class="gvClass(r.gv.score)" style="font-weight: 600">{{ r.gv.suggestion }}</span>
                </td>
                <td v-else>-</td>
              </tr>
              <tr v-if="gvExpanded === r.code" class="gv-detail-row">
                <td colspan="12">
                  <div v-if="r.gv && r.gv.signals && r.gv.signals.length" class="gv-signals">{{ r.gv.signals.join('\n') }}</div>
                  <div v-else class="dim-txt">{{ r.gv ? r.gv.skipped : '该股不在当日葛南维评分结果中' }}</div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 涨停股信息列表（Wind+iFinD，仅最新交易日有） -->
    <div class="panel">
      <h2>涨停股信息{{ stockInfo.length ? `（${stockInfo.length} 只）` : '' }}</h2>
      <div v-if="stockInfo.length" style="overflow-x: auto">
        <table class="stock-info-table">
          <thead>
            <tr>
              <th class="left">代码</th>
              <th class="left">名称</th>
              <th>涨停时间</th>
              <th>涨跌幅</th>
              <th class="left">控股股东</th>
              <th class="left">主营业务</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in stockInfo" :key="s['代码']">
              <td class="left">{{ s['代码'] || '-' }}</td>
              <td class="left">
                <a v-if="s['代码'] && stockUrl(s['代码'])" :href="stockUrl(s['代码'])" target="_blank" rel="noopener" class="stock-link">{{ s['名称'] || '-' }}</a>
                <span v-else>{{ s['名称'] || '-' }}</span>
              </td>
              <td>{{ s['涨停时间'] || '-' }}</td>
              <td class="up">{{ pctText(findField(s, '涨跌幅')) }}</td>
              <td class="left">{{ findField(s, '控股股东') || '-' }}</td>
              <td class="left">{{ findField(s, '主营业务') || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty">
        暂无涨停股基础信息（控股股东/主营业务等）。需在 Wind/iFinD 插件环境运行
        <code>make fetch-limit-info</code> 采集后展示。
      </div>
    </div>

    <!-- 涨停股信息 AI 分析：题材分类（列全个股）/ 催化原因 / 财报披露，结果按天缓存 data/analysis/ -->
    <LimitUpAiAnalysis :date="selected" />

    <!-- 连板分布 -->
    <div class="panel">
      <h2>连板数分布</h2>
      <BarChart :items="boardDist" :value-fmt="(v) => v + ' 只'" color="var(--red)" />
    </div>

    <!-- 连板进阶 -->
    <div class="panel" v-if="progression">
      <h2>连板进阶（N 进 N+1 成功数）</h2>
      <div class="stat-grid">
        <StatCard label="1 进 2" :value="progression['1to2'] ?? 0" accent="blue" />
        <StatCard label="2 进 3" :value="progression['2to3'] ?? 0" accent="blue" />
        <StatCard label="3 进 4" :value="progression['3to4'] ?? 0" accent="blue" />
        <StatCard label="4 进 5" :value="progression['4to5'] ?? 0" accent="blue" />
      </div>
    </div>

    <!-- 三大指数 -->
    <div class="panel">
      <h2>三大指数</h2>
      <div class="stat-grid">
        <div
          v-for="idx in indices"
          :key="idx.name"
          class="stat-card"
          :class="idx.pct_change >= 0 ? 'red' : 'green'"
        >
          <div class="stat-label">{{ idx.name }}</div>
          <div class="stat-value">{{ idx.close ?? '-' }}</div>
          <div class="stat-sub">
            涨跌 {{ fmtPct(idx.pct_change) }} · 量 {{ fmtVol(idx.volume) }}<br />
            MA5 {{ idx.ma5 ?? '-' }} · MA10 {{ idx.ma10 ?? '-' }}
          </div>
        </div>
      </div>
    </div>

    <!-- 资金面 -->
    <div class="grid-2">
      <div class="panel">
        <h2>融资余额</h2>
        <div class="stat-grid">
          <StatCard
            label="沪市融资"
            :value="fmtYi(day.margin?.sh_margin_balance)"
            accent="blue"
          />
          <StatCard
            label="深市融资"
            :value="fmtYi(day.margin?.sz_margin_balance)"
            accent="blue"
          />
          <StatCard
            label="两市合计"
            :value="fmtYi(day.margin?.total_margin_balance)"
            accent="blue"
          />
        </div>
        <div class="stat-sub" style="margin-top: 8px; color: var(--text-dim)">
          * 融资余额 T+1 更新，最新一天可能为 -
        </div>
      </div>
      <div class="panel">
        <h2>北向资金（沪深港通）</h2>
        <div class="stat-grid">
          <StatCard
            label="沪股通净买"
            :value="fmtYi2(day.north_flow?.sh_net_buy)"
            accent="green"
          />
          <StatCard
            label="深股通净买"
            :value="fmtYi2(day.north_flow?.sz_net_buy)"
            accent="green"
          />
          <StatCard
            label="合计净买"
            :value="fmtYi2(day.north_flow?.total_net_buy)"
            accent="green"
          />
        </div>
        <div class="stat-sub" style="margin-top: 8px; color: var(--text-dim)">
          * 2024 年起北向实时数据不再披露，字段可能缺失或为 0
        </div>
      </div>
    </div>

    <!-- 权重板块动向 -->
    <div class="panel" v-if="sectors">
      <h2>权重板块动向（最新交易日）</h2>
      <div class="grid-2">
        <div>
          <h2 style="color: var(--red)">涨幅前 5</h2>
          <div class="stat-grid">
            <div v-for="r in top5Rows" :key="r.name" class="stat-card red">
              <div class="stat-label">{{ r.rank }}. {{ r.name }}</div>
              <div class="stat-value up">{{ fmtPct(r.pct) }}</div>
              <div class="stat-sub">
                净流入 {{ fmtYi2(r.netIn) }} · 领涨
                {{ r.leadName }} <span class="up">{{ fmtPct(r.leadPct) }}</span>
              </div>
            </div>
          </div>
        </div>
        <div>
          <h2 style="color: var(--green)">跌幅前 5</h2>
          <div class="stat-grid">
            <div v-for="r in bottom5Rows" :key="r.name" class="stat-card green">
              <div class="stat-label">{{ r.rank }}. {{ r.name }}</div>
              <div class="stat-value down">{{ fmtPct(r.pct) }}</div>
              <div class="stat-sub">净流入 {{ fmtYi2(r.netIn) }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
