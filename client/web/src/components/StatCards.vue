<script setup>
import { computed, reactive, watch } from 'vue'
import { useSSE } from '../composables/useSSE.js'

const { state: sse } = useSSE()

// @claude 21 samples ≒ the mockup's sparkline resolution; one sample per SSE
// @claude report keeps the line moving at the report cadence.
const HISTORY = 21

const history = reactive({ cpu: [], gpu: [], ram: [], disk: [] })

function push(list, value) {
  list.push(Number.isFinite(value) ? value : 0)
  if (list.length > HISTORY) list.shift()
}

const ramPct = computed(() =>
  sse.ram_total_mb > 0 ? (sse.ram_used_mb / sse.ram_total_mb) * 100 : 0,
)
const diskPct = computed(() =>
  sse.disk_total_mb > 0 ? (sse.disk_used_mb / sse.disk_total_mb) * 100 : 0,
)

watch(
  () => [sse.cpu_percent, sse.gpu_load, ramPct.value, diskPct.value],
  ([cpu, gpu, ram, disk]) => {
    push(history.cpu, cpu)
    push(history.gpu, gpu)
    push(history.ram, ram)
    push(history.disk, disk)
  },
)

function points(list) {
  if (!list.length) return ''
  return list
    .map((v, i) => {
      const x = (i / Math.max(list.length - 1, 1)) * 100
      const y = 44 - (Math.min(Math.max(v, 0), 100) / 100) * 40
      return `${x},${y}`
    })
    .join(' ')
}

function formatPct(value) {
  return Number.isFinite(value) ? `${Math.round(value)}%` : '—'
}
function formatTemp(value) {
  return Number.isFinite(value) && value > 0 ? `${Math.round(value)}°C` : '—'
}

const cards = computed(() => [
  { name: 'CPU', pct: sse.cpu_percent, temp: formatTemp(sse.cpu_temp), line: points(history.cpu) },
  { name: 'GPU', pct: sse.gpu_load, temp: formatTemp(sse.gpu_temp), line: points(history.gpu) },
  { name: 'RAM', pct: ramPct.value, temp: '—', line: points(history.ram) },
  { name: 'DISK', pct: diskPct.value, temp: '—', line: points(history.disk) },
])
</script>

<template>
  <div class="stat-cards">
    <div v-for="(card, i) in cards" :key="card.name" class="stat-card" :class="{ first: i === 0 }">
      <div class="stat-head">
        <span class="stat-name">{{ card.name }}</span>
        <span class="stat-pct">{{ formatPct(card.pct) }}</span>
        <span class="stat-temp">{{ card.temp }}</span>
      </div>
      <span class="stat-gauge"><span :style="{ width: formatPct(card.pct) }"></span></span>
      <svg viewBox="0 0 100 44" preserveAspectRatio="none" class="stat-spark">
        <polyline :points="card.line" fill="none" stroke="var(--color-accent)" stroke-width="1" vector-effect="non-scaling-stroke" />
        <polyline :points="card.line ? `0,44 ${card.line} 100,44` : ''" fill="color-mix(in srgb, var(--color-accent) 14%, transparent)" stroke="none" />
      </svg>
    </div>
  </div>
</template>

<style scoped>
.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  border: 1px solid var(--color-neutral-800);
  border-radius: 8px;
  background: var(--color-neutral-900);
  overflow: hidden;
}
.stat-card {
  border-left: 1px solid var(--color-divider);
  padding: 12px 12px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 12.5px;
}
.stat-card.first { border-left-color: transparent; }
.stat-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.stat-name {
  flex: 1;
  color: var(--color-neutral-500);
  letter-spacing: 0.06em;
}
.stat-pct { font-variant-numeric: tabular-nums; }
.stat-temp {
  color: var(--color-neutral-500);
  font-variant-numeric: tabular-nums;
}
.stat-gauge {
  height: 4px;
  border-radius: 2px;
  background: var(--color-neutral-800);
  overflow: hidden;
  display: block;
}
.stat-gauge span {
  display: block;
  height: 100%;
  background: var(--color-accent);
  transition: width 0.6s cubic-bezier(0.22, 1, 0.36, 1);
}
.stat-spark {
  width: 100%;
  height: 44px;
  display: block;
}
</style>
