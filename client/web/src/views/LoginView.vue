<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth.js'
import { useLocale } from '../composables/useLocale.js'
import { getEditableBabycatHost, applyBabycatHost } from '../endpoints.js'
import ThemeToggle from '../components/ThemeToggle.vue'

const router = useRouter()
const { login, consumeLogoutNotice } = useAuth()
const { t } = useLocale()

const username = ref('')
const password = ref('')
const babycatHost = ref(getEditableBabycatHost())
const rememberMe = ref(false)
const error = ref('')
const loading = ref(false)

// @claude Why the previous session ended (FR-047) — read once on arrival; the
// @claude key is kept so the template retranslates when the locale changes.
const logoutNotice = consumeLogoutNotice()
const noticeKey = logoutNotice === 'sessionReplaced' ? 'login.notice.sessionReplaced' : ''

// @claude Reflect the normalized host back into the field on blur; does not persist.
function normalizeHostField() {
  babycatHost.value = applyBabycatHost(babycatHost.value)
}

async function handleLogin() {
  error.value = ''
  applyBabycatHost(babycatHost.value)
  loading.value = true
  try {
    await login(username.value, password.value, rememberMe.value)
    router.push({ name: 'dashboard' })
  } catch (e) {
    if (e.message === 'host unreachable') {
      error.value = t('login.error.hostUnreachable')
    } else if (e.message.startsWith('too many attempts')) {
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
    <form class="login-card" @submit.prevent="handleLogin" novalidate>
      <div class="login-head">
        <div class="login-mark"><i class="ph ph-cat"></i></div>
        <h1 class="login-title">{{ t('login.title') }}</h1>
        <p class="login-sub">{{ t('login.subtitle') }}</p>
      </div>

      <div v-if="error || noticeKey" class="login-notice">
        <i class="ph ph-warning-circle"></i>
        <span>{{ error || t(noticeKey) }}</span>
      </div>

      <div class="login-fields">
        <label class="login-field">{{ t('login.usernamePlaceholder') }}
          <input v-model="username" type="text" autocomplete="username" required />
        </label>
        <label class="login-field">{{ t('login.passwordPlaceholder') }}
          <input v-model="password" type="password" autocomplete="current-password" required />
        </label>
        <label class="login-field">{{ t('login.backendHostPlaceholder') }}
          <input v-model="babycatHost" type="text" autocomplete="off" spellcheck="false" @change="normalizeHostField" />
        </label>
        <button type="button" class="login-remember" @click="rememberMe = !rememberMe">
          <span class="login-check" :class="{ on: rememberMe }"><i v-if="rememberMe" class="ph ph-check"></i></span>
          {{ t('login.rememberMe') }}
        </button>
      </div>

      <button type="submit" class="login-submit" :disabled="loading">
        {{ loading ? t('login.loading') : t('login.submit') }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg);
  padding: 40px;
}

.login-card {
  width: min(100%, 420px);
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.login-head {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.login-mark {
  width: 32px; height: 32px;
  border-radius: 8px;
  border: 1px solid var(--color-accent);
  display: flex; align-items: center; justify-content: center;
  color: var(--color-accent);
  font-size: 18px;
}
.login-title {
  font-size: 30px;
  font-weight: var(--font-heading-weight);
  letter-spacing: -0.01em;
  margin-top: 10px;
  line-height: 1.2;
}
.login-sub {
  font-size: 13.5px;
  color: var(--color-neutral-500);
  line-height: 1.5;
  text-wrap: pretty;
}

.login-notice {
  display: flex;
  gap: 9px;
  padding: 12px 13px;
  border-radius: 8px;
  background: var(--color-neutral-900);
  border-left: 2px solid var(--color-accent);
  font-size: 12.5px;
  line-height: 1.45;
  color: var(--color-neutral-300);
  align-items: flex-start;
}
.login-notice i {
  color: var(--color-accent);
  font-size: 16px;
  flex: none;
  margin-top: 1px;
}

.login-fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.login-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 11.5px;
  color: var(--color-neutral-500);
}
.login-field input {
  height: 44px;
  border-radius: 8px;
  border: 1px solid var(--color-neutral-800);
  background: transparent;
  color: var(--color-text);
  padding: 0 12px;
  font-size: 14px;
  font-family: inherit;
  outline: none;
  caret-color: var(--color-accent);
}
.login-field input:hover { border-color: var(--color-neutral-700); }
.login-field input:focus-visible { border-color: var(--color-accent); outline: none; }

.login-remember {
  display: flex;
  align-items: center;
  gap: 9px;
  height: 40px;
  background: none;
  border: none;
  padding: 0;
  color: var(--color-neutral-400);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
}
.login-check {
  width: 18px; height: 18px;
  border-radius: 5px;
  border: 1px solid var(--color-neutral-700);
  display: flex; align-items: center; justify-content: center;
  font-size: 12px;
  color: var(--color-accent);
}
.login-check.on { background: var(--color-accent-900); border-color: var(--color-accent); }

.login-submit {
  height: 48px;
  border-radius: 8px;
  border: 1px solid var(--color-accent);
  background: transparent;
  color: var(--color-accent);
  font-size: 14px;
  font-weight: var(--font-heading-weight);
  font-family: inherit;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  gap: 8px;
}
.login-submit:hover { background: color-mix(in srgb, var(--color-accent) 12%, transparent); }
.login-submit:active { background: color-mix(in srgb, var(--color-accent) 22%, transparent); }
.login-submit:disabled { opacity: 0.55; cursor: default; }

.theme-toggle-fixed {
  position: fixed;
  top: 1rem;
  right: 1rem;
  z-index: 10;
}
</style>
