<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth.js'
import { useTheme } from '../composables/useTheme.js'
import ThemeToggle from '../components/ThemeToggle.vue'

const router = useRouter()
const { login } = useAuth()
const { theme } = useTheme()

const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await login(username.value, password.value)
    router.push({ name: 'dashboard' })
  } catch (e) {
    if (e.message.startsWith('too many attempts')) {
      error.value = `로그인 시도가 너무 많습니다. ${e.message.replace('too many attempts, retry after ', '').replace('s', '초')} 후 다시 시도하세요.`
    } else {
      error.value = '아이디 또는 비밀번호가 올바르지 않습니다.'
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <ThemeToggle class="theme-toggle-fixed" />
    <form class="login-form" @submit.prevent="handleLogin" novalidate>
      <img :src="theme === 'dark' ? '/banner-dark-theme.png' : '/banner-light-theme.png'" alt="Babycat" class="login-banner" />

      <input
        v-model="username"
        type="text"
        placeholder="아이디"
        class="login-input"
        autocomplete="username"
        required
      />
      <input
        v-model="password"
        type="password"
        placeholder="비밀번호"
        class="login-input"
        autocomplete="current-password"
        required
      />

      <button type="submit" class="login-btn" :disabled="loading">
        {{ loading ? '로그인 중...' : '로그인' }}
      </button>

      <p v-if="error" class="login-error">{{ error }}</p>
    </form>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-surface);
  padding: 1.5rem;
}

.login-form {
  width: min(90%, 25rem);
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.login-banner {
  display: block;
  width: 100%;
  height: auto;
  margin-bottom: 0;
}

.login-input {
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
.login-input::placeholder {
  color: var(--text-4);
}
.login-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-shadow);
}

.login-btn {
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
.login-btn:hover {
  opacity: 0.85;
}
.login-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.login-error {
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
