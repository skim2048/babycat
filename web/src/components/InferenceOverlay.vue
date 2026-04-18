<script setup>
import { computed } from 'vue'
import { useSSE } from '../composables/useSSE.js'
import { authFetch } from '../composables/useFetch.js'

defineProps({ open: Boolean })

const { state } = useSSE()

// @claude Convert ms -> s and truncate to two decimals (e.g. 5038.5 -> 5.03).
const inferSec = computed(() => (Math.floor(state.infer_ms / 10) / 100).toFixed(2))

// @claude Whether to show the VLM section (badge + radios). Visible when at least one model exists.
const showVlmSection = computed(() => (state.vlm_models?.length || 0) >= 1)

// @claude Disable radios when not ready (initializing / loading / switching / error, etc.).
const switchDisabled = computed(() => state.vlm_state !== 'ready')

const vlmStatusLabel = computed(() => {
  const s = state.vlm_state
  if (s === 'ready') return 'VLM ready'
  if (s === 'switching') return 'Switching VLM ...'
  if (s === 'downloading') return 'Downloading VLM ...'
  if (s === 'compiling') return 'Compiling VLM ...'
  if (s === 'initializing') return 'Initializing VLM ...'
  if (s === 'error') return `VLM error: ${state.vlm_error || 'unknown'}`
  return 'Loading VLM ...'
})

// @claude In-progress states (spinner) — every stage the user should see as "work in flight on the backend".
const vlmInProgress = computed(() =>
  ['initializing', 'loading', 'switching', 'downloading', 'compiling'].includes(state.vlm_state)
)

async function selectModel(name) {
  if (!name || name === state.vlm_current_model || switchDisabled.value) return
  try {
    await authFetch('/vlm/switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: name }),
    })
  } catch (e) {
    console.error('VLM switch failed:', e)
  }
}

// @claude Display only the last path segment of the model id (e.g. Efficient-Large-Model/VILA1.5-3b -> VILA1.5-3b).
function shortName(id) {
  if (!id) return ''
  const parts = id.split('/')
  return parts[parts.length - 1]
}
</script>

<template>
  <Transition name="fade">
    <div v-if="open" class="infer-panel">
      <div v-if="showVlmSection" class="infer-model-section">
        <div class="infer-vlm-status" :class="`vlm-${state.vlm_state}`">
          <span v-if="vlmInProgress" class="vlm-spinner" aria-hidden="true"></span>
          <svg v-else-if="state.vlm_state === 'ready'" class="vlm-icon" width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="2,6 5,9 10,3" />
          </svg>
          <svg v-else class="vlm-icon" width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="3" y1="3" x2="9" y2="9" />
            <line x1="9" y1="3" x2="3" y2="9" />
          </svg>
          <span>{{ vlmStatusLabel }}</span>
        </div>
        <div class="infer-model-row" role="radiogroup" aria-label="VLM 모델">
          <label
            v-for="m in state.vlm_models"
            :key="m"
            class="infer-model-option"
            :class="{ disabled: switchDisabled, active: m === state.vlm_current_model }"
            :title="m"
          >
            <input
              type="radio"
              name="vlm-model"
              :value="m"
              :checked="m === state.vlm_current_model"
              :disabled="switchDisabled"
              @change="selectModel(m)"
            />
            <span class="infer-model-label">{{ shortName(m) }}</span>
          </label>
        </div>
      </div>
      <div v-if="state.inference_prompt" class="infer-config">
        <span class="infer-config-label">Q</span>
        <span class="infer-config-value">{{ state.inference_prompt }}</span>
      </div>
      <div v-if="state.trigger_keywords" class="infer-config">
        <span class="infer-config-label">K</span>
        <span class="infer-config-value">{{ state.trigger_keywords }}</span>
      </div>
      <div class="infer-config infer-answer">
        <span class="infer-config-label">A</span>
        <span class="infer-config-value">{{ state.infer_raw || '-' }}</span>
      </div>
      <div class="infer-meta">{{ inferSec }} s</div>
    </div>
  </Transition>
</template>

<style scoped>
/* @claude Use viewport-relative units so font and padding scale with viewport width.
   @claude clamp(min, preferred, max) prevents the result from getting too small or too large. */
.infer-panel {
  position: absolute;
  bottom: calc(1.2vw + 56px); /* @claude Sit above the unified video-bar (height ~44px + padding). */
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(8px);
  border-radius: 0.5em;
  padding: 0.6em 1em;
  max-width: min(70%, 640px);
  text-align: center;
  pointer-events: auto;
  z-index: 6;
  font-size: clamp(14px, 1.6vw, 24px);
}
.infer-model-section {
  margin-bottom: 0.5em;
  padding-bottom: 0.4em;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}
.infer-vlm-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-family: var(--font-mono);
  color: rgba(255, 255, 255, 0.7);
  margin-bottom: 0.35em;
}
.infer-vlm-status.vlm-ready { color: rgba(167, 243, 208, 1); }
.infer-vlm-status.vlm-error { color: rgba(252, 165, 165, 1); }
.vlm-icon { flex-shrink: 0; }
.vlm-spinner {
  width: 10px;
  height: 10px;
  border: 1.5px solid rgba(255, 255, 255, 0.25);
  border-top-color: rgba(255, 255, 255, 0.9);
  border-radius: 50%;
  animation: vlm-spin 0.9s linear infinite;
  flex-shrink: 0;
}
@keyframes vlm-spin {
  to { transform: rotate(360deg); }
}
.infer-model-row {
  display: flex;
  gap: 14px;
  justify-content: center;
  flex-wrap: wrap;
}
.infer-model-option {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-family: var(--font-mono);
  color: rgba(255, 255, 255, 0.75);
  cursor: pointer;
  user-select: none;
}
.infer-model-option.disabled {
  opacity: 0.4;
  cursor: default;
}
.infer-model-option input[type="radio"] {
  margin: 0;
  accent-color: rgba(52, 211, 153, 0.9);
  cursor: inherit;
}
.infer-model-option.disabled input[type="radio"] {
  cursor: default;
}
.infer-config {
  display: flex;
  gap: 0.5em;
  align-items: baseline;
  justify-content: flex-start;
  font-size: 11px; /* @claude Match the VLM status badge. */
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
.infer-answer {
  margin-top: 0.4em;
  padding-top: 0.4em;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  color: rgba(255, 255, 255, 0.95);
}
.infer-meta {
  font-size: 11px; /* @claude Match the VLM status badge. */
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
