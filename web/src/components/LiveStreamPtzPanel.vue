<script setup>
import { ref, watch, onBeforeUnmount } from 'vue'
import { usePtz } from '../composables/usePtz.js'

const props = defineProps({
  open: Boolean,
  disabled: Boolean,
})

const emit = defineEmits(['toggle'])

const { status: ptzStatus, startMove, stopMove, forceStop, saveHome, gotoHome } = usePtz()
const ptzPressing = ref(null)

const ptzDirs = [
  { id: 'up', pan: 0, tilt: 1 },
  { id: 'left', pan: -1, tilt: 0 },
  { id: 'right', pan: 1, tilt: 0 },
  { id: 'down', pan: 0, tilt: -1 },
]

function ptzDown(dir, event) {
  event.preventDefault()
  ptzPressing.value = dir.id
  startMove(dir.pan, dir.tilt)
}

function ptzUp(dir) {
  if (ptzPressing.value !== dir.id) return
  ptzPressing.value = null
  stopMove()
}

function forceStopMotion() {
  ptzPressing.value = null
  forceStop()
}

function stopActiveMotion() {
  if (ptzPressing.value == null) return
  forceStopMotion()
}

watch(
  () => props.disabled,
  (disabled) => {
    if (disabled) stopActiveMotion()
  },
)

onBeforeUnmount(() => {
  stopActiveMotion()
})

defineExpose({
  stopActiveMotion,
})
</script>

<template>
  <div class="vsb-acc">
    <button class="vsb-acc-header" @click="emit('toggle')">
      <span>PTZ</span>
      <svg class="vsb-acc-chevron" :class="{ open }" width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="2,4.5 6,8 10,4.5"/>
      </svg>
    </button>
    <div class="vsb-acc-body" :class="{ open }">
      <div class="vsb-acc-content">
        <div class="vsb-ptz-grid">
          <div></div>
          <button class="vsb-ptz-btn" :class="{ pressing: ptzPressing === 'up' }" :disabled="disabled"
            @mousedown="(event) => ptzDown(ptzDirs[0], event)" @mouseup="ptzUp(ptzDirs[0])"
            @mouseleave="ptzUp(ptzDirs[0])" @touchstart.prevent="(event) => ptzDown(ptzDirs[0], event)"
            @touchend="ptzUp(ptzDirs[0])">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="2,9.5 7,4.5 12,9.5"/></svg>
          </button>
          <div></div>

          <button class="vsb-ptz-btn" :class="{ pressing: ptzPressing === 'left' }" :disabled="disabled"
            @mousedown="(event) => ptzDown(ptzDirs[1], event)" @mouseup="ptzUp(ptzDirs[1])"
            @mouseleave="ptzUp(ptzDirs[1])" @touchstart.prevent="(event) => ptzDown(ptzDirs[1], event)"
            @touchend="ptzUp(ptzDirs[1])">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9.5,2 4.5,7 9.5,12"/></svg>
          </button>
          <button class="vsb-ptz-btn stop" :disabled="disabled" @click="forceStopMotion">
            <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor"><rect x="1" y="1" width="8" height="8" rx="1.5"/></svg>
          </button>
          <button class="vsb-ptz-btn" :class="{ pressing: ptzPressing === 'right' }" :disabled="disabled"
            @mousedown="(event) => ptzDown(ptzDirs[2], event)" @mouseup="ptzUp(ptzDirs[2])"
            @mouseleave="ptzUp(ptzDirs[2])" @touchstart.prevent="(event) => ptzDown(ptzDirs[2], event)"
            @touchend="ptzUp(ptzDirs[2])">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4.5,2 9.5,7 4.5,12"/></svg>
          </button>

          <div></div>
          <button class="vsb-ptz-btn" :class="{ pressing: ptzPressing === 'down' }" :disabled="disabled"
            @mousedown="(event) => ptzDown(ptzDirs[3], event)" @mouseup="ptzUp(ptzDirs[3])"
            @mouseleave="ptzUp(ptzDirs[3])" @touchstart.prevent="(event) => ptzDown(ptzDirs[3], event)"
            @touchend="ptzUp(ptzDirs[3])">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="2,4.5 7,9.5 12,4.5"/></svg>
          </button>
          <div></div>
        </div>
        <div class="vsb-ptz-actions">
          <button class="vsb-ptz-act" :disabled="disabled" @click="saveHome">홈 저장</button>
          <button class="vsb-ptz-act go" :disabled="disabled" @click="gotoHome">홈 이동</button>
        </div>
        <div class="vsb-ptz-status">{{ ptzStatus }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.vsb-acc {
  background: var(--bg-surface);
  flex-shrink: 0;
}

.vsb-acc-header {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 12px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.9px;
  color: var(--text-3);
  transition: background 0.15s, color 0.15s;
  text-align: left;
}

.vsb-acc-header:hover {
  background: var(--bg-surface-hover);
  color: var(--text-1);
}

.vsb-acc-chevron {
  color: var(--text-4);
  flex-shrink: 0;
  transition: transform 0.22s ease;
}

.vsb-acc-chevron.open {
  transform: rotate(180deg);
}

.vsb-acc-body {
  overflow: hidden;
  max-height: 0;
  transition: max-height 0.28s ease;
}

.vsb-acc-body.open {
  max-height: 520px;
}

.vsb-acc-content {
  padding: 10px 12px 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  border-top: 1px solid var(--border-subtle);
}

.vsb-ptz-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
}

.vsb-ptz-btn {
  aspect-ratio: 1;
  width: 100%;
  border: 1px solid var(--border-input);
  border-radius: 7px;
  background: var(--bg-surface-secondary);
  color: var(--text-2);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.12s, border-color 0.12s, color 0.12s, box-shadow 0.12s;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
}

.vsb-ptz-btn:hover:not(:disabled) {
  background: var(--bg-surface-hover);
  color: var(--text-1);
  border-color: var(--border-accent);
}

.vsb-ptz-btn.pressing {
  background: var(--accent-bg);
  border-color: var(--accent);
  color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-shadow);
}

.vsb-ptz-btn.stop {
  background: var(--danger-bg-soft);
  border-color: var(--danger-border);
  color: var(--danger);
}

.vsb-ptz-btn.stop:hover:not(:disabled) {
  background: var(--danger-bg);
}

.vsb-ptz-btn:disabled,
.vsb-ptz-act:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  pointer-events: none;
}

.vsb-ptz-actions {
  display: flex;
  gap: 6px;
}

.vsb-ptz-act {
  flex: 1;
  padding: 6px 4px;
  font-size: 11px;
  font-weight: 600;
  border: 1px solid var(--border-input);
  border-radius: 6px;
  background: var(--bg-surface-secondary);
  color: var(--text-2);
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}

.vsb-ptz-act:hover:not(:disabled) {
  background: var(--bg-surface-hover);
}

.vsb-ptz-act.go {
  background: var(--success-bg);
  border-color: var(--success-border);
  color: var(--success);
}

.vsb-ptz-act.go:hover:not(:disabled) {
  background: var(--success-hover);
}

.vsb-ptz-status {
  font-size: 9.5px;
  color: var(--text-4);
  text-align: center;
  min-height: 14px;
}
</style>
