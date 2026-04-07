<script setup>
import { useCamera } from '../composables/useCamera.js'

const emit = defineEmits(['close'])
const { config, status, save } = useCamera()

async function handleSave() {
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
        <span class="cam-label-text">이름 (별칭)</span>
        <input class="cam-input" v-model="config.name" placeholder="mycam" />
      </label>
      <label class="cam-label">
        <span class="cam-label-text">카메라 ID</span>
        <input class="cam-input" v-model="config.username" placeholder="admin" />
      </label>
      <label class="cam-label">
        <span class="cam-label-text">카메라 비밀번호</span>
        <input class="cam-input" v-model="config.password" type="password" />
      </label>
      <label class="cam-label">
        <span class="cam-label-text">IP 또는 호스트명</span>
        <input class="cam-input" v-model="config.ip" placeholder="192.168.1.101" />
      </label>
      <label class="cam-label">
        <span class="cam-label-text">RTSP 포트 번호</span>
        <input class="cam-input" v-model.number="config.rtsp_port" type="number" />
      </label>
      <label class="cam-label">
        <span class="cam-label-text">ONVIF 포트 번호 (선택)</span>
        <input class="cam-input" v-model.number="config.onvif_port" type="number"
               placeholder="2020" />
      </label>
      <label class="cam-label">
        <span class="cam-label-text">URL (경로)</span>
        <input class="cam-input" v-model="config.stream_path" placeholder="stream1" />
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
