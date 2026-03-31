<script setup>
import { ref } from 'vue'
import { useSSE } from '../composables/useSSE.js'
import { usePtz } from '../composables/usePtz.js'

const { state } = useSSE()
const { status, startMove, stopMove, forceStop, saveHome, gotoHome } = usePtz()

const collapsed = ref(false)
const pressing = ref(null)

function fmt(v) {
  return v !== null && v !== undefined ? v.toFixed(3) : '-'
}

const dirs = [
  { id: 'up',    pan: 0,  tilt: 1,  label: '▲' },
  { id: 'down',  pan: 0,  tilt: -1, label: '▼' },
  { id: 'left',  pan: -1, tilt: 0,  label: '◀' },
  { id: 'right', pan: 1,  tilt: 0,  label: '▶' },
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
  <div class="section" :class="{ collapsed }">
    <div class="section-title" @click="collapsed = !collapsed">
      Pan / Tilt <span class="arrow">&#9660;</span>
    </div>
    <div class="section-body">
      <div class="ptz-info">
        현재 위치 &nbsp; Pan: <span>{{ fmt(state.ptz_pan) }}</span>
        &nbsp; Tilt: <span>{{ fmt(state.ptz_tilt) }}</span>
      </div>

      <div class="ptz-row">
        <button
          v-for="dir in dirs"
          :key="dir.id"
          class="ptz-btn"
          :class="{ pressing: pressing === dir.id }"
          @mousedown="(e) => onDown(dir, e)"
          @mouseup="onUp(dir)"
          @mouseleave="onUp(dir)"
          @touchstart.prevent="(e) => onDown(dir, e)"
          @touchend="onUp(dir)"
        >{{ dir.label }}</button>
        <button class="ptz-btn stop" @click="forceStop">■</button>
      </div>

      <div class="ptz-saved-row">
        <div class="ptz-saved-val">
          저장 &nbsp; Pan: <span>{{ fmt(state.ptz_saved_pan) }}</span>
          &nbsp; Tilt: <span>{{ fmt(state.ptz_saved_tilt) }}</span>
        </div>
        <button class="ptz-action-btn" @click="saveHome">현재 저장</button>
        <button class="ptz-action-btn go" @click="gotoHome">저장 위치로</button>
      </div>

      <div class="ptz-status-txt">{{ status }}</div>
    </div>
  </div>
</template>
