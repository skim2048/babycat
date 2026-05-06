<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useSSE } from '../composables/useSSE.js'
import { useLocale } from '../composables/useLocale.js'

defineProps({
  open: Boolean,
})

const emit = defineEmits(['toggle'])

const { state: sseState } = useSSE()
const { t } = useLocale()

const HISTORY_LEN = 30
const cpuUsageHist = []
const cpuTempHist = []
const gpuUsageHist = []
const gpuTempHist = []
const ramUsageHist = []

const cpuCanvasRef = ref(null)
const gpuCanvasRef = ref(null)
const ramCanvasRef = ref(null)

const ramPercent = computed(() =>
  sseState.ram_total_mb > 0
    ? Math.round((sseState.ram_used_mb / sseState.ram_total_mb) * 100)
    : 0,
)

const segmentRecorderStateLabel = computed(() =>
  t(`live.segmentRecorder.state.${sseState.segment_recorder_state || 'disabled'}`),
)

const segmentRecorderAgeLabel = computed(() => {
  if (sseState.segment_recorder_last_segment_age_s == null) return '—'
  return `${sseState.segment_recorder_last_segment_age_s.toFixed(1)}s`
})

function pushHist(arr, val) {
  arr.push(typeof val === 'number' ? val : 0)
  if (arr.length > HISTORY_LEN) arr.shift()
}

