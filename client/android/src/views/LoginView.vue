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
  <form class="login-page" @submit.prevent="handleLogin" novalidate>
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
        <span class="login-check" :class="{ on: rememberMe }"><svg v-if="rememberMe" class="check-glyph" viewBox="0 0 12 12" aria-hidden="true"><polyline points="2.5,6.5 5,9 9.5,3.5" /></svg></span>
        {{ t('login.rememberMe') }}
      </button>
    </div>

    <button type="submit" class="login-submit" :disabled="loading">
      {{ loading ? t('login.loading') : t('login.submit') }}
    </button>
  </form>
</template>

<style scoped>
.check-glyph {
  width: 11px;
  height: 11px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2.2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.login-page {
  min-height: 100vh;
  background: var(--color-bg);
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 56px 24px 40px;
  gap: 22px;
}

.login-head {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.login-title {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.01em;
  margin-top: 10px;
  line-height: 1.2;
}
.login-sub {
  font-size: 13.5px;
  color: var(--color-neutral-400);
  line-height: 1.5;
  text-wrap: pretty;
}

.login-notice {
  font-size: 13px;
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
  height: 44px;
  background: none;
  border: none;
  padding: 0;
  color: var(--color-neutral-300);
  font-size: 13.5px;
  font-family: inherit;
  cursor: pointer;
}
.login-check {
  width: 18px; height: 18px;
  border-radius: 5px;
  border: 1px solid var(--color-neutral-700);
  display: flex; align-items: center; justify-content: center;
  font-size: 13px;
  color: var(--color-accent);
}
.login-check.on {
  background: color-mix(in srgb, var(--color-accent) 20%, transparent);
  border-color: var(--color-accent);
}

/* 시안: 모바일 제출 버튼은 액센트 채움 알약 */
.login-submit {
  height: 56px;
  border-radius: 100px;
  border: none;
  background: var(--color-accent);
  color: #12131c;
  font-size: 16px;
  font-weight: 700;
  font-family: inherit;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  gap: 8px;
}
.login-submit:disabled { opacity: 0.5; cursor: default; }
</style>
