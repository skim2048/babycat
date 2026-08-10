<script setup>
import { computed, reactive, watch } from 'vue'
import SheetFrame from './SheetFrame.vue'
import { useSSE } from '../composables/useSSE.js'
import { useLocale } from '../composables/useLocale.js'

defineEmits(['close'])

const { state: sse } = useSSE()
const { t } = useLocale()

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
  { immediate: true },
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

const rows = computed(() => [
  { name: 'CPU', pct: sse.cpu_percent, temp: formatTemp(sse.cpu_temp), line: points(history.cpu) },
  { name: 'GPU', pct: sse.gpu_load, temp: formatTemp(sse.gpu_temp), line: points(history.gpu) },
  { name: 'RAM', pct: ramPct.value, temp: '—', line: points(history.ram) },
  { name: 'DISK', pct: diskPct.value, temp: '—', line: points(history.disk) },
])
</script>

<template>
  <SheetFrame :title="t('dashboard.resources')" @close="$emit('close')">
    <div class="res-list">
      <div v-for="(row, i) in rows" :key="row.name" class="res-row" :class="{ first: i === 0 }">
        <div class="res-head">
          <span class="res-name">{{ row.name }}</span>
          <span class="res-gauge"><span :style="{ width: formatPct(row.pct) }"></span></span>
          <span class="res-pct">{{ formatPct(row.pct) }}</span>
          <span class="res-temp">{{ row.temp }}</span>
        </div>
        <svg viewBox="0 0 100 44" preserveAspectRatio="none" class="res-graph">
          <polyline :points="row.line" fill="none" stroke="var(--color-accent)" stroke-width="1" vector-effect="non-scaling-stroke" />
          <polyline :points="row.line ? `0,44 ${row.line} 100,44` : ''" fill="color-mix(in srgb, var(--color-accent) 14%, transparent)" stroke="none" />
        </svg>
      </div>
    </div>
  </SheetFrame>
</template>

<style scoped>
.res-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.res-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 14px;
  border-top: 1px solid var(--color-divider);
}
.res-row.first {
  padding-top: 0;
  border-top: none;
}
.res-head {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}
.res-name {
  width: 40px;
  color: var(--color-neutral-400);
  letter-spacing: 0.06em;
}
.res-gauge {
  flex: 1;
  height: 4px;
  border-radius: 2px;
  background: var(--color-neutral-800);
  overflow: hidden;
  display: block;
}
.res-gauge span {
  display: block;
  height: 100%;
  background: var(--color-accent);
  transition: width 0.6s cubic-bezier(0.22, 1, 0.36, 1);
}
.res-pct {
  width: 38px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.res-temp {
  width: 44px;
  text-align: right;
  color: var(--color-neutral-400);
  font-variant-numeric: tabular-nums;
}
.res-graph {
  width: 100%;
  height: 44px;
  display: block;
}
</style>