function drawChart(canvas, series) {
  if (!canvas) return
  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  canvas.width = Math.round(rect.width * dpr)
  canvas.height = Math.round(rect.height * dpr)
  const ctx = canvas.getContext('2d')
  ctx.scale(dpr, dpr)
  const width = rect.width
  const height = rect.height

  const style = getComputedStyle(document.documentElement)
  ctx.fillStyle = style.getPropertyValue('--bg-surface-secondary').trim()
  ctx.fillRect(0, 0, width, height)

  for (const seriesDef of series) {
    if (!seriesDef.data.length) continue
    ctx.beginPath()
    ctx.strokeStyle = style.getPropertyValue(seriesDef.colorVar).trim()
    ctx.lineWidth = 1.5
    ctx.globalAlpha = seriesDef.alpha ?? 1
    ctx.setLineDash(seriesDef.dashed ? [3, 3] : [])
    const offset = HISTORY_LEN - seriesDef.data.length
    for (let index = 0; index < seriesDef.data.length; index += 1) {
      const x = ((offset + index) / (HISTORY_LEN - 1)) * width
      const y = height - (Math.min(Math.max(seriesDef.data[index], 0), 100) / 100) * (height - 2) - 1
      if (index === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    }
    ctx.stroke()
  }
  ctx.globalAlpha = 1
  ctx.setLineDash([])
}

function redrawSidebar() {
  drawChart(cpuCanvasRef.value, [
    { data: cpuUsageHist, colorVar: '--bar-cpu', dashed: false, alpha: 1 },
    { data: cpuTempHist, colorVar: '--bar-cpu', dashed: true, alpha: 0.45 },
  ])
  drawChart(gpuCanvasRef.value, [
    { data: gpuUsageHist, colorVar: '--bar-gpu', dashed: false, alpha: 1 },
    { data: gpuTempHist, colorVar: '--bar-gpu', dashed: true, alpha: 0.45 },
  ])
  drawChart(ramCanvasRef.value, [
    { data: ramUsageHist, colorVar: '--bar-ram', dashed: false, alpha: 1 },
  ])
}

watch(
  () => [
    sseState.cpu_percent,
    sseState.cpu_temp,
    sseState.gpu_load,
    sseState.gpu_temp,
    sseState.ram_used_mb,
    sseState.ram_total_mb,
  ],
  ([cpu, cpuTemp, gpu, gpuTemp, ramUsed, ramTotal]) => {
    const ram = ramTotal > 0 ? Math.round((ramUsed / ramTotal) * 100) : 0
    pushHist(cpuUsageHist, cpu)
    pushHist(cpuTempHist, cpuTemp)
    pushHist(gpuUsageHist, gpu)
    pushHist(gpuTempHist, gpuTemp)
    pushHist(ramUsageHist, ram)
    nextTick(redrawSidebar)
  },
)

onMounted(() => {
  nextTick(redrawSidebar)
})
</script>

<template>
  <div class="vsb-acc">
    <button class="vsb-acc-header" @click="emit('toggle')">
      <span>{{ t('live.system') }}</span>
      <svg class="vsb-acc-chevron" :class="{ open }" width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="2,4.5 6,8 10,4.5"/>
      </svg>
    </button>
    <div class="vsb-acc-body" :class="{ open }">
      <div class="vsb-acc-content">
        <div class="vsb-section">
          <div class="vsb-header">
            <span class="vsb-name vsb-cpu">CPU</span>
            <div class="vsb-legend">
              <span class="vsb-leg-usage vsb-cpu">{{ t('live.usage') }}</span>
              <span class="vsb-leg-temp vsb-cpu">{{ t('live.temperature') }}</span>
            </div>
          </div>
          <canvas ref="cpuCanvasRef" class="vsb-canvas"></canvas>
          <div class="vsb-footer">
            <span class="vsb-pct vsb-cpu">{{ sseState.cpu_percent }}%</span>
            <span class="vsb-deg">{{ sseState.cpu_temp }}°</span>
          </div>
        </div>

        <div class="vsb-section">
          <div class="vsb-header">
            <span class="vsb-name vsb-gpu">GPU</span>
            <div class="vsb-legend">
              <span class="vsb-leg-usage vsb-gpu">{{ t('live.usage') }}</span>
              <span class="vsb-leg-temp vsb-gpu">{{ t('live.temperature') }}</span>
            </div>
          </div>
          <canvas ref="gpuCanvasRef" class="vsb-canvas"></canvas>
          <div class="vsb-footer">
            <span class="vsb-pct vsb-gpu">{{ sseState.gpu_load }}%</span>
            <span class="vsb-deg">{{ sseState.gpu_temp }}°</span>
          </div>
        </div>

        <div class="vsb-section">
          <div class="vsb-header">
            <span class="vsb-name vsb-ram">RAM</span>
            <div class="vsb-legend">
              <span class="vsb-leg-usage vsb-ram">{{ t('live.usage') }}</span>
            </div>
          </div>
          <canvas ref="ramCanvasRef" class="vsb-canvas"></canvas>
          <div class="vsb-footer">
            <span class="vsb-pct vsb-ram">{{ ramPercent }}%</span>
          </div>
        </div>

        <div class="vsb-section">
          <div class="vsb-header">
            <span class="vsb-name vsb-recorder">{{ t('live.segmentRecorder.title') }}</span>
          </div>
          <div class="vsb-recorder-grid">
            <span class="vsb-recorder-label">{{ t('live.segmentRecorder.status') }}</span>
            <span class="vsb-recorder-value" :class="`state-${sseState.segment_recorder_state}`">{{ segmentRecorderStateLabel }}</span>
            <span class="vsb-recorder-label">{{ t('live.segmentRecorder.count') }}</span>
            <span class="vsb-recorder-value">{{ sseState.segment_recorder_segment_count }}</span>
            <span class="vsb-recorder-label">{{ t('live.segmentRecorder.age') }}</span>
            <span class="vsb-recorder-value">{{ segmentRecorderAgeLabel }}</span>
            <span class="vsb-recorder-label">{{ t('live.segmentRecorder.error') }}</span>
            <span class="vsb-recorder-value vsb-recorder-error">{{ sseState.segment_recorder_error || '—' }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.vsb-acc {
  background: var(--bg-surface);
  flex-shrink: 0;
}

.vsb-acc-header {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 12px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.9px;
  color: var(--text-3);
  transition: background 0.15s, color 0.15s;
  text-align: left;
}

.vsb-acc-header:hover {
  background: var(--bg-surface-hover);
  color: var(--text-1);
}

.vsb-acc-chevron {
  color: var(--text-4);
  flex-shrink: 0;
  transition: transform 0.22s ease;
}

.vsb-acc-chevron.open {
  transform: rotate(180deg);
}

.vsb-acc-body {
  overflow: hidden;
  max-height: 0;
  transition: max-height 0.28s ease;
}

.vsb-acc-body.open {
  max-height: 520px;
}

.vsb-acc-content {
  padding: 10px 12px 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  border-top: 1px solid var(--border-subtle);
}

.vsb-section {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.vsb-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.vsb-name {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.4px;
}

.vsb-recorder {
  color: var(--text-1);
}

.vsb-legend {
  display: flex;
  gap: 6px;
  align-items: center;
}

.vsb-leg-usage,
.vsb-leg-temp {
  font-size: 9px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 3px;
  opacity: 0.6;
}

.vsb-leg-usage::before {
  content: '';
  display: inline-block;
  width: 14px;
  height: 1.5px;
  background: currentColor;
  border-radius: 1px;
}

.vsb-leg-temp::before {
  content: '';
  display: inline-block;
  width: 14px;
  height: 1px;
  background: repeating-linear-gradient(
    to right,
    currentColor 0px,
    currentColor 3px,
    transparent 3px,
    transparent 6px
  );
}

.vsb-cpu {
  color: var(--bar-cpu);
}

.vsb-gpu {
  color: var(--bar-gpu);
}

.vsb-ram {
  color: var(--bar-ram);
}

.vsb-canvas {
  display: block;
  width: 100%;
  height: 58px;
  border-radius: 4px;
}

.vsb-footer {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.vsb-pct {
  font-size: 13px;
  font-weight: 700;
}

.vsb-deg {
  font-size: 11px;
  color: var(--text-3);
}

.vsb-recorder-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px 10px;
  padding: 8px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  background: var(--bg-surface-secondary);
}

.vsb-recorder-label,
.vsb-recorder-value {
  font-size: 10px;
  line-height: 1.35;
}

.vsb-recorder-label {
  color: var(--text-3);
  font-weight: 600;
}

.vsb-recorder-value {
  color: var(--text-1);
  font-family: var(--font-mono);
  text-align: right;
}

.vsb-recorder-error {
  max-width: 130px;
  word-break: break-word;
}

.state-running {
  color: var(--ok, #1c8c5e);
}

.state-error {
  color: var(--danger, #c2410c);
}

.state-starting {
  color: var(--warn, #a16207);
}
</style>
