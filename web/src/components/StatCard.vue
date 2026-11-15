<script setup>
defineProps({
  label: { type: String, default: '' },
  value: { type: [String, Number], default: '-' },
  sub: { type: String, default: '' },
  accent: { type: String, default: '' }, // red | green | blue | gold
});
</script>

<template>
  <div class="stat-card" :class="accent">
    <div class="stat-label">{{ label }}</div>
    <div class="stat-value">{{ value }}</div>
    <div v-if="sub" class="stat-sub">{{ sub }}</div>
  </div>
</template>
