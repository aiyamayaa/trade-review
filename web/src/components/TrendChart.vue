<script>
export default {
  name: 'TrendChart',
  props: {
    // series: [{ name, points: [{x, y}], color }]
    series: { type: Array, default: () => [] },
    unit: { type: String, default: '' }, // 数值单位，如 '亿'、'%'
    digits: { type: Number, default: 2 },
    showZeroLine: { type: Boolean, default: false },
  },
  data() {
    return {
      tip: null,
      visible: {}, // 每条线是否可见（缺省可见）
      w: 800, // 实际渲染宽度（响应式）
      uid: Math.random().toString(36).slice(2, 7),
    };
  },
  computed: {
    H() { return 300; },
    padL() { return 60; },
    padR() { return 20; },
    pb() { return 42; },
    topPad() { return 20; },
    // 可见的 series（保持原顺序与索引）
    visibleSeries() {
      return this.series
        .map((s, i) => ({ s, i }))
        .filter((x) => this.visible[x.i] !== false);
    },
    allPts() {
      return this.visibleSeries.flatMap((x) =>
        x.s.points.filter((p) => p.y != null)
      );
    },
    yMin() {
      if (!this.allPts.length) return 0;
      const vals = this.allPts.map((p) => p.y);
      let mn = Math.min(...vals), mx = Math.max(...vals);
      if (mn === mx) { mn -= 1; mx += 1; }
      if (this.showZeroLine) { if (mx < 0) mx = 0; if (mn > 0) mn = 0; }
      const pad = (mx - mn) * 0.1;
      return mn - pad;
    },
    yMax() {
      if (!this.allPts.length) return 10;
      const vals = this.allPts.map((p) => p.y);
      let mn = Math.min(...vals), mx = Math.max(...vals);
      if (mn === mx) { mn -= 1; mx += 1; }
      if (this.showZeroLine) { if (mx < 0) mx = 0; if (mn > 0) mn = 0; }
      const pad = (mx - mn) * 0.1;
      return mx + pad;
    },
    zeroY() { return this.py(0); },
    // x 轴刻度基准：第一个可见 series 的点
    xPts() {
      const first = this.visibleSeries[0];
      return first ? first.s.points : [];
    },
    n() { return Math.max(this.xPts.length, 1); },
    yTicks() {
      const cnt = 5;
      const step = (this.yMax - this.yMin) / cnt || 1;
      const ticks = [];
      for (let i = 0; i <= cnt; i++) {
        const v = this.yMin + step * i;
        ticks.push({ y: this.py(v), label: this.fmtTick(v) });
      }
      return ticks;
    },
    xLabels() {
      const gap = Math.max(1, Math.ceil(this.n / 10));
      return this.xPts
        .map((p, i) => ({ x: this.cx(i), label: p.x, i }))
        .filter((t) => t.i % gap === 0);
    },
  },
  methods: {
    py(v) {
      const range = (this.yMax - this.yMin) || 1;
      return this.pb + (1 - (v - this.yMin) / range) * (this.H - this.pb - this.topPad);
    },
    cx(i) {
      const w = this.w - this.padL - this.padR;
      if (this.n <= 1) return this.padL + w / 2;
      return this.padL + (i / (this.n - 1)) * w;
    },
    linePath(points) {
      const valid = [];
      points.forEach((p, i) => { if (p.y != null) valid.push([i, p.y]); });
      if (valid.length < 2) return '';
      return valid
        .map(([i, y], k) => `${k === 0 ? 'M' : 'L'} ${this.cx(i)} ${this.py(y)}`)
        .join(' ');
    },
    fmtTick(v) {
      if (Math.abs(v) >= 100) return v.toFixed(0);
      if (Math.abs(v) >= 10) return v.toFixed(1);
      return v.toFixed(2);
    },
    fmtVal(v) {
      if (v == null) return '-';
      const n = Number(v);
      const sign = n > 0 ? '+' : '';
      return sign + n.toFixed(this.digits) + (this.unit ? ' ' + this.unit : '');
    },
    isVisible(i) {
      return this.visible[i] !== false;
    },
    toggleVisible(i) {
      const next = { ...this.visible, [i]: !this.isVisible(i) };
      const visibleCount = this.series.filter((_, j) => next[j] !== false).length;
      if (visibleCount === 0) return; // 至少保留一条
      this.visible = next;
    },
    selectAll() { this.visible = {}; },
    clearAll() {
      const next = {};
      this.series.forEach((_, i) => { next[i] = false; });
      this.visible = next;
    },
    onHover(si, pi, s) {
      const p = s.points[pi];
      this.tip = { si, pi, x: p.x, y: p.y, name: s.name, color: s.color };
    },
    onLeave() { this.tip = null; },
    tipX() {
      if (!this.tip) return 0;
      const x = this.cx(this.tip.pi);
      // clamp 避免 tooltip 超出左右边界被裁剪
      return Math.max(92, Math.min(this.w - 92, x));
    },
    tipY() {
      if (!this.tip) return 0;
      const y = this.py(this.tip.y) - 40;
      // clamp 避免 tooltip 超出上下边界
      return Math.max(38, Math.min(this.H - 4, y));
    },
    observe() {
      if (typeof ResizeObserver === 'undefined' || !this.$refs.box) return;
      this.ro = new ResizeObserver((entries) => {
        const w = entries[0] && entries[0].contentRect.width;
        if (w && w > 50) this.w = w;
      });
      this.ro.observe(this.$refs.box);
    },
  },
  mounted() { this.observe(); },
  beforeUnmount() { if (this.ro) this.ro.disconnect(); },
};
</script>

