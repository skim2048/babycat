<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth.js'
import { useLocale } from '../composables/useLocale.js'
import { getEditableBabycatHost, applyBabycatHost } from '../endpoints.js'

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
    <form class="login-card" @submit.prevent="handleLogin" novalidate>
      <div class="login-head">
        <h1 class="login-title">{{ t('login.title') }}</h1>
        <p class="login-sub">{{ t('login.subtitle') }}</p>
      </div>

      <div v-if="error || noticeKey" class="form-note login-notice">
        <i class="ph ph-warning-circle"></i>
        <span>{{ error || t(noticeKey) }}</span>
      </div>

      <div class="login-fields">
        <label class="form-field on-bg">{{ t('login.usernamePlaceholder') }}
          <input v-model="username" type="text" autocomplete="username" required />
        </label>
        <label class="form-field on-bg">{{ t('login.passwordPlaceholder') }}
          <input v-model="password" type="password" autocomplete="current-password" required />
        </label>
        <label class="form-field on-bg">{{ t('login.backendHostPlaceholder') }}
          <input v-model="babycatHost" type="text" autocomplete="off" spellcheck="false" @change="normalizeHostField" />
        </label>
        <button type="button" class="login-remember" @click="rememberMe = !rememberMe">
          <span class="login-check" :class="{ on: rememberMe }"><i v-if="rememberMe" class="ph-fill ph-check"></i></span>
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
.login-title {
  font-size: 30px;
  font-weight: 700;
  letter-spacing: -0.01em;
  margin-top: 10px;
  line-height: 1.2;
}
.login-sub {
  font-size: 15px;
  color: var(--color-neutral-400);
  line-height: 1.5;
  text-wrap: pretty;
}

.login-notice {
  font-size: 14px;
  line-height: 1.45;
}

.login-fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.login-remember {
  display: flex;
  align-items: center;
  gap: 9px;
  height: 40px;
  background: none;
  border: none;
  padding: 0;
  color: var(--color-neutral-300);
  font-size: 14.5px;
  font-family: inherit;
  cursor: pointer;
}
.login-check {
  width: 18px; height: 18px;
  border-radius: 5px;
  border: 1px solid var(--color-neutral-700);
  display: flex; align-items: center; justify-content: center;
  font-size: 13.5px;
  color: var(--color-accent);
}
.login-check.on {
  background: color-mix(in srgb, var(--color-accent) 20%, transparent);
  border-color: var(--color-accent);
}

.login-submit {
  height: 48px;
  border-radius: 8px;
  border: none;
  background: color-mix(in srgb, var(--color-accent) 28%, transparent);
  color: var(--color-text);
  font-size: 15.5px;
  font-weight: 700;
  font-family: inherit;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  gap: 8px;
  transition: background 0.15s;
}
.login-submit:hover:not(:disabled) { background: color-mix(in srgb, var(--color-accent) 42%, transparent); }
.login-submit:disabled { opacity: 0.5; cursor: default; }
</style>
