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

const cells = computed(() => [
  { name: 'CPU', pct: sse.cpu_percent, temp: formatTemp(sse.cpu_temp), line: points(history.cpu) },
  { name: 'GPU', pct: sse.gpu_load, temp: formatTemp(sse.gpu_temp), line: points(history.gpu) },
  { name: 'RAM', pct: ramPct.value, temp: '—', line: points(history.ram) },
  { name: 'DISK', pct: diskPct.value, temp: '—', line: points(history.disk) },
])
</script>

<template>
  <div class="res-panel">
    <div v-for="cell in cells" :key="cell.name" class="res-cell">
      <div class="res-head">
        <span class="res-name">{{ cell.name }}</span>
        <span class="res-pct">{{ formatPct(cell.pct) }}</span>
        <span class="res-temp">{{ cell.temp }}</span>
      </div>
      <svg viewBox="0 0 100 44" preserveAspectRatio="none" class="res-graph">
        <polyline :points="cell.line" fill="none" stroke="var(--color-accent)" stroke-width="1" vector-effect="non-scaling-stroke" />
        <polyline :points="cell.line ? `0,44 ${cell.line} 100,44` : ''" fill="color-mix(in srgb, var(--color-accent) 14%, transparent)" stroke="none" />
      </svg>
    </div>
  </div>
</template>

<style scoped>
.res-panel {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  border-radius: 8px;
  background: var(--color-neutral-900);
  overflow: hidden;
}
.res-cell {
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 7px;
  font-size: 13px;
  box-shadow: 0 0 0 1px var(--color-divider);
}
.res-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.res-name {
  flex: 1;
  color: var(--color-neutral-400);
  letter-spacing: 0.06em;
}
.res-pct { font-variant-numeric: tabular-nums; }
.res-temp {
  color: var(--color-neutral-400);
  font-variant-numeric: tabular-nums;
}
.res-graph {
  width: 100%;
  height: 44px;
  display: block;
}
</style>
