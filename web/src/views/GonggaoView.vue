<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { fetchGonggao, fetchGonggaoMeta, syncGonggao } from '../api.js';

// 公告页：东方财富公告大全（scripts/fetch_gonggao.py），按月 CSV 存储在 data/gonggao/
// 查询读本地文件（不请求网络）；"实时刷新"在线抓今天并落盘；"补历史"在线抓指定日期范围并落盘。

const today = () => new Date().toLocaleDateString('sv-SE'); // YYYY-MM-DD（本地时区）
const daysAgo = (n) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toLocaleDateString('sv-SE');
};

// 筛选条件
const from = ref(today());
const to = ref(today());
const company = ref('');
const cat = ref('');
const q = ref('');
const size = ref(50);
const page = ref(1);

const meta = ref(null);
const result = ref({ total: 0, items: [], top_cats: [] });
const loading = ref(false);
const error = ref('');

// 在线抓取
const syncing = ref(false);
const syncMsg = ref('');
const histFrom = ref(daysAgo(6));
const histTo = ref(today());

// 实时刷新（在线抓今天 → 重新查询）
const autoRefresh = ref(false);
const interval = ref(60);
let timer = null;

onMounted(async () => {
  await loadMeta();
  // 本地无今天数据时，默认展示库内最新日期，避免打开页面一片空白
  if (meta.value?.max_date && meta.value.max_date < from.value) {
    from.value = to.value = meta.value.max_date;
  }
  search();
});
onBeforeUnmount(stopTimer);

async function loadMeta() {
  try {
    meta.value = await fetchGonggaoMeta();
  } catch { /* 概览失败不影响主流程 */ }
}

