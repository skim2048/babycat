<script setup>
import { useSSE } from '../composables/useSSE.js'

defineProps({ open: Boolean })

const { state } = useSSE()
</script>

<template>
  <Transition name="fade">
    <div v-if="open" class="infer-panel">
      <div class="infer-result">{{ state.infer_raw || '-' }}</div>
      <div class="infer-meta">{{ state.infer_ms }} ms</div>
    </div>
  </Transition>
</template>

<style scoped>
.infer-panel {
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(8px);
  border-radius: 6px;
  padding: 8px 12px;
  max-width: 320px;
  pointer-events: none;
}
.infer-result {
  font-size: 12px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.9);
  line-height: 1.5;
  word-break: break-word;
}
.infer-meta {
  font-size: 10px;
  font-weight: 600;
  font-family: var(--font-mono);
  color: rgba(255, 255, 255, 0.45);
  margin-top: 4px;
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
