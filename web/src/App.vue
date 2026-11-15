<script setup>
import { ref } from 'vue';
import EmotionView from './views/EmotionView.vue';
import EmotionSummaryView from './views/EmotionSummaryView.vue';
import SectorView from './views/SectorView.vue';
import TiCaiView from './views/TiCaiView.vue';
import TiCaiSummaryView from './views/TiCaiSummaryView.vue';
import TiCaiTrendView from './views/TiCaiTrendView.vue';
import ChatView from './views/ChatView.vue';
import ConceptView from './views/ConceptView.vue';
import IndustryConceptView from './views/IndustryConceptView.vue';
import IndustryView from './views/IndustryView.vue';
import StockInfoView from './views/StockInfoView.vue';
import LimitUpTimelineView from './views/LimitUpTimelineView.vue';
import TickView from './views/TickView.vue';
import LinksView from './views/LinksView.vue';
import MeetingView from './views/MeetingView.vue';
import TelegraphView from './views/TelegraphView.vue';
import ZtPoolView from './views/ZtPoolView.vue';
import YidongView from './views/YidongView.vue';
import LhbRealtimeView from './views/LhbRealtimeView.vue';
import GonggaoView from './views/GonggaoView.vue';

const tab = ref('telegraph');
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="brand">数据看板</div>
      <nav class="tabs">
        <button :class="{ active: tab === 'telegraph' }" @click="tab = 'telegraph'">
          电报
        </button>
        <button :class="{ active: tab === 'emotion' }" @click="tab = 'emotion'">
          市场情绪
        </button>
        <button :class="{ active: tab === 'summary' }" @click="tab = 'summary'">
          情绪汇总
        </button>
        <button :class="{ active: tab === 'sector' }" @click="tab = 'sector'">
          板块分析
        </button>
        <button :class="{ active: tab === 'ticai' }" @click="tab = 'ticai'">
          题材板块
        </button>
        <button :class="{ active: tab === 'ticai-trend' }" @click="tab = 'ticai-trend'">
          题材趋势
        </button>
        <button :class="{ active: tab === 'industry-concept' }" @click="tab = 'industry-concept'">
概念
        </button>
        <button :class="{ active: tab === 'industry' }" @click="tab = 'industry'">
行业
        </button>
        <button :class="{ active: tab === 'stock-info' }" @click="tab = 'stock-info'">
          个股信息
        </button>
        <button :class="{ active: tab === 'limit-up-timeline' }" @click="tab = 'limit-up-timeline'">
          涨停时间轴
        </button>
        <button :class="{ active: tab === 'zt-pool' }" @click="tab = 'zt-pool'">
          涨停池
        </button>
        <button :class="{ active: tab === 'yidong' }" @click="tab = 'yidong'">
          竞价异动
        </button>
        <button :class="{ active: tab === 'lhb-realtime' }" @click="tab = 'lhb-realtime'">
          实时龙虎榜
        </button>
        <button :class="{ active: tab === 'gonggao' }" @click="tab = 'gonggao'">
          公告
        </button>
        <button :class="{ active: tab === 'tick' }" @click="tab = 'tick'">
          分时数据
        </button>
        <button :class="{ active: tab === 'links' }" @click="tab = 'links'">
          链接导航
        </button>
        <button :class="{ active: tab === 'meeting' }" @click="tab = 'meeting'">
          会议日历
        </button>
        <button :class="{ active: tab === 'concept' }" @click="tab = 'concept'">
          概念板块
        </button>
        <button :class="{ active: tab === 'chat' }" @click="tab = 'chat'">
          AI 对话
        </button>
        <button :class="{ active: tab === 'ticai-summary' }" @click="tab = 'ticai-summary'">
          题材汇总
        </button>
      </nav>
    </header>
    <main class="content">
      <EmotionView v-show="tab === 'emotion'" />
      <EmotionSummaryView v-show="tab === 'summary'" />
      <SectorView v-show="tab === 'sector'" />
      <TiCaiView v-show="tab === 'ticai'" />
      <TiCaiSummaryView v-if="tab === 'ticai-summary'" />
      <TiCaiTrendView v-if="tab === 'ticai-trend'" />
      <ChatView v-if="tab === 'chat'" />
      <ConceptView v-if="tab === 'concept'" />
      <IndustryConceptView v-if="tab === 'industry-concept'" />
      <IndustryView v-if="tab === 'industry'" />
      <StockInfoView v-if="tab === 'stock-info'" />
      <LimitUpTimelineView v-if="tab === 'limit-up-timeline'" />
      <ZtPoolView v-if="tab === 'zt-pool'" />
      <YidongView v-if="tab === 'yidong'" />
      <LhbRealtimeView v-if="tab === 'lhb-realtime'" />
      <GonggaoView v-if="tab === 'gonggao'" />
      <TickView v-if="tab === 'tick'" />
      <LinksView v-if="tab === 'links'" />
      <MeetingView v-if="tab === 'meeting'" />
      <TelegraphView v-if="tab === 'telegraph'" />
    </main>
  </div>
</template>
