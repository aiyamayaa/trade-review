<script setup>
import { ref, onMounted } from 'vue';
import { fetchLinks } from '../api.js';

// 链接导航页：配置在 data/config/links.json，修改后刷新页面即生效
const groups = ref([]);
const error = ref('');
const loading = ref(false);

onMounted(load);

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const r = await fetchLinks();
    groups.value = r.groups || [];
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

// 从 URL 提取域名展示（如 data.10jqka.com.cn）
function hostOf(url) {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

// 链接卡片图标：按域名给个可辨识 emoji（可按需扩充）
function iconOf(url) {
  const h = hostOf(url);
  if (h.includes('10jqka')) return '📈';
  if (h.includes('eastmoney')) return '🐂';
  if (h.includes('cninfo')) return '📜';
  if (h.includes('cls.cn')) return '⚡';
  if (h.includes('sina')) return '🅢';
  if (h.includes('xueqiu')) return '❄️';
  return '🔗';
}

const total = () => groups.value.reduce((n, g) => n + (g.items || []).length, 0);
</script>

<template>
  <div>
    <div class="panel">
      <h2>链接导航
        <span class="lk-sub" v-if="!loading && !error">{{ total() }} 个常用入口 · 配置：data/config/links.json（修改即生效）</span>
      </h2>
      <div v-if="loading" class="loading">加载中…</div>
      <div v-else-if="error" class="error">⚠ {{ error }}</div>
      <div v-else-if="!groups.length" class="empty">
        暂无链接，请在 data/config/links.json 中添加
      </div>

      <div v-for="g in groups" :key="g.group" class="lk-group">
        <div class="lk-group-title">{{ g.group }}</div>
        <div class="lk-grid">
          <a
            v-for="l in g.items"
            :key="l.url"
            :href="l.url"
            target="_blank"
            rel="noopener"
            class="lk-card"
            :title="l.url"
          >
            <div class="lk-card-head">
              <span class="lk-icon">{{ iconOf(l.url) }}</span>
              <span class="lk-name">{{ l.name }}</span>
              <span class="lk-arrow">↗</span>
            </div>
            <div v-if="l.desc" class="lk-desc">{{ l.desc }}</div>
            <div class="lk-host">{{ hostOf(l.url) }}</div>
          </a>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lk-sub {
  font-size: 12px;
  color: var(--text-dim);
  font-weight: 400;
  margin-left: 10px;
}
.lk-group { margin-bottom: 18px; }
.lk-group-title {
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.lk-group-title::before {
  content: '';
  width: 3px;
  height: 14px;
  background: var(--blue);
  border-radius: 2px;
}
.lk-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}
.lk-card {
  display: block;
  padding: 14px 16px;
  background: var(--card-2);
  border: 1px solid var(--border);
  border-radius: 12px;
  text-decoration: none;
  color: var(--text);
  transition: all 0.15s;
}
.lk-card:hover {
  border-color: var(--blue);
  box-shadow: 0 4px 14px rgba(24, 144, 255, 0.15);
  transform: translateY(-2px);
}
.lk-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.lk-icon { font-size: 18px; }
.lk-name { font-size: 14px; font-weight: 700; flex: 1; }
.lk-arrow {
  font-size: 13px;
  color: var(--text-dim);
  opacity: 0;
  transition: opacity 0.15s;
}
.lk-card:hover .lk-arrow { opacity: 1; color: var(--blue); }
.lk-desc {
  font-size: 12px;
  color: var(--text-dim);
  margin-top: 6px;
  line-height: 1.6;
}
.lk-host {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 8px;
  font-family: 'SF Mono', Menlo, monospace;
}
</style>
