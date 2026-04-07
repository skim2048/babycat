<script setup>
import { ref } from 'vue'
import { authFetch } from '../composables/useFetch.js'

const emit = defineEmits(['close'])

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const error = ref('')
const success = ref('')
const loading = ref(false)
const showCurrent = ref(false)
const showNew = ref(false)
const showConfirm = ref(false)

async function handleChange() {
  error.value = ''
  success.value = ''

  if (currentPassword.value === newPassword.value) {
    error.value = '현재 비밀번호와 다른 비밀번호를 입력하세요.'
    return
  }
  if (newPassword.value.length < 4) {
    error.value = '새 비밀번호는 4자 이상이어야 합니다.'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    error.value = '새 비밀번호가 일치하지 않습니다.'
    return
  }

  loading.value = true
  try {
    const res = await authFetch('/api/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        current_password: currentPassword.value,
        new_password: newPassword.value,
      }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      error.value = body.detail || '비밀번호 변경에 실패했습니다.'
      return
    }
    success.value = '비밀번호가 변경되었습니다.'
    currentPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
  } catch {
    error.value = '서버 연결에 실패했습니다.'
  } finally {
    loading.value = false
  }
}

function handleCancel() {
  emit('close')
}
</script>

<template>
  <div class="cp-panel">
    <div class="cp-form">
      <label class="cp-label">
        <span class="cp-label-text">현재 비밀번호</span>
        <div class="pw-field">
          <input class="cp-input pw-input" v-model="currentPassword"
                 :type="showCurrent ? 'text' : 'password'" autocomplete="current-password" />
          <button type="button" class="pw-toggle" @click="showCurrent = !showCurrent" tabindex="-1">
            <svg v-if="showCurrent" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
          </button>
        </div>
      </label>
      <label class="cp-label">
        <span class="cp-label-text">새 비밀번호</span>
        <div class="pw-field">
          <input class="cp-input pw-input" v-model="newPassword"
                 :type="showNew ? 'text' : 'password'" autocomplete="new-password" />
          <button type="button" class="pw-toggle" @click="showNew = !showNew" tabindex="-1">
            <svg v-if="showNew" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
          </button>
        </div>
      </label>
      <label class="cp-label">
        <span class="cp-label-text">새 비밀번호 확인</span>
        <div class="pw-field">
          <input class="cp-input pw-input" v-model="confirmPassword"
                 :type="showConfirm ? 'text' : 'password'" autocomplete="new-password" />
          <button type="button" class="pw-toggle" @click="showConfirm = !showConfirm" tabindex="-1">
            <svg v-if="showConfirm" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
          </button>
        </div>
      </label>
    </div>
    <div class="cp-actions">
      <button class="cp-btn save" @click="handleChange" :disabled="loading">
        {{ loading ? '변경 중...' : '변경' }}
      </button>
      <button class="cp-btn cancel" @click="handleCancel">취소</button>
    </div>
    <p v-if="error" class="cp-msg error">{{ error }}</p>
    <p v-if="success" class="cp-msg success">{{ success }}</p>
  </div>
</template>

<style scoped>
.cp-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cp-label {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.cp-label-text {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.cp-input {
  width: 100%;
  min-width: 0;
  font-size: 13px;
  padding: 7px 10px;
  border: 1px solid var(--border-input);
  border-radius: var(--radius);
  outline: none;
  background: var(--input-bg);
  color: var(--text-1);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.cp-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-shadow);
}
.pw-field {
  position: relative;
  display: flex;
  align-items: center;
}
.pw-input {
  padding-right: 34px;
}
.pw-toggle {
  position: absolute;
  right: 6px;
  background: none;
  border: none;
  padding: 4px;
  cursor: pointer;
  color: var(--text-3);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: color 0.15s;
}
.pw-toggle:hover {
  color: var(--text-1);
}
.cp-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.cp-btn {
  flex: 1;
  padding: 8px;
  font-size: 13px;
  font-weight: 600;
  border-radius: var(--radius);
  cursor: pointer;
  transition: background 0.15s, box-shadow 0.15s;
}
.cp-btn:active {
  transform: translateY(1px);
}
.cp-btn.save {
  border: 1px solid var(--accent);
  background: var(--accent-bg);
  color: var(--accent);
}
.cp-btn.save:hover {
  box-shadow: 0 0 0 3px var(--accent-shadow);
}
.cp-btn.save:disabled {
  opacity: 0.5;
  cursor: default;
}
.cp-btn.cancel {
  border: 1px solid var(--border-input);
  background: var(--bg-surface);
  color: var(--text-2);
}
.cp-btn.cancel:hover {
  background: var(--bg-surface-hover);
}
.cp-msg {
  font-size: 11px;
  text-align: center;
  margin-top: 6px;
  font-weight: 500;
}
.cp-msg.error {
  color: var(--danger);
}
.cp-msg.success {
  color: var(--success);
}
</style>
