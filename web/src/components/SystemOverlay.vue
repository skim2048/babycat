<script setup>
import { computed } from 'vue'
import { useSSE } from '../composables/useSSE.js'

defineProps({ open: Boolean })

const { state } = useSSE()

const ramPercent = computed(() =>
  state.ram_total_mb > 0
    ? Math.round((state.ram_used_mb / state.ram_total_mb) * 100)
    : 0,
)
</script>

<template>
  <Transition name="fade">
    <div v-if="open" class="system-panel">
      <div class="sys-row">
        <span class="sys-label">CPU</span>
        <span class="sys-value">{{ state.cpu_percent }}%</span>
        <span class="sys-temp">{{ state.cpu_temp }}°</span>
      </div>
      <div class="sys-row">
        <span class="sys-label">GPU</span>
        <span class="sys-value">{{ state.gpu_load }}%</span>
        <span class="sys-temp">{{ state.gpu_temp }}°</span>
      </div>
      <div class="sys-row">
        <span class="sys-label">RAM</span>
        <span class="sys-value">{{ ramPercent }}%</span>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.system-panel {
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(8px);
  border-radius: 6px;
  padding: 6px 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  pointer-events: none;
}
.sys-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.sys-label {
  font-size: 10px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.5);
  width: 28px;
}
.sys-value {
  font-size: 11px;
  font-weight: 700;
  font-family: var(--font-mono);
  color: rgba(255, 255, 255, 0.9);
  width: 32px;
  text-align: right;
}
.sys-temp {
  font-size: 10px;
  font-weight: 600;
  font-family: var(--font-mono);
  color: rgba(255, 255, 255, 0.5);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
