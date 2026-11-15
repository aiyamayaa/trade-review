<script setup>
import { ref, computed, onMounted } from 'vue';
import { fetchMeetings } from '../api.js';

// 政策/会议日历页：数据源 data/meta/meeting.json（修改后刷新即生效）
const events = ref([]);
const loading = ref(false);
const error = ref('');
const keyword = ref('');
const cycleFilter = ref('all');
const sortByPriority = ref(true);

onMounted(load);

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const r = await fetchMeetings();
    events.value = r.events || [];
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

// 周期类型元信息（label + 配色）
const CYCLE_META = {
  yearly: { label: '年度', color: '#1890ff' },
  quarterly: { label: '季度', color: '#722ed1' },
  weekly: { label: '每周', color: '#52c41a' },
  once: { label: '一次性', color: '#eb2f96' },
  long_cycle: { label: '长周期', color: '#fa8c16' },
  irregular: { label: '不定期', color: '#8c8c8c' },
};
// 分组展示顺序（重要→次要）
const CYCLE_ORDER = ['yearly', 'quarterly', 'weekly', 'once', 'long_cycle', 'irregular'];

function cycleMeta(cycle) {
  return CYCLE_META[cycle] || { label: cycle || '未知', color: '#8c8c8c' };
}

// 月份 → 文本（支持 number / 数组 / null）
function monthText(m) {
  if (m == null) return '';
  if (Array.isArray(m)) return m.map((x) => `${x}月`).join('/');
  return `${m}月`;
}

// 时间描述：月份 + 日期区间 / 特殊日期 / 待定
function timeText(ev) {
  const m = monthText(ev.month);
  const d = ev.day_range;
  if (m && d) return `${m} ${d}`;
  if (m) return m;
  if (d) return d;
  return '时间待定';
}

// 优先级：1-5，5 最高
function priorityClass(p) {
  if (p >= 5) return 'p5';
  if (p === 4) return 'p4';
  if (p === 3) return 'p3';
  return 'p-low';
}
function starText(p) {
  return '★'.repeat(p) + '☆'.repeat(Math.max(0, 5 - p));
}

// 统计
const total = computed(() => events.value.length);
const fixedCount = computed(() => events.value.filter((e) => e.is_fixed_cycle).length);
const irregularCount = computed(() => events.value.filter((e) => !e.is_fixed_cycle).length);
const topCount = computed(() => events.value.filter((e) => e.priority >= 5).length);

// 筛选 + 分组
const filtered = computed(() => {
  let list = events.value.slice();
  if (cycleFilter.value !== 'all') {
    list = list.filter((e) => e.cycle === cycleFilter.value);
  }
  const kw = keyword.value.trim().toLowerCase();
  if (kw) {
    list = list.filter(
      (e) =>
        (e.event || '').toLowerCase().includes(kw) ||
        (e.keywords || []).some((k) => String(k).toLowerCase().includes(kw))
    );
  }
  if (sortByPriority.value) {
    list.sort((a, b) => (b.priority || 0) - (a.priority || 0));
  }
  return list;
});

const groups = computed(() => {
  const map = new Map();
  for (const c of CYCLE_ORDER) {
    const list = filtered.value.filter((e) => e.cycle === c);
    if (list.length) map.set(c, list);
  }
  // 未在预设顺序里的 cycle 兜底追加
  for (const e of filtered.value) {
    if (!map.has(e.cycle)) map.set(e.cycle, []);
    if (!map.get(e.cycle).includes(e)) map.get(e.cycle).push(e);
  }
  return [...map.entries()].map(([cycle, list]) => ({ cycle, list }));
});

const cycleOptions = computed(() => {
  const seen = new Set();
  const opts = [];
  for (const c of CYCLE_ORDER) {
    if (events.value.some((e) => e.cycle === c) && !seen.has(c)) {
      seen.add(c);
      opts.push({ value: c, ...cycleMeta(c) });
    }
  }
  return opts;
});

// 周期筛选按钮（全部 + 各类型）
const filters = computed(() => [
  { value: 'all', label: '全部', color: '#2c3142' },
  ...cycleOptions.value,
]);
</script>

