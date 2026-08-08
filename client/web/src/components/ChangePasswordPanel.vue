<script setup>
import { ref } from 'vue'
import { authFetch } from '../composables/useFetch.js'
import { API_ENDPOINTS } from '../endpoints.js'
import { useLocale } from '../composables/useLocale.js'

const emit = defineEmits(['close'])
// @claude Forced first-login mode (FR-006): no cancel until the change succeeds.
const props = defineProps({ forced: { type: Boolean, default: false } })

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const error = ref('')
const success = ref('')
const loading = ref(false)
const showCurrent = ref(false)
const showNew = ref(false)
const showConfirm = ref(false)
const { t } = useLocale()

async function handleChange() {
  error.value = ''
  success.value = ''

  if (currentPassword.value === newPassword.value) {
    error.value = t('changePassword.error.sameAsCurrent')
    return
  }
  if (newPassword.value.length < 4) {
    error.value = t('changePassword.error.minLength')
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    error.value = t('changePassword.error.mismatch')
    return
  }

  loading.value = true
  try {
    const res = await authFetch(API_ENDPOINTS.changePassword, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        current_password: currentPassword.value,
        new_password: newPassword.value,
      }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      error.value = body.detail || t('changePassword.error.requestFailed')
      return
    }
    success.value = t('changePassword.success')
    currentPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
  } catch {
    error.value = t('changePassword.error.network')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="form-col">
    <div v-if="props.forced" class="form-note warn">
      <i class="ph ph-info"></i><span>{{ t('changePassword.forcedNotice') }}</span>
    </div>
    <div v-if="error" class="form-note warn">
      <i class="ph ph-warning-circle"></i><span>{{ error }}</span>
    </div>
    <div v-if="success" class="form-note">
      <i class="ph ph-check-circle"></i><span>{{ success }}</span>
    </div>

    <label class="form-field">{{ t('changePassword.field.current') }}
      <span class="pw-wrap">
        <input v-model="currentPassword" :type="showCurrent ? 'text' : 'password'" autocomplete="current-password" />
        <button type="button" class="pw-toggle" tabindex="-1" @click="showCurrent = !showCurrent">
          <i :class="showCurrent ? 'ph ph-eye-slash' : 'ph ph-eye'"></i>
        </button>
      </span>
    </label>
    <label class="form-field">{{ t('changePassword.field.new') }}
      <span class="pw-wrap">
        <input v-model="newPassword" :type="showNew ? 'text' : 'password'" autocomplete="new-password" />
        <button type="button" class="pw-toggle" tabindex="-1" @click="showNew = !showNew">
          <i :class="showNew ? 'ph ph-eye-slash' : 'ph ph-eye'"></i>
        </button>
      </span>
    </label>
    <label class="form-field">{{ t('changePassword.field.confirm') }}
      <span class="pw-wrap">
        <input v-model="confirmPassword" :type="showConfirm ? 'text' : 'password'" autocomplete="new-password" />
        <button type="button" class="pw-toggle" tabindex="-1" @click="showConfirm = !showConfirm">
          <i :class="showConfirm ? 'ph ph-eye-slash' : 'ph ph-eye'"></i>
        </button>
      </span>
    </label>

    <div class="form-actions">
      <button class="form-btn primary" :disabled="loading" @click="handleChange">
        {{ loading ? t('changePassword.action.loading') : t('changePassword.action.submit') }}
      </button>
      <button v-if="!props.forced" class="form-btn" @click="emit('close')">{{ t('changePassword.action.cancel') }}</button>
    </div>
  </div>
</template>

<style scoped>
.pw-wrap {
  position: relative;
  display: flex;
  align-items: center;
}
.pw-wrap input { padding-right: 40px; }
.pw-toggle {
  position: absolute;
  right: 6px;
  width: 30px; height: 30px;
  border: none;
  background: none;
  color: var(--color-neutral-500);
  font-size: 16px;
  cursor: pointer;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.pw-toggle:hover { background: var(--color-neutral-900); color: var(--color-text); }
</style>