<template>
  <div class="trend">
    <!-- 图例（可点击切换） -->
    <div class="trend-legend">
      <div v-if="series.length > 1" class="tl-actions">
        <button class="tl-btn" @click="selectAll">全选</button>
        <button class="tl-btn" @click="clearAll">清空</button>
      </div>
      <span
        v-for="(s, i) in series"
        :key="'lg' + i"
        class="tl-item"
        :class="{ off: !isVisible(i) }"
        @click="toggleVisible(i)"
      >
        <i class="tl-swatch" :style="{ background: isVisible(i) ? s.color : '#c6ccd6' }"></i>
        {{ s.name }}
      </span>
    </div>

    <div ref="box" class="trend-box">
      <svg :width="w" :height="H">
        <!-- 零线 -->
        <line v-if="showZeroLine" :x1="padL" :y1="zeroY" :x2="w - padR" :y2="zeroY"
              stroke="var(--border)" stroke-dasharray="4,4"/>
        <!-- Y轴网格 + 刻度 -->
        <g v-for="(tick, i) in yTicks" :key="'g' + i">
          <line :x1="padL" :y1="tick.y" :x2="w - padR" :y2="tick.y"
                stroke="var(--border)" stroke-opacity="0.5"/>
          <text :x="padL - 8" :y="tick.y + 4" text-anchor="end"
                font-size="11" fill="var(--text-dim)">{{ tick.label }}</text>
        </g>
        <!-- X轴标签 -->
        <g v-for="(t, i) in xLabels" :key="'xl' + i">
          <text :x="t.x" :y="H - pb + 18" text-anchor="middle"
                font-size="11" fill="var(--text-dim)">{{ t.label }}</text>
        </g>
        <!-- 折线 -->
        <template v-for="(x, si) in visibleSeries" :key="'s' + x.i">
          <path :d="linePath(x.s.points)" :stroke="x.s.color" stroke-width="2" fill="none"/>
          <template v-for="(pt, pi) in x.s.points" :key="x.i + '-' + pi">
            <circle v-if="pt.y != null"
                    :cx="cx(pi)" :cy="py(pt.y)" r="3.2"
                    :fill="x.s.color" stroke="#fff" stroke-width="1"
                    @mouseenter="onHover(x.i, pi, x.s)"
                    @mouseleave="onLeave"/>
          </template>
        </template>
        <!-- hover tooltip -->
        <g v-if="tip" :transform="'translate(' + tipX() + ',' + tipY() + ')'" pointer-events="none">
          <rect x="-90" y="-38" width="180" height="34" rx="6" fill="rgba(28,32,45,0.92)"/>
          <text x="0" y="-20" text-anchor="middle" font-size="12" fill="#fff" font-weight="600">
            {{ tip.x }} · {{ tip.name }}
          </text>
          <text x="0" y="-5" text-anchor="middle" font-size="12" :fill="tip.color">
            {{ fmtVal(tip.y) }}
          </text>
        </g>
      </svg>
    </div>
  </div>
</template>

<style scoped>
.trend { width: 100%; }
.trend-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  margin-bottom: 10px;
}
.tl-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text);
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 5px;
  transition: background 0.12s, opacity 0.12s;
  user-select: none;
}
.tl-item:hover {
  background: var(--card-2);
}
.tl-item.off {
  opacity: 0.45;
  text-decoration: line-through;
}
.tl-actions {
  display: inline-flex;
  gap: 6px;
  margin-right: 8px;
}
.tl-btn {
  font-size: 12px;
  color: var(--blue);
  cursor: pointer;
  padding: 2px 10px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: #fff;
  transition: all 0.12s;
}
.tl-btn:hover {
  background: #e8f3ff;
  border-color: var(--blue);
}
.tl-swatch {
  display: inline-block;
  width: 14px;
  height: 4px;
  border-radius: 2px;
}
.trend-box {
  width: 100%;
  min-width: 480px;
  overflow-x: auto;
}
.trend-box svg {
  display: block;
}
</style>
