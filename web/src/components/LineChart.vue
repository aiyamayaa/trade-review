<script>
export default {
  name: 'LineChart',
  props: {
    series: { type: Array, default: () => [] }, // [{name, points:[{x,y}], color}]
    showZeroLine: { type: Boolean, default: false },
  },
  data() {
    return {
      tip: null,
      uid: Math.random().toString(36).slice(2, 7),
    };
  },
  computed: {
    W() { return 800; },
    H() { return 280; },
    padL() { return 56; },
    padR() { return 20; },
    pb() { return 40; },
    allPts() {
      return this.series.flatMap((s) => s.points.filter((p) => p.y != null));
    },
    yMin() {
      if (!this.allPts.length) return 0;
      const vals = this.allPts.map((p) => p.y);
      let mn = Math.min(...vals), mx = Math.max(...vals);
      if (mn === mx) { mn -= 1; mx += 1; }
      if (this.showZeroLine) { if (mx < 0) mx = 0; if (mn > 0) mn = 0; }
      const pad = (mx - mn) * 0.08;
      return mn - pad;
    },
    yMax() {
      if (!this.allPts.length) return 10;
      const vals = this.allPts.map((p) => p.y);
      let mn = Math.min(...vals), mx = Math.max(...vals);
      if (mn === mx) { mn -= 1; mx += 1; }
      if (this.showZeroLine) { if (mx < 0) mx = 0; if (mn > 0) mn = 0; }
      const pad = (mx - mn) * 0.08;
      return mx + pad;
    },
    zeroY() { return this.py(0); },
    yTicks() {
      const n = 5;
      const step = (this.yMax - this.yMin) / n || 1;
      const ticks = [];
      for (let i = 0; i <= n; i++) {
        const v = this.yMin + step * i;
        ticks.push({ y: this.py(v), label: this.fmtTick(v) });
      }
      return ticks;
    },
    xLabels() {
      const pts = this.series[0]?.points || [];
      const gap = Math.max(1, Math.ceil(pts.length / 10));
      return pts.filter((_, i) => i % gap === 0).map((p) => ({
        x: this.cx(pts.indexOf(p)),
        label: p.x,
      }));
    },
  },
  methods: {
    py(v) {
      const range = (this.yMax - this.yMin) || 1;
      return this.pb + (1 - (v - this.yMin) / range) * (this.H - this.pb - 20);
    },
    cx(i) {
      const n = Math.max(this.series[0]?.points?.length || 1, 1);
      const w = this.W - this.padL - this.padR;
      return this.padL + (i / (n - 1)) * w;
    },
    cy(v) { return this.py(v); },
    linePath(pts) {
      const valid = pts.filter((p) => p.y != null);
      if (valid.length < 2) return '';
      return valid.map((p, i) =>
        `${i === 0 ? 'M' : 'L'} ${this.cx(pts.indexOf(p))} ${this.cy(p.y)}`
      ).join(' ');
    },
    areaPath(pts) {
      const valid = pts.filter((p) => p.y != null);
      if (valid.length < 2) return '';
      const line = valid.map((p, i) =>
        `${i === 0 ? 'M' : 'L'} ${this.cx(pts.indexOf(p))} ${this.cy(p.y)}`
      ).join(' ');
      const lastX = this.cx(pts.indexOf(valid[valid.length - 1]));
      const firstX = this.cx(pts.indexOf(valid[0]));
      return `${line} L ${lastX} ${this.H - this.pb} L ${firstX} ${this.H - this.pb} Z`;
    },
    fmtTick(v) {
      if (Math.abs(v) >= 100) return v.toFixed(0);
      if (Math.abs(v) >= 1) return v.toFixed(1);
      return v.toFixed(2);
    },
    tipFmt(v) {
      if (Math.abs(v) >= 100) return v.toFixed(0);
      if (Math.abs(v) >= 1) return v.toFixed(2);
      return v.toFixed(3);
    },
    tipX() {
      if (!this.tip) return 0;
      const pts = this.series.flatMap((s) => s.points);
      const idx = pts.findIndex((p) => p.x === this.tip.x);
      if (idx < 0) return 0;
      return this.cx(idx);
    },
    tipY() {
      if (!this.tip) return 0;
      return this.py(this.tip.y) - 44;
    },
    onHover(d) { this.tip = d; },
    onLeave() { this.tip = null; },
  },
};
</script>

