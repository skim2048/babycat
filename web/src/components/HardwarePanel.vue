<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useSSE } from '../composables/useSSE.js'

const { state } = useSSE()
const collapsed = ref(false)

const MAX_POINTS = 60

const history = {
  cpu: [],
  ram: [],
  gpu: [],
  cpuTemp: [],
  gpuTemp: [],
}

const usageCanvas = ref(null)
const tempCanvas = ref(null)

function pushHistory() {
  const ramPct = state.ram_total_mb > 0
    ? (state.ram_used_mb / state.ram_total_mb) * 100
    : 0

  history.cpu.push(state.cpu_percent ?? 0)
  history.ram.push(ramPct)
  history.gpu.push(state.gpu_load ?? 0)
  history.cpuTemp.push(state.cpu_temp ?? 0)
  history.gpuTemp.push(state.gpu_temp ?? 0)

  if (history.cpu.length > MAX_POINTS) {
    history.cpu.shift()
    history.ram.shift()
    history.gpu.shift()
    history.cpuTemp.shift()
    history.gpuTemp.shift()
  }
}

function getColor(name) {
  const style = getComputedStyle(document.documentElement)
  const map = {
    cpu: '--bar-cpu',
    ram: '--bar-ram',
    gpu: '--bar-gpu',
    cpuTemp: '--bar-cpu',
    gpuTemp: '--bar-gpu',
  }
  return style.getPropertyValue(map[name]).trim()
}

function getThemeColors() {
  const style = getComputedStyle(document.documentElement)
  return {
    grid: style.getPropertyValue('--border-subtle').trim(),
    text: style.getPropertyValue('--text-4').trim(),
    bg: style.getPropertyValue('--bg-surface').trim(),
  }
}

function drawChart(canvas, series, maxVal, unit) {
  if (!canvas) return
  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  const w = rect.width
  const h = rect.height

  canvas.width = w * dpr
  canvas.height = h * dpr
  const ctx = canvas.getContext('2d')
  ctx.scale(dpr, dpr)

  const theme = getThemeColors()
  ctx.fillStyle = theme.bg
  ctx.fillRect(0, 0, w, h)

  // Grid lines + Y-axis labels
  ctx.strokeStyle = theme.grid
  ctx.lineWidth = 0.5
  ctx.fillStyle = theme.text
  ctx.font = '9px -apple-system, sans-serif'
  ctx.textAlign = 'right'
  for (let i = 0; i <= 4; i++) {
    const y = (h * i) / 4
    if (i > 0 && i < 4) {
      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.lineTo(w, y)
      ctx.stroke()
    }
    const label = Math.round(maxVal - (maxVal * i) / 4)
    ctx.fillText(label + unit, w - 3, y + 10)
  }

  // Draw each series
  for (const { data, color } of series) {
    if (data.length < 2) continue
    const len = data.length
    const step = w / (MAX_POINTS - 1)

    ctx.beginPath()
    ctx.strokeStyle = color
    ctx.lineWidth = 1.5
    ctx.lineJoin = 'round'

    for (let i = 0; i < len; i++) {
      const x = (MAX_POINTS - len + i) * step
      const y = h - (data[i] / maxVal) * h
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    }
    ctx.stroke()

    // Fill area
    ctx.lineTo((MAX_POINTS - 1) * step, h)
    ctx.lineTo((MAX_POINTS - len) * step, h)
    ctx.closePath()
    if (color.startsWith('#')) {
      const r = parseInt(color.slice(1, 3), 16)
      const g = parseInt(color.slice(3, 5), 16)
      const b = parseInt(color.slice(5, 7), 16)
      ctx.fillStyle = `rgba(${r}, ${g}, ${b}, 0.08)`
    }
    ctx.fill()
  }
}

function redraw() {
  drawChart(usageCanvas.value, [
    { data: history.cpu, color: getColor('cpu') },
    { data: history.ram, color: getColor('ram') },
    { data: history.gpu, color: getColor('gpu') },
  ], 100, '%')

  drawChart(tempCanvas.value, [
    { data: history.cpuTemp, color: getColor('cpuTemp') },
    { data: history.gpuTemp, color: getColor('gpuTemp') },
  ], 100, '°')
}

const ramPercent = () => {
  return state.ram_total_mb > 0
    ? ((state.ram_used_mb / state.ram_total_mb) * 100).toFixed(0)
    : 0
}

watch(() => state.cpu_percent, () => {
  pushHistory()
  if (!collapsed.value) nextTick(redraw)
})

watch(collapsed, (val) => {
  if (!val) nextTick(redraw)
})

let themeQuery
onMounted(() => {
  themeQuery = window.matchMedia('(prefers-color-scheme: dark)')
  themeQuery.addEventListener('change', redraw)
})
onUnmounted(() => {
  if (themeQuery) themeQuery.removeEventListener('change', redraw)
})
</script>

<template>
  <div class="section" :class="{ collapsed }">
    <div class="section-title" @click="collapsed = !collapsed">
      Hardware <span class="arrow">&#9660;</span>
    </div>
    <div class="section-body hw-body">
      <div class="hw-chart-group">
        <div class="hw-chart-header">
          <span class="hw-chart-label">Usage</span>
          <div class="hw-legend">
            <span class="hw-legend-item hw-legend-cpu">CPU {{ state.cpu_percent }}%</span>
            <span class="hw-legend-item hw-legend-ram">RAM {{ ramPercent() }}%</span>
            <span class="hw-legend-item hw-legend-gpu">GPU {{ state.gpu_load }}%</span>
          </div>
        </div>
        <canvas ref="usageCanvas" class="hw-canvas"></canvas>
      </div>
      <div class="hw-chart-group">
        <div class="hw-chart-header">
          <span class="hw-chart-label">Temperature</span>
          <div class="hw-legend">
            <span class="hw-legend-item hw-legend-cpu">CPU {{ state.cpu_temp }}°</span>
            <span class="hw-legend-item hw-legend-gpu">GPU {{ state.gpu_temp }}°</span>
          </div>
        </div>
        <canvas ref="tempCanvas" class="hw-canvas"></canvas>
      </div>
    </div>
  </div>
</template>
