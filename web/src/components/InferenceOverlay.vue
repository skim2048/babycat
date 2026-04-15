<script setup>
import { useSSE } from '../composables/useSSE.js'

defineProps({ open: Boolean })

const { state } = useSSE()
</script>

<template>
  <Transition name="fade">
    <div v-if="open" class="infer-panel">
      <div v-if="state.inference_prompt" class="infer-config">
        <span class="infer-config-label">Q</span>
        <span class="infer-config-value">{{ state.inference_prompt }}</span>
      </div>
      <div v-if="state.trigger_keywords" class="infer-config">
        <span class="infer-config-label">K</span>
        <span class="infer-config-value">{{ state.trigger_keywords }}</span>
      </div>
      <div class="infer-result">{{ state.infer_raw || '-' }}</div>
      <div class="infer-meta">{{ state.infer_ms }} ms</div>
    </div>
  </Transition>
</template>

<style scoped>
/* 뷰포트 너비에 비례하여 폰트·여백 크기가 스케일링되도록 상대 단위 사용.
   clamp(min, preferred, max)로 너무 작거나 커지는 것을 방지. */
.infer-panel {
  position: absolute;
  bottom: 1.2vw;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(8px);
  border-radius: 0.5em;
  padding: 0.6em 1em;
  max-width: min(70%, 640px);
  text-align: center;
  pointer-events: none;
  z-index: 6;
  font-size: clamp(14px, 1.6vw, 24px);
}
.infer-config {
  display: flex;
  gap: 0.5em;
  align-items: baseline;
  justify-content: flex-start;
  font-size: 0.6em;
  font-family: var(--font-mono);
  color: rgba(255, 255, 255, 0.55);
  line-height: 1.4;
  margin-bottom: 0.2em;
  word-break: break-word;
}
.infer-config-label {
  flex-shrink: 0;
  padding: 0.1em 0.45em;
  border-radius: 0.3em;
  background: rgba(255, 255, 255, 0.12);
  color: rgba(255, 255, 255, 0.75);
  font-weight: 700;
}
.infer-config-value {
  text-align: left;
}
.infer-config + .infer-result {
  margin-top: 0.4em;
  padding-top: 0.4em;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
}
.infer-result {
  font-size: 0.8em;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.95);
  line-height: 1.5;
  word-break: break-word;
}
.infer-meta {
  font-size: 0.65em;
  font-weight: 600;
  font-family: var(--font-mono);
  color: rgba(255, 255, 255, 0.55);
  margin-top: 0.3em;
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