<template>
  <div>
    <!-- 统计卡片 -->
    <div class="panel">
      <div class="stat-grid">
        <div class="stat-card blue">
          <div class="stat-label">会议总数</div>
          <div class="stat-value">{{ total }}</div>
        </div>
        <div class="stat-card green">
          <div class="stat-label">固定周期</div>
          <div class="stat-value">{{ fixedCount }}</div>
        </div>
        <div class="stat-card gold">
          <div class="stat-label">不定期</div>
          <div class="stat-value">{{ irregularCount }}</div>
        </div>
        <div class="stat-card red">
          <div class="stat-label">最高优先级（P5）</div>
          <div class="stat-value">{{ topCount }}</div>
        </div>
      </div>
    </div>

    <div class="panel">
      <h2>
        政策 / 会议日历
        <span class="lk-sub" v-if="!loading && !error">
          数据源：data/meta/meeting.json（修改后刷新即生效）
        </span>
      </h2>

      <!-- 工具栏 -->
      <div class="toolbar" style="margin-bottom: 16px">
        <input v-model="keyword" class="search" placeholder="搜索会议名称 / 关键词…" />
        <button
          v-for="f in filters"
          :key="f.value"
          class="view-switch"
          :class="{ active: cycleFilter === f.value }"
          @click="cycleFilter = f.value"
        >
          {{ f.label }}
        </button>
        <button
          class="sort-dir-btn"
          :class="{ on: sortByPriority }"
          @click="sortByPriority = !sortByPriority"
        >
          {{ sortByPriority ? '优先级排序' : '原始顺序' }}
        </button>
        <span class="toolbar-hint">{{ filtered.length }} 项</span>
      </div>

      <div v-if="loading" class="loading">加载中…</div>
      <div v-else-if="error" class="error">⚠ {{ error }}</div>
      <div v-else-if="!filtered.length" class="empty">没有匹配的会议</div>

      <!-- 按周期分组 -->
      <div v-for="g in groups" :key="g.cycle" class="meet-group">
        <div class="meet-group-title" :style="{ '--gc': cycleMeta(g.cycle).color }">
          <span class="mgt-badge" :style="{ background: cycleMeta(g.cycle).color }">
            {{ cycleMeta(g.cycle).label }}
          </span>
          <span class="mgt-count">{{ g.list.length }} 项</span>
        </div>

        <div class="meet-grid">
          <div v-for="ev in g.list" :key="ev.event" class="meet-card">
            <div class="meet-head">
              <span class="meet-name">{{ ev.event }}</span>
              <span class="meet-priority" :class="priorityClass(ev.priority)">
                P{{ ev.priority }}
              </span>
            </div>

            <div class="meet-row">
              <span class="meet-time">🕒 {{ timeText(ev) }}</span>
              <span class="meet-fixed" :class="{ no: !ev.is_fixed_cycle }">
                {{ ev.is_fixed_cycle ? '固定周期' : '不定期' }}
              </span>
            </div>

            <div class="meet-stars" :title="'优先级 ' + ev.priority + '/5'">
              {{ starText(ev.priority) }}
            </div>

            <div v-if="ev.remind_days_before > 0" class="meet-remind">
              🔔 提前 {{ ev.remind_days_before }} 天提醒
            </div>

            <div v-if="ev.keywords && ev.keywords.length" class="meet-kws">
              <span v-for="k in ev.keywords" :key="k" class="stock-tag">{{ k }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.meet-group {
  margin-bottom: 24px;
}
.meet-group-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--gc, var(--blue));
}
.mgt-badge {
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  border-radius: 6px;
  padding: 3px 12px;
}
.mgt-count {
  font-size: 12px;
  color: var(--text-dim);
}
.meet-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.meet-card {
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
  transition: all 0.15s;
}
.meet-card:hover {
  border-color: var(--blue);
  box-shadow: 0 4px 14px rgba(24, 144, 255, 0.12);
  transform: translateY(-2px);
}
.meet-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.meet-name {
  flex: 1;
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  line-height: 1.4;
}
.meet-priority {
  flex: 0 0 auto;
  font-size: 12px;
  font-weight: 700;
  border-radius: 6px;
  padding: 2px 8px;
  color: #fff;
}
.meet-priority.p5 { background: #dc2626; }
.meet-priority.p4 { background: #ea580c; }
.meet-priority.p3 { background: #d97706; }
.meet-priority.p-low { background: #94a3b8; }

.meet-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
.meet-time {
  font-size: 12.5px;
  color: var(--text-dim);
}
.meet-fixed {
  font-size: 11px;
  font-weight: 600;
  color: var(--green);
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 10px;
  padding: 1px 8px;
}
.meet-fixed.no {
  color: #b45309;
  background: #fef3c7;
  border-color: #fde68a;
}
.meet-stars {
  font-size: 13px;
  color: var(--gold);
  letter-spacing: 1px;
  margin-bottom: 6px;
}
.meet-remind {
  font-size: 12px;
  color: var(--blue);
  margin-bottom: 6px;
}
.meet-kws {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.meet-kws .stock-tag {
  font-size: 11px;
  margin: 0;
}
</style>
