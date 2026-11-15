<script>
export default {
  name: 'BarGroupChart',
  props: {
    groups: { type: Array, default: () => [] }, // [{label, points:[{x,y}], color}]
  },
  computed: {
    W() { return 800; },
    H() { return 260; },
    padL() { return 48; },
    padR() { return 24; },
    pb() { return 38; },
    nGroups() { return this.groups.length; },
    gbw() {
      const n = Math.max(this.groups[0]?.points?.length || 1, 1);
      const totalW = this.W - this.padL - this.padR;
      return Math.max(8, Math.min(24, (totalW / n) / (this.nGroups + 0.6)));
    },
    allVals() {
      return this.groups.flatMap((g) =>
        g.points.filter((p) => p.y != null).map((p) => p.y)
      );
    },
    yMax() {
      if (!this.allVals.length) return 10;
      return Math.max(...this.allVals) * 1.15;
    },
    zeroY() { return this.H - this.pb; },
    yTicks() {
      const n = 5;
      const step = this.yMax / n || 1;
      const ticks = [];
      for (let i = 0; i <= n; i++) {
        const v = step * i;
        const yPos = this.zeroY - (v / this.yMax) * (this.H - this.pb - 20);
        ticks.push({ y: yPos, label: v.toFixed(0) });
      }
      return ticks;
    },
    xLabels() {
      const pts = this.groups[0]?.points || [];
      const gap = Math.max(1, Math.ceil(pts.length / 10));
      return pts.filter((_, i) => i % gap === 0);
    },
  },
  methods: {
    py(v) {
      if (!this.yMax) return this.zeroY;
      return this.zeroY - (v / this.yMax) * (this.H - this.pb - 20);
    },
    groupX(dateIdx, groupIdx) {
      const n = Math.max(this.groups[0]?.points?.length || 1, 1);
      const totalW = this.W - this.padL - this.padR;
      const cellW = totalW / n;
      const base = this.padL + dateIdx * cellW + cellW / 2;
      return base + (groupIdx - (this.nGroups - 1) / 2) * (this.gbw + 3);
    },
    groupCenter(i) {
      const n = Math.max(this.groups[0]?.points?.length || 1, 1);
      const totalW = this.W - this.padL - this.padR;
      return this.padL + (i + 0.5) * (totalW / n);
    },
    shortLabel(x) {
      const m = String(x).match(/(\d{2})-(\d{2})$/);
      return m ? m[1] + '/' + m[2] : x;
    },
  },
};
</script>

<template>
  <svg class="lc-wrap" :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="xMinYMin meet">
    <g v-for="(tick,i) in yTicks" :key="'g'+i">
      <line :x1="padL" :y1="tick.y" :x2="W-padR" :y2="tick.y"
            stroke="var(--border)" stroke-opacity="0.5"/>
      <text :x="padL-8" :y="tick.y+4" text-anchor="end"
            font-size="11" fill="var(--text-dim)">{{ tick.label }}</text>
    </g>
    <g v-for="(gi,gIdx) in groups" :key="gIdx">
      <template v-for="(pt,i) in gi.points" :key="gIdx+'-'+i">
        <rect v-if="pt.y != null"
              :x="groupX(i,gIdx)-gbw/2"
              :y="py(pt.y)"
              :width="gbw" :height="Math.max(1, zeroY - py(pt.y))"
              rx="2" :fill="gi.color" opacity="0.85"/>
      </template>
    </g>
    <!-- X 标签 -->
    <g v-for="(pt,i) in xLabels" :key="'xl'+i">
      <text :x="groupCenter(groups[0].points.indexOf(pt))"
            :y="H-pb+16" text-anchor="middle"
            font-size="10" fill="var(--text-dim)">{{ shortLabel(pt.x) }}</text>
    </g>
    <!-- 图例 -->
    <g :transform="'translate('+(W-padR-80)+', 22)'">
      <g v-for="(g,idx) in groups" :key="'leg'+idx"
         :transform="'translate(0,'+(idx*20)+')'">
        <rect width="12" height="12" rx="2" :fill="g.color" opacity="0.85"/>
        <text x="18" y="11" font-size="11" fill="var(--text-dim)">{{ g.label }}</text>
      </g>
    </g>
  </svg>
</template>

<style scoped>
.lc-wrap { display: block; width: 100%; min-width: 480px; }
</style>
