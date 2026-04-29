<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth.js'
import { useLocale } from '../composables/useLocale.js'
import { useTheme } from '../composables/useTheme.js'
import ThemeToggle from '../components/ThemeToggle.vue'

const router = useRouter()
const { login } = useAuth()
const { t } = useLocale()
const { theme } = useTheme()

const username = ref('')
const password = ref('')
const rememberMe = ref(false)
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await login(username.value, password.value, rememberMe.value)
    router.push({ name: 'dashboard' })
  } catch (e) {
    if (e.message.startsWith('too many attempts')) {
      const seconds = e.message.replace('too many attempts, retry after ', '').replace('s', '')
      error.value = t('login.error.tooManyAttempts', { seconds })
    } else {
      error.value = t('login.error.invalidCredentials')
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
        :placeholder="t('login.usernamePlaceholder')"
        class="login-input"
        autocomplete="username"
        required
      />
      <input
        v-model="password"
        type="password"
        :placeholder="t('login.passwordPlaceholder')"
        class="login-input"
        autocomplete="current-password"
        required
      />

      <div class="login-options">
        <label class="login-remember">
          <input v-model="rememberMe" type="checkbox" />
          <span>{{ t('login.rememberMe') }}</span>
        </label>
        <a class="login-find" @click.prevent="error = t('login.error.unsupported')">{{ t('login.findAccount') }}</a>
      </div>

      <hr class="login-divider" />

      <button type="submit" class="login-btn" :disabled="loading">
        {{ loading ? t('login.loading') : t('login.submit') }}
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

.login-options {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0.5rem;
}
.login-remember {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.8rem;
  color: var(--text-2);
  cursor: pointer;
  user-select: none;
}
.login-find {
  font-size: 0.75rem;
  color: var(--text-3);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}
.login-find:hover {
  color: var(--text-1);
}
.login-remember input[type="checkbox"] {
  width: 1rem;
  height: 1rem;
  cursor: pointer;
}

.login-divider {
  border: none;
  border-top: 1px solid var(--border);
  margin: 0.25rem 0;
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
