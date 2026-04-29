<script setup>
import { ref, watch } from 'vue'
import { useSSE } from '../composables/useSSE.js'
import { authFetch } from '../composables/useFetch.js'
import { APP_ENDPOINTS } from '../endpoints.js'
import { useLocale } from '../composables/useLocale.js'

const emit = defineEmits(['close'])

const { state } = useSSE()
const { t } = useLocale()

const prompt = ref('')
const triggers = ref('')
const status = ref('')
let loaded = false

watch(
  () => [state.inference_prompt, state.trigger_keywords],
  ([p, t]) => {
    if (!loaded && (p || t)) {
      if (p) prompt.value = p
      if (t) triggers.value = t
      loaded = true
    }
  },
  { immediate: true },
)

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
      status.value = t('prompt.status.applied')
      setTimeout(() => { status.value = '' }, 2000)
    } else {
      status.value = t('prompt.status.error', { message: data.error || t('prompt.status.unknown') })
    }
  } catch {
    status.value = t('prompt.status.failed')
  }
}
</script>

<template>
  <div class="prompt-form">
    <label class="prompt-label">{{ t('prompt.label.query') }}</label>
    <p class="prompt-hint">{{ t('prompt.hint.query') }}</p>
    <textarea
      class="prompt-input"
      v-model="prompt"
      :placeholder="t('prompt.placeholder.query')"
      rows="3"
    />

    <label class="prompt-label">{{ t('prompt.label.triggers') }}</label>
    <p class="prompt-hint">{{ t('prompt.hint.triggers') }}</p>
    <div class="triggers-field">
      <input
        class="prompt-input"
        v-model="triggers"
        :placeholder="t('prompt.placeholder.triggers')"
      />
      <button
        type="button"
        class="triggers-clear"
        :disabled="!triggers"
        @click="triggers = ''"
        :aria-label="t('prompt.action.clear')"
        :title="t('prompt.action.clear')"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="2,4 14,4" />
          <path d="M5 4 V2.5 Q5 2 5.5 2 H10.5 Q11 2 11 2.5 V4" />
          <path d="M3.5 4 L4.5 14 Q4.5 14.5 5 14.5 H11 Q11.5 14.5 11.5 14 L12.5 4" />
          <line x1="6.5" y1="7" x2="6.5" y2="12" />
          <line x1="9.5" y1="7" x2="9.5" y2="12" />
        </svg>
      </button>
    </div>

    <div class="prompt-actions">
      <span class="prompt-status">{{ status }}</span>
      <button class="btn-cancel" @click="emit('close')">{{ t('prompt.action.close') }}</button>
      <button class="btn-apply" @click="apply">{{ t('prompt.action.apply') }}</button>
    </div>
  </div>
</template>

<style scoped>
.prompt-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.prompt-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-2);
}
.prompt-input {
  width: 100%;
  font-family: var(--font-mono);
  font-size: 13px;
  padding: 8px 12px;
  border: 1px solid var(--border-input);
  border-radius: var(--radius);
  outline: none;
  background: var(--input-bg);
  color: var(--text-1);
  transition: border-color 0.15s, box-shadow 0.15s;
  resize: vertical;
}
.prompt-input::placeholder {
  color: var(--text-4);
}
.prompt-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-shadow);
}
.prompt-hint {
  margin: -4px 0 0;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-4);
  font-weight: 400;
}

.triggers-field {
  display: flex;
  gap: 6px;
  align-items: center;
}
.triggers-field .prompt-input {
  flex: 1;
}
.triggers-clear {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  border: 1px solid var(--border-input);
  border-radius: var(--radius);
  background: var(--bg-surface);
  color: var(--text-3);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.triggers-clear:hover:not(:disabled) {
  background: var(--danger-bg);
  border-color: var(--danger-border);
  color: var(--danger);
}
.triggers-clear:disabled {
  opacity: 0.4;
  cursor: default;
}

.prompt-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}
.prompt-status {
  flex: 1;
  font-size: 12px;
  color: var(--success);
  font-weight: 500;
}
.btn-cancel {
  padding: 7px 16px;
  font-size: 13px;
  font-weight: 600;
  border: 1px solid var(--border-input);
  border-radius: var(--radius);
  background: var(--bg-surface);
  color: var(--text-2);
  cursor: pointer;
  transition: background 0.15s;
}
.btn-cancel:hover {
  background: var(--bg-surface-hover);
}
.btn-apply {
  padding: 7px 16px;
  font-size: 13px;
  font-weight: 600;
  border: 1px solid var(--success-border);
  border-radius: var(--radius);
  background: var(--success-bg);
  color: var(--success);
  cursor: pointer;
  transition: background 0.15s;
}
.btn-apply:hover {
  background: var(--success-hover);
}
</style>