<template>
  <div class="lc">
    <div v-if="series.length > 1" class="lc-legend">
      <span v-for="(s, i) in series" :key="'lg' + i" class="lg-item">
        <i class="lg-swatch" :style="{ background: s.color }"></i>{{ s.name }}
      </span>
    </div>
    <svg class="lc-wrap" :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="xMinYMin meet">
    <defs>
      <linearGradient :id="'lg-' + uid" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#1890ff" stop-opacity="0.12"/>
        <stop offset="100%" stop-color="#1890ff" stop-opacity="0"/>
      </linearGradient>
    </defs>
      <!-- 正负区间底色（零线上方淡绿=正，下方淡红=负） -->
      <rect v-if="showZeroLine && yMax > 0"
            :x="padL" :y="py(yMax)"
            :width="W - padL - padR" :height="Math.max(0, zeroY - py(yMax))"
            fill="rgba(82, 196, 26, 0.08)"/>
      <rect v-if="showZeroLine && yMin < 0"
            :x="padL" :y="zeroY"
            :width="W - padL - padR" :height="Math.max(0, py(yMin) - zeroY)"
            fill="rgba(220, 38, 38, 0.07)"/>
      <!-- 零线 -->
      <line v-if="showZeroLine" :x1="padL" :y1="zeroY" :x2="W-padR" :y2="zeroY"
            stroke="var(--border)" stroke-dasharray="4,4"/>
    <!-- Y轴网格线 -->
    <g v-for="(tick,i) in yTicks" :key="'g'+i">
      <line :x1="padL" :y1="tick.y" :x2="W-padR" :y2="tick.y"
            stroke="var(--border)" stroke-opacity="0.5"/>
      <text :x="padL-8" :y="tick.y+4" text-anchor="end"
            font-size="11" fill="var(--text-dim)">{{ tick.label }}</text>
    </g>
    <!-- X轴标签 -->
    <g v-for="(pt,i) in xLabels" :key="'xl'+i">
      <text :x="pt.x" :y="H-pb+18" text-anchor="middle"
            font-size="11" fill="var(--text-dim)">{{ pt.label }}</text>
    </g>
    <!-- 折线 + 面积（多系列时只画连线，避免面积重叠混淆） -->
    <g v-for="(s,si) in series" :key="si">
      <path v-if="series.length === 1" :d="areaPath(s.points)" :fill="'url(#lg-' + uid + ')'" opacity="0.6"/>
      <path :d="linePath(s.points)" :stroke="s.color" stroke-width="2" fill="none"/>
      <template v-for="(pt,pi) in s.points" :key="si+'-'+pi">
        <circle v-if="pt.y != null"
                :cx="cx(s.points.indexOf(pt))" :cy="cy(pt.y)"
                r="3.5" :fill="s.color"
                @mouseenter="onHover({x: pt.x, y: pt.y, name: s.name})"
                @mouseleave="onLeave"/>
      </template>
    </g>
    <!-- hover tooltip -->
    <g v-if="tip" :transform="'translate('+tipX()+','+tipY()+')'" pointer-events="none">
      <rect x="-60" y="-36" width="120" height="30" rx="6" fill="rgba(28,32,45,0.92)"/>
      <text x="0" y="-16" text-anchor="middle" font-size="12" fill="#fff" font-weight="600">
        {{ tip.x }} · {{ tip.name }}
      </text>
      <text x="0" y="-2" text-anchor="middle" font-size="12" fill="#e0e4ec">
        {{ tipFmt(tip.y) }}
      </text>
    </g>
  </svg>
  </div>
</template>

<style scoped>
.lc { width: 100%; }
.lc-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 8px;
  padding-left: 4px;
}
.lg-item {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  color: var(--text);
}
.lg-swatch {
  display: inline-block;
  width: 14px;
  height: 4px;
  border-radius: 2px;
  margin-right: 6px;
}
.lc-wrap { display: block; width: 100%; min-width: 480px; }
</style>
