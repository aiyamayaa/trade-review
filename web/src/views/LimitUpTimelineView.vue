<script setup>
import { ref, computed, onMounted } from 'vue';
import { fetchData, fetchStockMap, fetchStockUrls } from '../api.js';
import { fmtPct, formatDate } from '../utils.js';

const json = ref(null);
const error = ref('');
const loading = ref(false);

// 个股 → { industry, concepts[] } 反向索引
const stockMap = ref(null);
// 个股 URL 映射（code → url，从 ths_stock_info.json 加载）
const stockUrlMap = ref({});
onMounted(async () => {
  try {
    stockMap.value = (await fetchStockMap()).map || {};
  } catch (e) {
    console.warn('个股归属映射加载失败:', e);
  }
  try {
    stockUrlMap.value = (await fetchStockUrls()).urls || {};
  } catch (e) {
    console.warn('个股URL映射加载失败:', e);
  }
});

function stockUrl(code) {
  return stockUrlMap.value[code] || '';
}

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

// 每天涨停股（按日期分组，用于时间轴）
const dailyUpTimeline = computed(() => {
  if (!json.value) return [];
  return dates.value.map((dt) => ({
    date: dt,
    boards: json.value.data[dt]?.limit_up_stocks || [],
  }));
});

// 按连板数分组（一板/二板/三板/四板以上）
function boardsByLevel(boards, level) {
  if (level === 1) return boards.filter((b) => b.board === 1);
  if (level === 2) return boards.filter((b) => b.board === 2);
  if (level === 3) return boards.filter((b) => b.board === 3);
  return boards.filter((b) => b.board >= 4);
}

// 悬浮详情（智能避边：右侧/底部空间不足时翻到鼠标左侧/上方，防止被屏幕边缘遮挡）
const hoveredStock = ref(null);
const hoverPos = ref({ x: 0, y: 0 });
function smartHoverPos(e) {
  const PAD = 16;
  const W = 260; // .hover-detail 宽度
  const H = 340; // 卡片内容高度上限（9 行数据 + 标题）
  let x = e.clientX + PAD;
  if (x + W > window.innerWidth - 8) x = e.clientX - W - PAD;
  if (x < 8) x = 8;
  let y = e.clientY + PAD;
  if (y + H > window.innerHeight - 8) y = e.clientY - H - PAD;
  if (y < 8) y = 8;
  return { x, y };
}
function setHover(s, e) {
  hoveredStock.value = s;
  if (e) hoverPos.value = smartHoverPos(e);
}
function moveHover(e) {
  if (e) hoverPos.value = smartHoverPos(e);
}
function clearHover() {
  hoveredStock.value = null;
}

// 概念分类查找
const brainMap = ref(loadBrainMap());
function loadBrainMap() {
  try {
    const s = localStorage.getItem('ticai_brainmap');
    if (s) return JSON.parse(s);
  } catch (e) { /* ignore */ }
  return { trees: [] };
}

function findCategory(code, industry) {
  const meta = stockMap.value && stockMap.value[code];
  if (meta && meta.concepts && meta.concepts.length) return meta.concepts[0];
  for (const tree of brainMap.value.trees) {
    if ((tree.leaves || []).includes(code)) return tree.name;
    for (const ch of (tree.children || [])) {
      if ((ch.leaves || []).includes(code)) return `${tree.name} > ${ch.name}`;
    }
    if (industry) {
      if (tree.name.includes(industry) || industry.includes(tree.name)) return tree.name;
      for (const ch of (tree.children || [])) {
        if (ch.name.includes(industry) || industry.includes(ch.name)) return `${tree.name} > ${ch.name}`;
      }
    }
  }
  return '';
}

function stockIndustryOf(s) {
  const meta = stockMap.value && stockMap.value[s.code];
  return (meta && meta.industry) || s.industry || '其他行业';
}

function stockConceptsText(s) {
  const meta = stockMap.value && stockMap.value[s.code];
  const list = (meta && meta.concepts) || [];
  if (list.length) {
    return list.length > 3 ? `${list.slice(0, 3).join('、')} 等${list.length}个` : list.join('、');
  }
  return findCategory(s.code, s.industry) || '未分类';
}

// 时间轴标签悬浮高亮
function tagHlClass(code) {
  if (!hoveredStock.value) return '';
  return hoveredStock.value.code === code ? 'hl' : 'dim';
}

