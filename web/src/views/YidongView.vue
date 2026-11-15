<script setup>
import { ref, computed, onMounted } from 'vue';
import { fetchYidong, fetchYidongDates } from '../api.js';

// 竞价异动页：开盘啦"板块竞价异动"（scripts/fetch_yidong.py），已拉取的日期缓存在 data/yidong/
const dates = ref([]);
const hasCred = ref(true);
const date = ref(''); // '' = 实时
const data = ref(null);
const loading = ref(false);
const error = ref('');
const group = ref('new'); // new | continued | other

const GROUPS = [
  { key: 'new', label: '今日新增', hint: '当日新增的竞价异动板块（新线索）' },
  { key: 'continued', label: '昨日延续', hint: '昨日爆发、今日竞价仍延续异动' },
  { key: 'other', label: '其他异动', hint: '其他异动板块' },
];

onMounted(async () => {
  await loadDates();
  load('');
});

async function loadDates() {
  try {
    const r = await fetchYidongDates();
    dates.value = r.dates || [];
    hasCred.value = r.has_credentials;
  } catch { /* 日期列表失败不影响主流程 */ }
}

async function load(d, refresh = false) {
  date.value = d;
  loading.value = true;
  error.value = '';
  try {
    data.value = await fetchYidong(d, refresh);
    hasCred.value = data.value.has_credentials ?? hasCred.value;
    if (data.value.saved) loadDates(); // 新落盘，刷新缓存日期
  } catch (e) {
    error.value = e.message;
    data.value = null;
  } finally {
    loading.value = false;
  }
}

const list = computed(() => (data.value ? data.value[group.value] || [] : []));
const counts = computed(() => ({
  new: data.value?.new?.length || 0,
  continued: data.value?.continued?.length || 0,
  other: data.value?.other?.length || 0,
}));
const total = computed(() => counts.value.new + counts.value.continued + counts.value.other);

// 金额（元）→ 亿/万
function fmtMoney(v) {
  const n = Number(v);
  if (v == null || v === '' || !isFinite(n)) return v ?? '-';
  const a = Math.abs(n);
  if (a >= 1e8) return (n / 1e8).toFixed(2) + ' 亿';
  if (a >= 1e4) return (n / 1e4).toFixed(0) + ' 万';
  return n.toFixed(0);
}
function netClass(v) {
  const n = Number(v);
  if (!isFinite(n) || n === 0) return '';
  return n > 0 ? 'up' : 'down';
}
const fmtVal = (v) => (v == null || v === '' ? '-' : v);
</script>

<template>
  <div>
    <div class="panel">
      <h2>
        竞价异动
        <span class="yd-sub">开盘啦板块竞价异动 · 已拉取的日期缓存在 data/yidong/，不重复请求</span>
      </h2>

      <!-- 无凭证提示 -->
      <div v-if="!hasCred" class="yd-warn">
        ⚠ 后端未检测到开盘啦凭证：接口在无凭证时只返回空列表。请在启动 web 服务的 shell 中设置环境变量后重启：
        <code>export KPL_USER_ID=你的ID KPL_TOKEN=你的Token</code>（凭证只走环境变量，不写入代码或仓库）。
        已缓存的历史日期仍可正常查看。
      </div>

      <!-- 日期切换：实时 + 已缓存日期 -->
      <div class="date-tabs">
        <button class="date-tab" :class="{ active: date === '' }" @click="load('')">实时（当前交易日）</button>
        <button
          v-for="d in dates"
          :key="d"
          class="date-tab"
          :class="{ active: date === d }"
          @click="load(d)"
        >
          {{ d.slice(5) }}
        </button>
        <button class="yd-refresh" :disabled="loading" @click="load(date, true)">⟳ 强制重拉</button>
      </div>

      <div v-if="loading" class="loading">加载中…</div>
      <div v-else-if="error" class="error">⚠ {{ error }}</div>
      <template v-else-if="data">
        <div class="stat-grid" style="margin-bottom: 14px">
          <div class="stat-card blue">
            <div class="stat-label">交易日</div>
            <div class="stat-value" style="font-size: 18px">{{ data.date }}</div>
            <div class="stat-sub">{{ data.from_cache ? '本地缓存' : '在线拉取' }}{{ data.saved ? ' · 已落盘' : '' }}</div>
          </div>
          <div class="stat-card red">
            <div class="stat-label">今日新增</div>
            <div class="stat-value">{{ counts.new }}</div>
          </div>
          <div class="stat-card gold">
            <div class="stat-label">昨日延续</div>
            <div class="stat-value">{{ counts.continued }}</div>
          </div>
          <div class="stat-card green">
            <div class="stat-label">其他异动</div>
            <div class="stat-value">{{ counts.other }}</div>
          </div>
        </div>

        <div v-if="!total" class="empty">
          当日三个列表均为空：可能是非交易日 / 竞价阶段未触发 / 账户无权限{{ hasCred ? '' : ' / 未配置凭证' }}。
          实时数据仅在交易日 9:15–9:25 竞价阶段有意义，建议 9:25 后拉一次固定快照。
        </div>

        <template v-else>
          <div class="stock-tabs">
            <button
              v-for="g in GROUPS"
              :key="g.key"
              :class="{ active: group === g.key }"
              :title="g.hint"
              @click="group = g.key"
            >
              {{ g.label }}（{{ counts[g.key] }}）
            </button>
          </div>
          <div style="overflow-x: auto">
            <table class="stock-table">
              <thead>
                <tr>
                  <th class="left">板块代码</th>
                  <th class="left">板块名称</th>
                  <th>竞价爆量</th>
                  <th>异动金额</th>
                  <th>竞价强度</th>
                  <th>主力净额</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(it, i) in list" :key="(it.code || '') + i">
                  <td class="left">{{ fmtVal(it.code) }}</td>
                  <td class="left"><b>{{ fmtVal(it.name) }}</b></td>
                  <td>{{ fmtVal(it.burst) }}</td>
                  <td>{{ fmtMoney(it.amount) }}</td>
                  <td>{{ fmtVal(it.strength) }}</td>
                  <td :class="netClass(it.net_inflow)">{{ fmtMoney(it.net_inflow) }}</td>
                </tr>
              </tbody>
            </table>
            <div v-if="!list.length" class="empty">该分组暂无数据</div>
          </div>
          <div class="yd-foot">
            ⓘ 字段含义按接口文档约定（[代码, 名称, 爆量指标, 异动金额, 强度, 主力净额]），为应用侧接口，字段顺序可能调整；
            原始数组完整保存在 data/yidong/ 的 JSON（raw 字段）中可回查。
          </div>
        </template>
      </template>
    </div>
  </div>
</template>

<style scoped>
.yd-sub {
  font-size: 12px;
  color: var(--text-dim);
  font-weight: 400;
  margin-left: 10px;
}
.yd-warn {
  font-size: 12.5px;
  line-height: 1.7;
  color: #7a5b12;
  background: #fff8e6;
  border: 1px solid #f0d9a6;
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 14px;
}
.yd-warn code {
  background: #fff;
  border: 1px solid #f0d9a6;
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 12px;
}
.yd-refresh {
  font-size: 12px;
  color: var(--blue);
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 5px 14px;
  cursor: pointer;
}
.yd-refresh:hover:not(:disabled) {
  border-color: var(--blue);
  background: #e8f3ff;
}
.yd-refresh:disabled {
  opacity: 0.5;
  cursor: wait;
}
.yd-foot {
  margin-top: 12px;
  font-size: 11.5px;
  color: var(--text-dim);
  line-height: 1.7;
}
</style>
