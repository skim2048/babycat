<script setup>
import { onMounted } from 'vue'
import { useCamera } from '../composables/useCamera.js'

const { config, configured, connecting, connected, status, load, save, disconnect } = useCamera()

onMounted(load)
</script>

<template>
  <div class="section">
    <div class="section-title">
      Camera
      <span class="cam-badge" :class="connected ? 'on' : connecting ? 'pending' : 'off'">
        {{ connected ? 'Connected' : connecting ? 'Connecting...' : 'Disconnected' }}
      </span>
    </div>
    <div class="section-body">
      <div class="cam-form">
        <label class="cam-label">
          <span class="cam-label-text">Name (alias)</span>
          <input class="cam-input" v-model="config.name" placeholder="mycam" />
        </label>
        <label class="cam-label">
          <span class="cam-label-text">IP or Hostname</span>
          <input class="cam-input" v-model="config.ip" placeholder="192.168.1.101" />
        </label>
        <label class="cam-label">
          <span class="cam-label-text">RTSP Port</span>
          <input class="cam-input" v-model.number="config.rtsp_port" type="number" />
        </label>
        <label class="cam-label">
          <span class="cam-label-text">Camera ID</span>
          <input class="cam-input" v-model="config.username" placeholder="admin" />
        </label>
        <label class="cam-label">
          <span class="cam-label-text">Camera Password</span>
          <input class="cam-input" v-model="config.password" type="password" />
        </label>
        <label class="cam-label">
          <span class="cam-label-text">URL (path)</span>
          <input class="cam-input" v-model="config.stream_path" placeholder="stream1" />
        </label>
        <label class="cam-label">
          <span class="cam-label-text">ONVIF Port (optional)</span>
          <input class="cam-input" v-model.number="config.onvif_port" type="number"
                 placeholder="2020" />
        </label>
      </div>
      <button v-if="!configured && !connecting" class="cam-apply-btn" @click="save">Connect</button>
      <button v-else-if="connecting" class="cam-apply-btn cancel" @click="disconnect">Cancel</button>
      <button v-else class="cam-apply-btn disconnect" @click="disconnect">Disconnect</button>
      <div class="cam-status" v-if="status">{{ status }}</div>
    </div>
  </div>
</template>

<style scoped>
.cam-badge {
  font-size: 9px;
  padding: 2px 7px;
  border-radius: 10px;
  font-weight: 600;
  letter-spacing: 0.02em;
  margin-left: auto;
  text-transform: none;
}
.cam-badge.on {
  background: var(--success-bg);
  color: var(--success);
  border: 1px solid var(--success-border);
}
.cam-badge.off {
  background: var(--danger-bg);
  color: var(--danger);
}
.cam-badge.pending {
  background: var(--warning-bg);
  color: var(--warning);
}
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
  font-size: 10px;
  font-weight: 600;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.cam-input {
  width: 100%;
  min-width: 0;
  font-family: var(--font-mono);
  font-size: 12px;
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
.cam-apply-btn {
  margin-top: 10px;
  width: 100%;
  padding: 8px;
  font-size: 12px;
  font-weight: 600;
  border: 1px solid var(--accent);
  background: var(--accent-bg);
  color: var(--accent);
  border-radius: var(--radius);
  cursor: pointer;
  transition: background 0.15s, box-shadow 0.15s;
}
.cam-apply-btn:hover {
  box-shadow: 0 0 0 3px var(--accent-shadow);
}
.cam-apply-btn:active {
  transform: translateY(1px);
}
.cam-apply-btn.cancel {
  border-color: var(--warning);
  background: var(--warning-bg);
  color: var(--warning);
}
.cam-apply-btn.cancel:hover {
  box-shadow: 0 0 0 3px rgba(160, 122, 0, 0.2);
}
.cam-apply-btn.disconnect {
  border-color: var(--danger-border);
  background: var(--danger-bg);
  color: var(--danger);
}
.cam-apply-btn.disconnect:hover {
  box-shadow: 0 0 0 3px rgba(208, 56, 56, 0.2);
}
.cam-status {
  font-size: 11px;
  color: var(--text-4);
  text-align: center;
  margin-top: 6px;
  font-weight: 500;
}
</style>
