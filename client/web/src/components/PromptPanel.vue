<script setup>
import { computed, ref, watch } from 'vue'
import { useSSE } from '../composables/useSSE.js'
import { useAnalysis } from '../composables/useAnalysis.js'
import { authFetch } from '../composables/useFetch.js'
import { APP_ENDPOINTS } from '../endpoints.js'
import { useLocale } from '../composables/useLocale.js'

const { state } = useSSE()
const { rejected, clearRejected } = useAnalysis()
const { t } = useLocale()

const prompt = ref('')
const triggers = ref('')
const savedPrompt = ref('')
const savedTriggers = ref('')
const savedNote = ref(false)
const errorNote = ref('')
let loaded = false

watch(
  () => [state.inference_prompt, state.trigger_keywords],
  ([promptText, triggerText]) => {
    if (!loaded && (promptText || triggerText)) {
      prompt.value = savedPrompt.value = promptText || ''
      triggers.value = savedTriggers.value = triggerText || ''
      loaded = true
    }
  },
  { immediate: true },
)

const dirty = computed(() =>
  prompt.value !== savedPrompt.value || triggers.value !== savedTriggers.value,
)

// @claude 저장 안내는 필드를 다시 편집하는 순간 사라진다.
watch([prompt, triggers], () => {
  savedNote.value = false
  errorNote.value = ''
})

async function apply() {
  if (!prompt.value.trim()) return
  errorNote.value = ''
  try {
    const res = await authFetch(APP_ENDPOINTS.prompt, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: prompt.value.trim(), triggers: triggers.value.trim() }),
    })
    if (res.ok) {
      savedPrompt.value = prompt.value
      savedTriggers.value = triggers.value
      savedNote.value = true
      clearRejected()
    } else {
      const body = await res.json().catch(() => ({}))
      errorNote.value = t('prompt.status.error', { message: body.detail || t('prompt.status.unknown') })
    }
  } catch {
    errorNote.value = t('prompt.status.failed')
  }
}

// @claude 취소는 마지막 저장 상태로 되돌린다.
function revert() {
  if (!dirty.value) return
  prompt.value = savedPrompt.value
  triggers.value = savedTriggers.value
}
</script>

<template>
  <div class="prompt-panel">
    <div v-if="savedNote" class="form-note">
      <i class="ph ph-info"></i><span>{{ t('prompt.status.applied') }}</span>
    </div>
    <div v-if="rejected" class="form-note warn">
      <i class="ph ph-info"></i><span>{{ t('prompt.status.needStreaming') }}</span>
    </div>
    <div v-if="errorNote" class="form-note warn">
      <i class="ph ph-info"></i><span>{{ errorNote }}</span>
    </div>

    <label class="form-field grow">{{ t('prompt.label.query') }}
      <textarea v-model="prompt" :placeholder="t('prompt.placeholder.query')" />
    </label>
    <label class="form-field grow">{{ t('prompt.label.triggers') }}
      <textarea v-model="triggers" :placeholder="t('prompt.placeholder.triggers')" />
    </label>

    <div class="form-actions">
      <button class="form-btn primary" @click="apply">{{ t('prompt.action.apply') }}</button>
      <button class="form-btn plain" :disabled="!dirty" @click="revert">{{ t('prompt.action.revert') }}</button>
    </div>
  </div>
</template>

<style scoped>
.prompt-panel {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.form-field.grow {
  flex: 1;
  min-height: 0;
}
.form-field.grow textarea {
  flex: 1;
  min-height: 0;
}
/* 패널은 neutral-900 위이므로 취소 버튼은 페이지 배경 채움을 쓴다 */
.form-btn.plain { background: var(--color-bg); }
.form-btn.plain:hover:not(:disabled) { background: color-mix(in srgb, var(--color-accent) 22%, transparent); }
</style>
