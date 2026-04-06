<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { authFetch } from '../composables/useFetch.js'
import { useTheme } from '../composables/useTheme.js'
import ThemeToggle from '../components/ThemeToggle.vue'

const router = useRouter()
const { theme } = useTheme()
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const error = ref('')
const loading = ref(false)

async function handleChange() {
  error.value = ''

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
    router.push({ name: 'dashboard' })
  } catch {
    error.value = '서버 연결에 실패했습니다.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="cp-page">
    <ThemeToggle class="theme-toggle-fixed" />
    <form class="cp-form" @submit.prevent="handleChange" novalidate>
      <img :src="theme === 'dark' ? '/banner-dark-theme.png' : '/banner-light-theme.png'" alt="Babycat" class="cp-banner" />

      <input
        v-model="currentPassword"
        type="password"
        placeholder="현재 비밀번호"
        class="cp-input"
        autocomplete="current-password"
      />
      <input
        v-model="newPassword"
        type="password"
        placeholder="새 비밀번호"
        class="cp-input"
        autocomplete="new-password"
      />
      <input
        v-model="confirmPassword"
        type="password"
        placeholder="새 비밀번호 확인"
        class="cp-input"
        autocomplete="new-password"
      />

      <button type="submit" class="cp-btn" :disabled="loading">
        {{ loading ? '변경 중...' : '비밀번호 변경' }}
      </button>

      <p v-if="error" class="cp-error">{{ error }}</p>
    </form>
  </div>
</template>

<style scoped>
.cp-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-surface);
  padding: 1.5rem;
}

.cp-form {
  width: min(90%, 25rem);
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.cp-banner {
  display: block;
  width: 100%;
  height: auto;
  margin-bottom: 0.75rem;
}

.cp-notice {
  font-size: 0.85rem;
  color: var(--warning);
  font-weight: 600;
  text-align: center;
}

.cp-input {
  width: 100%;
  padding: 0.65rem 0.75rem;
  font-size: 0.85rem;
  border: 1px solid var(--border-input);
  border-radius: var(--radius);
  background: var(--input-bg);
  color: var(--text-1);
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.cp-input::placeholder {
  color: var(--text-4);
}
.cp-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-shadow);
}

.cp-btn {
  width: 100%;
  padding: 0.65rem;
  font-size: 0.9rem;
  font-weight: 700;
  background: var(--text-1);
  color: var(--bg-surface);
  border: none;
  border-radius: var(--radius);
  cursor: pointer;
  transition: opacity 0.15s;
}
.cp-btn:hover {
  opacity: 0.85;
}
.cp-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.cp-error {
  text-align: center;
  font-size: 0.8rem;
  color: var(--danger);
}

.theme-toggle-fixed {
  position: fixed;
  top: 1rem;
  right: 1rem;
  z-index: 10;
}
</style>
