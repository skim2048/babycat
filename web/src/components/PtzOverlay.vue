<script setup>
import { ref } from 'vue'
import { usePtz } from '../composables/usePtz.js'

defineProps({ open: Boolean })

const { status, startMove, stopMove, forceStop, saveHome, gotoHome } = usePtz()

const pressing = ref(null)

const dirs = [
  { id: 'up',    pan: 0,  tilt: 1,  label: '▲' },
  { id: 'left',  pan: -1, tilt: 0,  label: '◀' },
  { id: 'right', pan: 1,  tilt: 0,  label: '▶' },
  { id: 'down',  pan: 0,  tilt: -1, label: '▼' },
]

function onDown(dir, e) {
  e.preventDefault()
  pressing.value = dir.id
  startMove(dir.pan, dir.tilt)
}

function onUp(dir) {
  if (pressing.value === dir.id) {
    pressing.value = null
    stopMove()
  }
}
</script>

<template>
  <Transition name="fade">
    <div v-if="open" class="ptz-panel" @click.stop>
      <div class="ptz-grid">
        <div class="ptz-grid-row">
          <div class="ptz-spacer" />
          <button
            class="ptz-dir-btn" :class="{ pressing: pressing === 'up' }"
            @mousedown="(e) => onDown(dirs[0], e)" @mouseup="onUp(dirs[0])"
            @mouseleave="onUp(dirs[0])" @touchstart.prevent="(e) => onDown(dirs[0], e)"
            @touchend="onUp(dirs[0])">▲</button>
          <div class="ptz-spacer" />
        </div>
        <div class="ptz-grid-row">
          <button
            class="ptz-dir-btn" :class="{ pressing: pressing === 'left' }"
            @mousedown="(e) => onDown(dirs[1], e)" @mouseup="onUp(dirs[1])"
            @mouseleave="onUp(dirs[1])" @touchstart.prevent="(e) => onDown(dirs[1], e)"
            @touchend="onUp(dirs[1])">◀</button>
          <button class="ptz-dir-btn stop" @click="forceStop">■</button>
          <button
            class="ptz-dir-btn" :class="{ pressing: pressing === 'right' }"
            @mousedown="(e) => onDown(dirs[2], e)" @mouseup="onUp(dirs[2])"
            @mouseleave="onUp(dirs[2])" @touchstart.prevent="(e) => onDown(dirs[2], e)"
            @touchend="onUp(dirs[2])">▶</button>
        </div>
        <div class="ptz-grid-row">
          <div class="ptz-spacer" />
          <button
            class="ptz-dir-btn" :class="{ pressing: pressing === 'down' }"
            @mousedown="(e) => onDown(dirs[3], e)" @mouseup="onUp(dirs[3])"
            @mouseleave="onUp(dirs[3])" @touchstart.prevent="(e) => onDown(dirs[3], e)"
            @touchend="onUp(dirs[3])">▼</button>
          <div class="ptz-spacer" />
        </div>
      </div>

      <div class="ptz-actions">
        <button class="ptz-act-btn" @click="saveHome">현재 저장</button>
        <button class="ptz-act-btn go" @click="gotoHome">저장 위치로</button>
      </div>

      <div class="ptz-status">{{ status }}</div>
    </div>
  </Transition>
</template>

<style scoped>
.ptz-panel {
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(8px);
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ptz-grid {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.ptz-grid-row {
  display: flex;
  gap: 3px;
  justify-content: center;
}
.ptz-spacer {
  width: 40px;
  height: 40px;
}
.ptz-dir-btn {
  width: 40px;
  height: 40px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.85);
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.12s, border-color 0.12s;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
}
.ptz-dir-btn:hover {
  background: rgba(255, 255, 255, 0.2);
}
.ptz-dir-btn:active,
.ptz-dir-btn.pressing {
  background: rgba(91, 158, 230, 0.4);
  border-color: rgba(91, 158, 230, 0.6);
}
.ptz-dir-btn.stop {
  background: rgba(208, 56, 56, 0.3);
  border-color: rgba(208, 56, 56, 0.4);
  font-size: 10px;
  color: rgba(255, 255, 255, 0.7);
}
.ptz-dir-btn.stop:hover {
  background: rgba(208, 56, 56, 0.5);
}

.ptz-actions {
  display: flex;
  gap: 4px;
}
.ptz-act-btn {
  flex: 1;
  padding: 5px 8px;
  font-size: 10px;
  font-weight: 600;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.7);
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}
.ptz-act-btn:hover {
  background: rgba(255, 255, 255, 0.2);
}
.ptz-act-btn.go {
  background: rgba(52, 192, 108, 0.2);
  border-color: rgba(52, 192, 108, 0.3);
  color: rgba(52, 192, 108, 0.9);
}
.ptz-act-btn.go:hover {
  background: rgba(52, 192, 108, 0.35);
}

.ptz-status {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.4);
  text-align: center;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
