<script setup>
import { computed, ref, watch } from 'vue'
import { useSSE } from '../composables/useSSE.js'
import { authFetch } from '../composables/useFetch.js'
import { APP_ENDPOINTS } from '../endpoints.js'
import { useLocale } from '../composables/useLocale.js'

defineEmits(['close'])

const { state } = useSSE()
const { t } = useLocale()

const prompt = ref('')
const triggers = ref('')
const status = ref('')
const statusWarn = ref(false)
let loaded = false

watch(
  () => [state.inference_prompt, state.trigger_keywords],
  ([promptText, triggerText]) => {
    if (!loaded && (promptText || triggerText)) {
      if (promptText) prompt.value = promptText
      if (triggerText) triggers.value = triggerText
      loaded = true
    }
  },
  { immediate: true },
)

function setStatus(text, { warn = false, transient = false } = {}) {
  status.value = text
  statusWarn.value = warn
  if (transient) setTimeout(() => { status.value = '' }, 3000)
}

async function apply() {
  if (!prompt.value.trim()) return
  status.value = ''
  try {
    const res = await authFetch(APP_ENDPOINTS.prompt, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: prompt.value.trim(), triggers: triggers.value.trim() }),
    })
    const data = await res.json()
    if (data.ok) {
      setStatus(t('prompt.status.applied'), { transient: true })
    } else {
      setStatus(t('prompt.status.error', { message: data.error || t('prompt.status.unknown') }), { warn: true })
    }
  } catch {
    setStatus(t('prompt.status.failed'), { warn: true })
  }
}

// @claude FR-024/FR-025: saving settings never starts analysis; this explicit
// @claude action fans out to the analyzer and the recorder. FR-050: the router
// @claude rejects a start while live streaming is inactive.
const busy = ref(false)

// @claude idle means the pipeline waits for an explicit start (FR-024), so a
// @claude streaming pipeline that is not idle is an analysis in progress.
const analysisActive = computed(() => state.streaming_active && state.pipeline_state !== 'idle')

async function startAnalysis() {
  status.value = ''
  try {
    const res = await authFetch(APP_ENDPOINTS.analysisStart, { method: 'POST' })
    const data = await res.json()
    if (res.ok && data.ok) {
      setStatus(t('prompt.status.started'), { transient: true })
    } else if (res.status === 409) {
      setStatus(t('prompt.status.needStreaming'), { warn: true })
    } else {
      setStatus(t('prompt.status.error', { message: data.detail || t('prompt.status.unknown') }), { warn: true })
    }
  } catch {
    setStatus(t('prompt.status.startFailed'), { warn: true })
  }
}

// @claude FR-051: stop analysis and buffering while streaming stays up.
async function stopAnalysis() {
  status.value = ''
  try {
    const res = await authFetch(APP_ENDPOINTS.analysisStop, { method: 'POST' })
    const data = await res.json()
    if (res.ok && data.ok) {
      setStatus(t('prompt.status.stopped'), { transient: true })
    } else {
      setStatus(t('prompt.status.error', { message: data.detail || t('prompt.status.unknown') }), { warn: true })
    }
  } catch {
    setStatus(t('prompt.status.stopFailed'), { warn: true })
  }
}

async function toggleAnalysis() {
  if (busy.value) return
  busy.value = true
  try {
    if (analysisActive.value) await stopAnalysis()
    else await startAnalysis()
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="form-col">
    <div v-if="status" class="form-note" :class="{ warn: statusWarn }">
      <i class="ph ph-info"></i><span>{{ status }}</span>
    </div>

    <label class="form-field">{{ t('prompt.label.query') }}
      <textarea v-model="prompt" :placeholder="t('prompt.placeholder.query')" rows="4" />
    </label>
    <label class="form-field">{{ t('prompt.label.triggers') }}
      <input v-model="triggers" :placeholder="t('prompt.placeholder.triggers')" />
    </label>

    <div class="form-actions">
      <button class="form-btn primary" @click="apply">{{ t('prompt.action.apply') }}</button>
      <button class="form-btn" :disabled="busy" @click="toggleAnalysis">
        {{ analysisActive ? t('prompt.action.stop') : t('prompt.action.start') }}
      </button>
    </div>
  </div>
</template>
