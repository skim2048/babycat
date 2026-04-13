<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useCamera } from '../composables/useCamera.js'

const emit = defineEmits(['close'])
const { config, status, save } = useCamera()

// 로컬 복사본 — 취소 시 원본에 영향 없음
const local = reactive({
  ip: '',
  rtsp_port: 554,
  username: '',
  password: '',
  stream_path: 'stream1',
  onvif_port: null,
  stream_protocol: 'hls',
})

const showPassword = ref(false)
const passwordLoaded = ref(false)

onMounted(() => {
  Object.assign(local, {
    ip: config.ip,
    rtsp_port: config.rtsp_port,
    username: config.username,
    password: config.password,
    stream_path: config.stream_path,
    onvif_port: config.onvif_port,
    stream_protocol: config.stream_protocol,
  })
  if (config.password) {
    passwordLoaded.value = true
  }
})

function onPasswordFocus() {
  if (passwordLoaded.value) {
    local.password = ''
    passwordLoaded.value = false
  }
}

function togglePasswordVisibility() {
  if (!passwordLoaded.value) {
    showPassword.value = !showPassword.value
  }
}

async function handleSave() {
  // 로컬 → 공유 config에 반영 후 저장
  Object.assign(config, local)
  const ok = await save()
  if (ok) emit('close')
}

function handleCancel() {
  emit('close')
}
</script>

<template>
  <div class="cam-panel">
    <div class="cam-form">
      <label class="cam-label">
        <span class="cam-label-text">카메라 ID</span>
        <input class="cam-input" v-model="local.username" placeholder="admin" />
      </label>
      <label class="cam-label">
        <span class="cam-label-text">카메라 비밀번호</span>
        <div class="pw-field">
          <input class="cam-input pw-input" :class="{ 'pw-loaded': passwordLoaded }"
                 v-model="local.password"
                 :type="showPassword ? 'text' : 'password'"
                 @focus="onPasswordFocus" />
          <button type="button" class="pw-toggle"
                  :class="{ disabled: passwordLoaded }"
                  @click="togglePasswordVisibility"
                  tabindex="-1">
            <svg v-if="showPassword" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
              <circle cx="12" cy="12" r="3"/>
            </svg>
            <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
              <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
              <line x1="1" y1="1" x2="23" y2="23"/>
            </svg>
          </button>
        </div>
      </label>
      <label class="cam-label">
        <span class="cam-label-text">IP 또는 호스트명</span>
        <input class="cam-input" v-model="local.ip" placeholder="192.168.1.101" />
      </label>
      <label class="cam-label">
        <span class="cam-label-text">RTSP 포트 번호</span>
        <input class="cam-input" v-model.number="local.rtsp_port" type="number" />
      </label>
      <label class="cam-label">
        <span class="cam-label-text">ONVIF 포트 번호 (선택)</span>
        <input class="cam-input" v-model.number="local.onvif_port" type="number"
               placeholder="2020" />
      </label>
      <label class="cam-label">
        <span class="cam-label-text">URL (경로)</span>
        <input class="cam-input" v-model="local.stream_path" placeholder="stream1" />
      </label>
    </div>
    <div class="cam-actions">
      <button class="cam-btn save" @click="handleSave">저장</button>
      <button class="cam-btn cancel" @click="handleCancel">취소</button>
    </div>
    <div class="cam-status" v-if="status">{{ status }}</div>
  </div>
</template>

<style scoped>
.cam-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cam-label {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.cam-label-text {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.cam-input {
  width: 100%;
  min-width: 0;
  font-family: var(--font-mono);
  font-size: 13px;
  padding: 7px 10px;
  border: 1px solid var(--border-input);
  border-radius: var(--radius);
  outline: none;
  background: var(--input-bg);
  color: var(--text-1);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.cam-input::placeholder {
  color: var(--text-4);
}
.cam-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-shadow);
}
.cam-input[type="number"]::-webkit-inner-spin-button,
.cam-input[type="number"]::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
.cam-input[type="number"] {
  -moz-appearance: textfield;
}
.pw-loaded {
  color: var(--text-4);
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
.pw-toggle:hover:not(.disabled) {
  color: var(--text-1);
}
.pw-toggle.disabled {
  opacity: 0.3;
  cursor: default;
}
.cam-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.cam-btn {
  flex: 1;
  padding: 8px;
  font-size: 13px;
  font-weight: 600;
  border-radius: var(--radius);
  cursor: pointer;
  transition: background 0.15s, box-shadow 0.15s;
}
.cam-btn:active {
  transform: translateY(1px);
}
.cam-btn.save {
  border: 1px solid var(--accent);
  background: var(--accent-bg);
  color: var(--accent);
}
.cam-btn.save:hover {
  box-shadow: 0 0 0 3px var(--accent-shadow);
}
.cam-btn.cancel {
  border: 1px solid var(--border-input);
  background: var(--bg-surface);
  color: var(--text-2);
}
.cam-btn.cancel:hover {
  background: var(--bg-surface-hover);
}
.cam-status {
  font-size: 11px;
  color: var(--text-4);
  text-align: center;
  margin-top: 6px;
  font-weight: 500;
}
</style>