async function search(resetPage = true) {
  if (resetPage) page.value = 1;
  loading.value = true;
  error.value = '';
  try {
    result.value = await fetchGonggao({
      from: from.value,
      to: to.value,
      company: company.value.trim(),
      cat: cat.value.trim(),
      q: q.value.trim(),
      page: page.value,
      size: size.value,
    });
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

// 在线抓取（body 为空=今天）
async function doSync(body, label) {
  if (syncing.value) return;
  syncing.value = true;
  syncMsg.value = `${label}抓取中…（全市场单日约 1500 条，需十几秒；补历史时每天约十几秒）`;
  try {
    const r = await syncGonggao(body);
    syncMsg.value = `${label}完成：拉取 ${r.fetched} 条，新增 ${r.added} 条`;
    await loadMeta();
    await search(false);
  } catch (e) {
    syncMsg.value = `❌ ${label}失败：${e.message}`;
  } finally {
    syncing.value = false;
  }
}
const refreshNow = () => doSync({}, '实时刷新');
const syncHistory = () => doSync({ from: histFrom.value, to: histTo.value }, `补历史 ${histFrom.value}~${histTo.value} `);

function toggleAuto() {
  if (autoRefresh.value) return stopAuto();
  autoRefresh.value = true;
  // 实时模式：筛选范围切到今天
  from.value = to.value = today();
  refreshNow();
  timer = setInterval(refreshNow, Math.max(30, interval.value) * 1000);
}
function stopAuto() {
  autoRefresh.value = false;
  stopTimer();
}
function stopTimer() {
  if (timer) { clearInterval(timer); timer = null; }
}

// 快捷时间范围
function setRange(n) {
  from.value = daysAgo(n);
  to.value = today();
  search();
}
function pickCat(name) {
  cat.value = cat.value === name ? '' : name;
  search();
}
function reset() {
  from.value = to.value = today();
  company.value = cat.value = q.value = '';
  search();
}

const totalPages = computed(() => Math.max(1, Math.ceil(result.value.total / size.value)));
function go(p) {
  if (p < 1 || p > totalPages.value) return;
  page.value = p;
  search(false);
}

const fmtTime = (t) => (t ? t.slice(5, 16) : ''); // MM-DD HH:MM
const catTags = (s) => (s || '').split(';').filter(Boolean);
</script>

<template>
  <div>
    <div class="panel">
      <h2>
        上市公司公告
        <span class="gg-sub">
          东方财富 · 按月存储 data/gonggao/*.csv
          <template v-if="meta">· 本地共 {{ meta.total }} 条（{{ meta.min_date }} ~ {{ meta.max_date }}）</template>
        </span>
      </h2>

      <!-- 筛选 -->
      <div class="gg-filter">
        <label class="gg-field">时间
          <input type="date" v-model="from" class="gg-input" />
          ~
          <input type="date" v-model="to" class="gg-input" />
        </label>
        <label class="gg-field">公司
          <input v-model="company" class="gg-input" placeholder="代码或名称，如 600519 / 茅台" @keyup.enter="search()" />
        </label>
        <label class="gg-field">分类
          <input v-model="cat" class="gg-input" placeholder="如 回购预案" @keyup.enter="search()" />
        </label>
        <label class="gg-field">标题
          <input v-model="q" class="gg-input" placeholder="关键词" @keyup.enter="search()" />
        </label>
        <button class="gg-btn primary" :disabled="loading" @click="search()">查询</button>
        <button class="gg-btn" @click="reset">重置</button>
      </div>
      <div class="gg-quick">
        快捷：
        <button class="gg-chip" @click="setRange(0)">今天</button>
        <button class="gg-chip" @click="setRange(1)">近2天</button>
        <button class="gg-chip" @click="setRange(6)">近7天</button>
        <button class="gg-chip" @click="setRange(29)">近30天</button>
        <button class="gg-chip" v-if="meta?.min_date" @click="from = meta.min_date; to = meta.max_date; search()">全部本地数据</button>
      </div>

      <!-- 数据获取：实时刷新 / 补历史 -->
      <div class="gg-sync">
        <button class="gg-btn primary" :disabled="syncing" @click="refreshNow">⟳ 实时刷新（抓今天）</button>
        <button class="gg-btn" :class="{ on: autoRefresh }" @click="toggleAuto">
          {{ autoRefresh ? '● 自动刷新中' : '○ 自动刷新' }}
        </button>
        <label class="gg-field" v-if="!autoRefresh">间隔
          <select v-model.number="interval" class="sort-select">
            <option :value="30">30s</option>
            <option :value="60">60s</option>
            <option :value="180">3分钟</option>
          </select>
        </label>
        <span class="gg-sep">|</span>
        <label class="gg-field">补历史
          <input type="date" v-model="histFrom" class="gg-input" />
          ~
          <input type="date" v-model="histTo" class="gg-input" />
        </label>
        <button class="gg-btn" :disabled="syncing" @click="syncHistory">⬇ 抓取并存储</button>
      </div>
      <div v-if="syncMsg" class="gg-msg" :class="{ bad: syncMsg.startsWith('❌') }">{{ syncMsg }}</div>
      <div class="gg-tip">
        ⓘ 「公告时间」为实际披露时间。东方财富按交易日归档，收盘后披露的公告归入下一交易日，因此抓取某天会同时抓取次日以保证当天完整；
        本地最早一天的数据可能不完整（缺其更早一天归档的部分）。
      </div>

      <!-- 分类快速筛选 -->
      <div class="gg-cats" v-if="result.top_cats.length">
        <span class="gg-cats-label">当前结果分类 TOP</span>
        <button
          v-for="c in result.top_cats"
          :key="c.name"
          class="gg-cat"
          :class="{ active: cat === c.name }"
          @click="pickCat(c.name)"
        >
          {{ c.name }} <i>{{ c.count }}</i>
        </button>
      </div>

      <div v-if="loading && !result.items.length" class="loading">加载中…</div>
      <div v-else-if="error" class="error">⚠ {{ error }}</div>
      <template v-else>
        <div class="gg-total">
          共 <b>{{ result.total }}</b> 条
          <template v-if="result.total">，第 {{ page }} / {{ totalPages }} 页</template>
        </div>

        <div v-if="!result.total" class="empty">
          本地没有符合条件的公告。可点「实时刷新」抓今天，或用「补历史」抓取该日期范围并存储（之后查询直接读本地文件）。
        </div>
        <div v-else style="overflow-x: auto">
          <table class="stock-table gg-table">
            <thead>
              <tr>
                <th class="left" style="width: 96px">公告时间</th>
                <th class="left" style="width: 150px">公司</th>
                <th class="left" style="width: 170px">分类</th>
                <th class="left">公告内容</th>
                <th style="width: 70px">原文</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="it in result.items" :key="it.art_code">
                <td class="left gg-time">{{ fmtTime(it.time) }}</td>
                <td class="left">
                  <b>{{ it.names }}</b>
                  <div class="gg-code">{{ it.codes }}</div>
                </td>
                <td class="left">
                  <span v-for="c in catTags(it.cats)" :key="c" class="gg-tag" @click="pickCat(c)">{{ c }}</span>
                </td>
                <td class="left gg-title">
                  <a :href="it.url" target="_blank" rel="noopener">{{ it.title }}</a>
                </td>
                <td><a :href="it.pdf" target="_blank" rel="noopener">PDF</a></td>
              </tr>
            </tbody>
          </table>

          <div class="gg-pager">
            <button class="gg-btn" :disabled="page <= 1" @click="go(1)">首页</button>
            <button class="gg-btn" :disabled="page <= 1" @click="go(page - 1)">上一页</button>
            <span>{{ page }} / {{ totalPages }}</span>
            <button class="gg-btn" :disabled="page >= totalPages" @click="go(page + 1)">下一页</button>
            <button class="gg-btn" :disabled="page >= totalPages" @click="go(totalPages)">末页</button>
            <select v-model.number="size" class="sort-select" @change="search()">
              <option :value="20">20条/页</option>
              <option :value="50">50条/页</option>
              <option :value="100">100条/页</option>
              <option :value="200">200条/页</option>
            </select>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.gg-sub {
  font-size: 12px;
  color: var(--text-dim);
  font-weight: 400;
  margin-left: 10px;
}
.gg-filter,
.gg-sync {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 8px 10px;
  background: var(--card-2);
  border-radius: 8px;
  margin-bottom: 8px;
}
.gg-field {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-dim);
}
.gg-input {
  padding: 6px 8px;
  font-size: 12.5px;
  border: 1px solid var(--border);
  border-radius: 6px;
  outline: none;
  background: #fff;
  min-width: 110px;
}
.gg-input:focus {
  border-color: var(--blue);
}
.gg-sep {
  color: var(--border);
}
.gg-btn {
  font-size: 12px;
  color: var(--blue);
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 6px 14px;
  cursor: pointer;
}
.gg-btn:hover:not(:disabled) {
  border-color: var(--blue);
  background: #e8f3ff;
}
.gg-btn.primary {
  color: #fff;
  background: var(--blue);
  border-color: var(--blue);
}
.gg-btn.primary:hover:not(:disabled) {
  background: #1677d9;
}
.gg-btn.on {
  color: #dc2626;
  border-color: #dc2626;
}
.gg-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.gg-quick {
  font-size: 12px;
  color: var(--text-dim);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.gg-chip {
  font-size: 11.5px;
  color: var(--text);
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 2px 10px;
  cursor: pointer;
}
.gg-chip:hover {
  border-color: var(--blue);
  color: var(--blue);
}
.gg-msg {
  font-size: 12.5px;
  color: #0f766e;
  background: #f0fdfa;
  border: 1px solid #99f6e4;
  border-radius: 6px;
  padding: 6px 12px;
  margin-bottom: 8px;
}
.gg-msg.bad {
  color: #b91c1c;
  background: #fef2f2;
  border-color: #fecaca;
}
.gg-tip {
  font-size: 11.5px;
  color: var(--text-dim);
  line-height: 1.7;
  margin-bottom: 4px;
}
.gg-cats {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin: 10px 0;
}
.gg-cats-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-dim);
  margin-right: 4px;
}
.gg-cat {
  font-size: 11.5px;
  color: #3a6ea5;
  background: #e0efff;
  border: 1px solid #bcd9f7;
  border-radius: 12px;
  padding: 2px 10px;
  cursor: pointer;
}
.gg-cat i {
  font-style: normal;
  opacity: 0.7;
  margin-left: 2px;
}
.gg-cat:hover {
  background: #cfe5ff;
}
.gg-cat.active {
  color: #fff;
  background: var(--blue);
  border-color: var(--blue);
}
.gg-total {
  font-size: 12.5px;
  color: var(--text-dim);
  margin: 8px 0;
}
.gg-table td {
  white-space: normal;
  vertical-align: top;
  line-height: 1.55;
}
.gg-time {
  color: var(--text-dim);
  font-variant-numeric: tabular-nums;
  white-space: nowrap !important;
}
.gg-code {
  font-size: 11px;
  color: var(--text-dim);
  font-variant-numeric: tabular-nums;
}
.gg-tag {
  display: inline-block;
  font-size: 11px;
  color: #3a6ea5;
  background: #eef6ff;
  border: 1px solid #bcd9f7;
  border-radius: 4px;
  padding: 0 6px;
  margin: 1px 4px 1px 0;
  cursor: pointer;
}
.gg-tag:hover {
  background: #d4e9ff;
}
.gg-title a {
  color: var(--text);
  text-decoration: none;
}
.gg-title a:hover {
  color: var(--blue);
  text-decoration: underline;
}
.gg-pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-top: 14px;
  font-size: 12.5px;
  color: var(--text-dim);
}
</style>
