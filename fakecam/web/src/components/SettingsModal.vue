<script setup>
import { computed, reactive, watch } from 'vue'
import { state } from '../state.js'
import { api } from '../api.js'
import { useLocale } from '../composables/useLocale.js'

const { t } = useLocale()

const emit = defineEmits(['close'])

const RESOLUTIONS = ['360p', '720p', '1080p']
const FPS_CHOICES = [10, 15, 20, 25, 30, 60]
const BITRATE_CHOICES = [1, 2, 4, 8]

const draft = reactive({
  auth_user: '',
  auth_password: '',
  port: 554,
  rtsp_path_body: 'live',
  resolution: '720p',
  fps: 30,
  bitrate_mbps: 2,
  audio: 'drop',
})

const playing = computed(() => state.playlist?.is_playing === true)
const disabled = computed(() => playing.value)

function hydrateFromState() {
  if (!state.settings) return
  const { rtsp_path, ...rest } = state.settings
  Object.assign(draft, rest)
  draft.rtsp_path_body = (rtsp_path || '').replace(/^\//, '')
}

watch(() => state.settings, hydrateFromState, { immediate: true })

const showPassword = computed({
  get: () => state._showPasswordInModal === true,
  set: (v) => (state._showPasswordInModal = v),
})

const composedRtspPath = computed(() => '/' + draft.rtsp_path_body)

const dirty = computed(() => {
  if (!state.settings) return false
  if (composedRtspPath.value !== state.settings.rtsp_path) return true
  return ['auth_user', 'auth_password', 'port', 'resolution', 'fps', 'bitrate_mbps', 'audio']
    .some((k) => draft[k] !== state.settings[k])
})

const portValid = computed(() => {
  const n = Number(draft.port)
  return Number.isInteger(n) && n >= 1 && n <= 65535
})
const pathValid = computed(() =>
  /^\/[A-Za-z0-9_\-/]*$/.test(composedRtspPath.value),
)
const userValid = computed(() => draft.auth_user.length >= 1 && draft.auth_user.length <= 64)
const passwordValid = computed(() => draft.auth_password.length >= 1 && draft.auth_password.length <= 128)

const canSave = computed(
  () =>
    !disabled.value &&
    dirty.value &&
    portValid.value &&
    pathValid.value &&
    userValid.value &&
    passwordValid.value,
)

const errorMessage = computed(() => {
  if (!portValid.value) return t('settings.errPort')
  if (!pathValid.value) return t('settings.errPath')
  if (!userValid.value) return t('settings.errUser')
  if (!passwordValid.value) return t('settings.errPass')
  return state._settingsError ?? ''
})

async function onSave() {
  if (!canSave.value) return
  state._settingsError = ''
  try {
    await api.updateSettings({
      auth_user: draft.auth_user,
      auth_password: draft.auth_password,
      port: Number(draft.port),
      rtsp_path: composedRtspPath.value,
      resolution: draft.resolution,
      fps: Number(draft.fps),
      bitrate_mbps: Number(draft.bitrate_mbps),
      audio: draft.audio,
    })
    emit('close')
  } catch (e) {
    state._settingsError = String(e)
  }
}

function onReset() {
  hydrateFromState()
  state._settingsError = ''
}

function onBackdropClick(e) {
  if (e.target === e.currentTarget) emit('close')
}
</script>

<template>
  <div class="backdrop" @click="onBackdropClick">
    <div class="modal" role="dialog" aria-modal="true" :aria-label="t('settings.aria')">
      <header class="modal-header">
        <h2>{{ t('settings.title') }}</h2>
        <button class="close" :aria-label="t('settings.close')" @click="emit('close')">✕</button>
      </header>

      <div v-if="disabled" class="banner">
        {{ t('settings.banner') }}
      </div>

      <div class="body">
        <div class="field">
          <label>{{ t('settings.user') }}</label>
          <input
            v-model="draft.auth_user"
            type="text"
            :disabled="disabled"
            :class="{ invalid: !userValid }"
          />
        </div>
        <div class="field">
          <label>{{ t('settings.password') }}</label>
          <div class="password-row">
            <input
              v-model="draft.auth_password"
              :type="showPassword ? 'text' : 'password'"
              :disabled="disabled"
              :class="{ invalid: !passwordValid }"
            />
            <button
              type="button"
              class="ghost tiny"
              @click="showPassword = !showPassword"
            >{{ showPassword ? t('dashboard.hide') : t('dashboard.show') }}</button>
          </div>
        </div>
        <div class="field">
          <label>{{ t('settings.port') }}</label>
          <input
            v-model.number="draft.port"
            type="number"
            min="1"
            max="65535"
            :disabled="disabled"
            :class="{ invalid: !portValid }"
          />
        </div>
        <div class="field">
          <label>{{ t('settings.path') }}</label>
          <div class="path-row" :class="{ invalid: !pathValid, disabled }">
            <span class="path-prefix">/</span>
            <input
              v-model="draft.rtsp_path_body"
              type="text"
              placeholder="live"
              :disabled="disabled"
            />
          </div>
        </div>
        <div class="field">
          <label>{{ t('settings.resolution') }}</label>
          <select v-model="draft.resolution" :disabled="disabled">
            <option v-for="r in RESOLUTIONS" :key="r" :value="r">{{ r }}</option>
          </select>
        </div>
        <div class="field">
          <label>{{ t('settings.fps') }}</label>
          <select v-model.number="draft.fps" :disabled="disabled">
            <option v-for="f in FPS_CHOICES" :key="f" :value="f">{{ f }} {{ t('params.fpsUnit') }}</option>
          </select>
        </div>
        <div class="field">
          <label>{{ t('settings.bitrate') }}</label>
          <select v-model.number="draft.bitrate_mbps" :disabled="disabled">
            <option v-for="b in BITRATE_CHOICES" :key="b" :value="b">{{ b }} {{ t('params.mbps') }}</option>
          </select>
        </div>
        <div class="field">
          <label>{{ t('settings.audio') }}</label>
          <select v-model="draft.audio" :disabled="disabled">
            <option value="drop">{{ t('settings.audioDrop') }}</option>
            <option value="keep">{{ t('settings.audioKeep') }}</option>
          </select>
        </div>
      </div>

      <div v-if="errorMessage" class="error">{{ errorMessage }}</div>

      <footer class="modal-footer">
        <button class="ghost" :disabled="!dirty" @click="onReset">{{ t('settings.reset') }}</button>
        <button class="primary" :disabled="!canSave" @click="onSave">{{ t('settings.save') }}</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background: var(--backdrop);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.modal {
  width: min(560px, calc(100vw - 32px));
  max-height: calc(100vh - 64px);
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
.modal-header h2 { margin: 0; font-size: 12px; }
.close {
  background: transparent;
  border: none;
  font-size: 12px;
  color: var(--text-3);
  padding: 4px 8px;
}
.close:hover { color: var(--text-1); background: var(--bg-hover); }

.banner {
  background: var(--warning-bg);
  color: var(--warning-text);
  padding: 8px 16px;
  font-size: 12px;
  border-bottom: 1px solid var(--border);
}

.body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: repeat(4, auto);
  grid-auto-flow: column;
  gap: 12px 16px;
  padding: 16px;
  overflow: auto;
}
.field { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.field label { font-size: 12px; color: var(--text-3); }
.field input,
.field select {
  background: var(--bg-page);
  color: var(--text-1);
  border: 1px solid var(--border-input);
  border-radius: 4px;
  padding: 6px 8px;
  font-size: 12px;
  font-family: var(--font-ui);
}
.field input:focus,
.field select:focus { outline: none; border-color: var(--accent); }
.field input.invalid { border-color: var(--danger); }
.field input:disabled,
.field select:disabled { opacity: 0.5; cursor: default; }

.password-row { display: flex; gap: 6px; }
.password-row input { flex: 1; min-width: 0; }

.path-row {
  display: flex;
  align-items: stretch;
  background: var(--bg-page);
  border: 1px solid var(--border-input);
  border-radius: 4px;
  overflow: hidden;
}
.path-row:focus-within { border-color: var(--accent); }
.path-row.invalid { border-color: var(--danger); }
.path-row.disabled { opacity: 0.5; }
.path-prefix {
  display: inline-flex;
  align-items: center;
  padding: 0 8px;
  color: var(--text-3);
  background: var(--bg-hover);
  font-family: var(--font-ui);
  font-size: 12px;
  border-right: 1px solid var(--border);
}
.path-row input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 6px 8px;
  color: var(--text-1);
  font-size: 12px;
}
.path-row input:focus { outline: none; }

.ghost {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-2);
  padding: 6px 12px;
  font-size: 12px;
}
.ghost:hover:not(:disabled) { background: var(--bg-hover); }
.ghost.tiny { padding: 4px 10px; font-size: 12px; }

.error {
  color: var(--danger);
  font-size: 12px;
  padding: 8px 16px;
  border-top: 1px solid var(--border);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
}
.primary {
  background: var(--primary-bg);
  color: var(--accent);
  border: 1px solid var(--primary-border);
  padding: 6px 16px;
}
.primary:hover:not(:disabled) { background: var(--primary-bg-hover); }
</style>