function fmtTime(t) {
  if (!t) return '-';
  const s = String(t);
  if (s.length === 6) return `${s.slice(0, 2)}:${s.slice(2, 4)}:${s.slice(4, 6)}`;
  return s;
}

function fmtYi(yuan) {
  if (yuan == null) return '-';
  const n = Number(yuan);
  if (!isFinite(n)) return '-';
  if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(2) + ' 亿';
  if (Math.abs(n) >= 1e4) return (n / 1e4).toFixed(2) + ' 万';
  return n.toFixed(0);
}
</script>

<template>
  <div v-if="loading" class="loading">加载中…</div>
  <div v-else-if="error" class="error">⚠ {{ error }}</div>
  <div v-else-if="json">
    <div class="panel">
      <h2>涨停时间轴<span style="font-size:12px;color:var(--text-dim);margin-left:8px">按日期展示每天的涨停个股，按连板数分层</span></h2>

      <div class="up-tl-wrap">
        <div class="up-tl-v">
          <div v-for="d in dailyUpTimeline" :key="d.date" class="up-tl-v-row">
            <!-- 左侧：日期轴节点 -->
            <div class="up-tl-v-axis">
              <span class="up-tl-v-date">{{ formatDate(d.date) }}</span>
              <span class="up-tl-v-dot"></span>
            </div>
            <!-- 右侧：按连板数分层（全部显示） -->
            <div class="up-tl-v-body">
              <div v-if="!d.boards.length" class="up-tl-v-none">无涨停数据</div>
              <div v-for="lv in [4, 3, 2, 1]" :key="lv" v-show="boardsByLevel(d.boards, lv).length" class="up-tl-v-layer">
                <span class="up-tl-v-badge" :class="'up-tl-v-l' + lv">
                  {{ lv === 4 ? '4板+' : lv + '板' }}
                  <i>{{ boardsByLevel(d.boards, lv).length }}</i>
                </span>
                <div class="up-tl-v-tags">
                  <span
                    v-for="s in boardsByLevel(d.boards, lv)"
                    :key="s.code"
                    class="dg-tag"
                    :class="tagHlClass(s.code)"
                    @mouseenter="setHover(s, $event)"
                    @mousemove="moveHover($event)"
                    @mouseleave="clearHover"
                  >
                    <a v-if="stockUrl(s.code)" :href="stockUrl(s.code)" target="_blank" rel="noopener" class="stock-link" @click.stop>{{ s.name }}</a>
                    <span v-else>{{ s.name }}</span>
                    <b>{{ s.board }}板</b>
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 悬浮详情面板 -->
    <div
      v-if="hoveredStock"
      class="hover-detail"
      :style="{ left: hoverPos.x + 'px', top: hoverPos.y + 'px' }"
    >
      <div class="hd-title">
        {{ hoveredStock.name }} · {{ hoveredStock.code }}
      </div>
      <div class="hd-row">
        <span>最新价</span><b>{{ hoveredStock.last_price ?? '-' }}</b>
      </div>
      <div class="hd-row">
        <span>涨跌幅</span>
        <b :class="hoveredStock.change_pct >= 0 ? 'hd-up' : 'hd-down'">
          {{ fmtPct(hoveredStock.change_pct) }}
        </b>
      </div>
      <div class="hd-row">
        <span>封单金额</span><b>{{ fmtYi(hoveredStock.seal_amount) }}</b>
      </div>
      <div class="hd-row">
        <span>成交金额</span><b>{{ fmtYi(hoveredStock.amount) }}</b>
      </div>
      <div class="hd-row">
        <span>总市值</span><b>{{ fmtYi(hoveredStock.total_mv) }}</b>
      </div>
      <div class="hd-row">
        <span>所属行业</span><b>{{ stockIndustryOf(hoveredStock) }}</b>
      </div>
      <div class="hd-row">
        <span>概念分类</span>
        <b>{{ stockConceptsText(hoveredStock) }}</b>
      </div>
      <div class="hd-row">
        <span>首次涨停</span><b>{{ fmtTime(hoveredStock.first_limit_time) }}</b>
      </div>
      <div class="hd-row">
        <span>连板</span><b>{{ hoveredStock.board || 1 }}板</b>
      </div>
    </div>
  </div>
</template>
