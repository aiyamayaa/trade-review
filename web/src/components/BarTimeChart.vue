<script>
export default {
  name: 'BarTimeChart',
  props: {
    points: { type: Array, default: () => [] }, // [{x,y}]
    color: { type: String, default: '#1890ff' },
    showZeroLine: { type: Boolean, default: false },
  },
  data() { return { tip: null }; },
  computed: {
    W() { return 800; },
    H() { return 260; },
    padL() { return 56; },
    padR() { return 20; },
    pb() { return 38; },
    bw() {
      const n = Math.max(this.points.length, 1);
      const totalW = this.W - this.padL - this.padR;
      return Math.max(14, Math.min(36, totalW / n * 0.55));
    },
    valid() { return this.points.filter((p) => p.y != null); },
    absMax() {
      if (!this.valid.length) return 10;
      const m = Math.max(...this.valid.map((p) => Math.abs(p.y)));
      return (m || 1) * 1.15;
    },
    zeroY() { return this.py(0); },
    yTicks() {
      const n = 5;
      const step = this.absMax / n;
      const ticks = [];
      for (let i = 0; i <= n; i++) {
        const v = -this.absMax + step * i * 2;
        ticks.push({ y: this.py(v), label: this.fmtTick(v) });
      }
      return ticks;
    },
    tipVal() {
      if (!this.tip) return '';
      const v = this.tip.y;
      if (Math.abs(v) >= 100) return v.toFixed(0);
      if (Math.abs(v) >= 1) return v.toFixed(2);
      return v.toFixed(3);
    },
  },
  methods: {
    py(v) {
      const range = this.absMax * 2;
      const mid = this.H - this.pb - 20;
      return mid - (v / range) * mid;
    },
    barX(i) {
      const n = Math.max(this.points.length, 1);
      const w = this.W - this.padL - this.padR;
      return this.padL + (i + 0.5) * (w / n);
    },
    barH(y) { return Math.max(1, Math.abs(this.py(0) - this.py(y))); },
    barColor(y) {
      if (!this.showZeroLine) return this.color;
      return y >= 0 ? '#52c41a' : '#f5a623';
    },
    fmtTick(v) {
      if (Math.abs(v) >= 100) return v.toFixed(0);
      if (Math.abs(v) >= 1) return v.toFixed(1);
      return v.toFixed(2);
    },
    shortLabel(x) {
      const m = String(x).match(/(\d{2})-(\d{2})$/);
      return m ? m[1] + '/' + m[2] : x;
    },
    tipBX() {
      if (!this.tip) return 0;
      return this.barX(this.points.findIndex((p) => p.x === this.tip.x));
    },
    tipBY() {
      if (!this.tip) return 0;
      return Math.min(this.py(this.tip.y), this.py(0)) - 34;
    },
  },
};
</script>

<template>
  <svg class="lc-wrap" :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="xMinYMin meet">
    <line v-if="showZeroLine" :x1="padL" :y1="zeroY" :x2="W-padR" :y2="zeroY"
          stroke="var(--border)" stroke-dasharray="4,4"/>
    <g v-for="(tick,i) in yTicks" :key="'g'+i">
      <line :x1="padL" :y1="tick.y" :x2="W-padR" :y2="tick.y"
            stroke="var(--border)" stroke-opacity="0.5"/>
      <text :x="padL-8" :y="tick.y+4" text-anchor="end"
            font-size="11" fill="var(--text-dim)">{{ tick.label }}</text>
    </g>
    <g v-for="(pt,i) in points" :key="i">
      <rect v-if="pt.y != null"
            :x="barX(i)-bw/2" :y="py(Math.max(0,pt.y))"
            :width="bw" :height="barH(pt.y)"
            rx="3" :fill="barColor(pt.y)"
            @mouseenter="tip={x:pt.x, y:pt.y}"
            @mouseleave="tip=null"/>
      <text :x="barX(i)" :y="H-pb+16" text-anchor="middle"
            font-size="10" fill="var(--text-dim)">{{ shortLabel(pt.x) }}</text>
    </g>
    <g v-if="tip" :transform="'translate('+tipBX()+','+tipBY()+')'" pointer-events="none">
      <rect x="-50" y="-30" width="100" height="24" rx="6" fill="rgba(28,32,45,0.92)"/>
      <text x="0" y="-14" text-anchor="middle" font-size="11" fill="#fff">{{ tip.x }} · {{ tipVal }}</text>
    </g>
  </svg>
</template>

<style scoped>
.lc-wrap { display: block; width: 100%; min-width: 480px; }
</style>
