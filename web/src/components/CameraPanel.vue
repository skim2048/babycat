<script setup>
import { ref, onMounted } from 'vue'
import { useCamera } from '../composables/useCamera.js'

const { config, configured, status, load, save } = useCamera()
const collapsed = ref(false)

onMounted(load)
</script>

<template>
  <div class="section" :class="{ collapsed }">
    <div class="section-title" @click="collapsed = !collapsed">
      Camera
      <span class="cam-badge" :class="configured ? 'on' : 'off'">
        {{ configured ? 'Connected' : 'Not configured' }}
      </span>
      <span class="arrow">&#9660;</span>
    </div>
    <div class="section-body">
      <div class="cam-form">
        <label class="cam-label">
          <span class="cam-label-text">IP</span>
          <input class="cam-input" v-model="config.ip" placeholder="192.168.1.101" />
        </label>
        <div class="cam-row-2">
          <label class="cam-label">
            <span class="cam-label-text">RTSP Port</span>
            <input class="cam-input" v-model.number="config.rtsp_port" type="number" />
          </label>
          <label class="cam-label">
            <span class="cam-label-text">ONVIF Port</span>
            <input class="cam-input" v-model.number="config.onvif_port" type="number" />
          </label>
        </div>
        <label class="cam-label">
          <span class="cam-label-text">Username</span>
          <input class="cam-input" v-model="config.username" />
        </label>
        <label class="cam-label">
          <span class="cam-label-text">Password</span>
          <input class="cam-input" v-model="config.password" type="password" />
        </label>
        <label class="cam-label">
          <span class="cam-label-text">Stream Path</span>
          <input class="cam-input" v-model="config.stream_path" placeholder="stream1" />
        </label>
      </div>
      <button class="cam-apply-btn" @click="save">적용</button>
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
  margin-right: 8px;
  text-transform: none;
}
.cam-badge.on {
  background: var(--success-bg);
  color: var(--success);
  border: 1px solid var(--success-border);
}
.cam-badge.off {
  background: var(--warning-bg);
  color: var(--warning);
}
.cam-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cam-row-2 {
  display: flex;
  gap: 8px;
}
.cam-row-2 .cam-label {
  flex: 1;
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
/* Hide number input spinners */
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
.cam-status {
  font-size: 11px;
  color: var(--text-4);
  text-align: center;
  margin-top: 6px;
  font-weight: 500;
}
</style>
