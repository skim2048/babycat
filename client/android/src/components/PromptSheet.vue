<script setup>
import { ref, watch } from 'vue'
import SheetFrame from './SheetFrame.vue'
import { useSSE } from '../composables/useSSE.js'
import { useAnalysis } from '../composables/useAnalysis.js'
import { authFetch } from '../composables/useFetch.js'
import { APP_ENDPOINTS } from '../endpoints.js'
import { useLocale } from '../composables/useLocale.js'

const emit = defineEmits(['close'])

const { state } = useSSE()
const { rejected, clearRejected } = useAnalysis()
const { t } = useLocale()

const prompt = ref('')
const triggers = ref('')
const savedPrompt = ref('')
const savedTriggers = ref('')
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

// @claude 시안: 저장은 시트를 닫고, 취소·닫기·배경 클릭은 마지막 저장
// @claude 상태로 되돌린 뒤 닫는다.
async function apply() {
  if (!prompt.value.trim()) return
  errorNote.value = ''
  try {
    const res = await authFetch(APP_ENDPOINTS.prompt, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: prompt.value.trim(), triggers: triggers.value.trim() }),
    })
    const data = await res.json()
    if (data.ok) {
      savedPrompt.value = prompt.value
      savedTriggers.value = triggers.value
      clearRejected()
      emit('close')
    } else {
      errorNote.value = t('prompt.status.error', { message: data.error || t('prompt.status.unknown') })
    }
  } catch {
    errorNote.value = t('prompt.status.failed')
  }
}

function revertAndClose() {
  prompt.value = savedPrompt.value
  triggers.value = savedTriggers.value
  clearRejected()
  emit('close')
}
</script>

<template>
  <SheetFrame :title="t('dashboard.panel.prompt')" @close="revertAndClose">
    <div class="form-col">
      <div v-if="rejected" class="form-note warn">
        <i class="ph ph-info"></i><span>{{ t('prompt.status.needStreaming') }}</span>
      </div>
      <div v-if="errorNote" class="form-note warn">
        <i class="ph ph-info"></i><span>{{ errorNote }}</span>
      </div>

      <label class="form-field">{{ t('prompt.label.query') }}
        <textarea v-model="prompt" :placeholder="t('prompt.placeholder.query')" rows="4" />
      </label>
      <label class="form-field">{{ t('prompt.label.triggers') }}
        <input v-model="triggers" :placeholder="t('prompt.placeholder.triggers')" />
      </label>

      <div class="form-actions">
        <button class="form-btn primary" @click="apply">{{ t('prompt.action.apply') }}</button>
        <button class="form-btn" @click="revertAndClose">{{ t('prompt.action.revert') }}</button>
      </div>
    </div>
  </SheetFrame>
</template>
