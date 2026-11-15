<script setup>
import { computed } from 'vue';

const props = defineProps({
  // items: [{ label, value, color? }]
  items: { type: Array, default: () => [] },
  valueFmt: { type: Function, default: null },
  color: { type: String, default: 'var(--blue)' },
  labelWidth: { type: Number, default: 110 },
});

const max = computed(() => Math.max(1, ...props.items.map((i) => i.value)));
const barArea = computed(() => 800 - props.labelWidth - 90);

function widthOf(v) {
  return Math.max(2, (v / max.value) * barArea.value);
}
function fmt(v) {
  return props.valueFmt ? props.valueFmt(v) : String(v);
}
</script>

<template>
  <div v-if="!items.length" class="empty">暂无数据</div>
  <svg
    v-else
    class="barchart"
    :viewBox="`0 0 800 ${items.length * 26 + 10}`"
    preserveAspectRatio="xMinYMin meet"
  >
    <g v-for="(it, i) in items" :key="i" :transform="`translate(0, ${i * 26})`">
      <text x="0" y="16" class="bc-label">{{ it.label }}</text>
      <rect
        :x="labelWidth"
        y="4"
        :width="widthOf(it.value)"
        height="14"
        rx="3"
        :fill="it.color || color"
      />
      <text :x="labelWidth + widthOf(it.value) + 6" y="16" class="bc-val">
        {{ fmt(it.value) }}
      </text>
    </g>
  </svg>
</template>
