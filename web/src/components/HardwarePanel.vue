<script setup>
import { ref, computed } from 'vue'
import { useSSE } from '../composables/useSSE.js'

const { state } = useSSE()
const collapsed = ref(false)

function tempClass(c) {
  if (c >= 80) return 'temp hot'
  if (c >= 60) return 'temp warm'
  return 'temp cool'
}

const ramPercent = computed(() =>
  state.ram_total_mb > 0
    ? ((state.ram_used_mb / state.ram_total_mb) * 100).toFixed(0)
    : 0,
)
</script>

<template>
  <div class="section" :class="{ collapsed }">
    <div class="section-title" @click="collapsed = !collapsed">
      Hardware <span class="arrow">&#9660;</span>
    </div>
    <div class="section-body">
      <div class="row">
        <span class="k">CPU</span>
        <span class="v">{{ state.cpu_percent }}%</span>
      </div>
      <div class="bar-bg bar-cpu"><div class="bar-fg" :style="{ width: state.cpu_percent + '%' }"></div></div>

      <div class="row" style="margin-top: 8px">
        <span class="k">RAM</span>
        <span class="v">{{ state.ram_used_mb }} / {{ state.ram_total_mb }} MB</span>
      </div>
      <div class="bar-bg bar-ram"><div class="bar-fg" :style="{ width: ramPercent + '%' }"></div></div>

      <div class="row" style="margin-top: 8px">
        <span class="k">GPU</span>
        <span class="v">{{ state.gpu_load }}%</span>
      </div>
      <div class="bar-bg bar-gpu"><div class="bar-fg" :style="{ width: state.gpu_load + '%' }"></div></div>

      <div class="row" style="margin-top: 10px">
        <span class="k">CPU Temp</span>
        <span :class="tempClass(state.cpu_temp)">{{ state.cpu_temp }} C</span>
      </div>
      <div class="row" style="margin-top: 4px">
        <span class="k">GPU Temp</span>
        <span :class="tempClass(state.gpu_temp)">{{ state.gpu_temp }} C</span>
      </div>
    </div>
  </div>
</template>
