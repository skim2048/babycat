<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  clip: Object,
  isChecked: Boolean,
})
const emit = defineEmits(['check', 'delete'])

const videoEl = ref(null)
const playing = ref(false)
const progress = ref(0)
const currentTime = ref(0)
const duration = ref(0)

function fmtTime(s) {
  if (isNaN(s)) return '0:00'
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec < 10 ? '0' : ''}${sec}`
}

const timeLabel = computed(() =>
  duration.value ? `${fmtTime(currentTime.value)} / ${fmtTime(duration.value)}` : '0:00',
)

function togglePlay() {
  const vid = videoEl.value
  if (vid.paused) {
    vid.muted = false
    vid.play()
  } else {
    vid.pause()
  }
}

function onPlay() { playing.value = true }
function onPause() { playing.value = false }
function onEnded() {
  const vid = videoEl.value
  vid.muted = true
  vid.currentTime = 0
  playing.value = false
  progress.value = 0
}
function onTimeUpdate() {
  const vid = videoEl.value
  if (vid.duration) {
    progress.value = (vid.currentTime / vid.duration) * 100
    currentTime.value = vid.currentTime
  }
}
function onLoaded() {
  duration.value = videoEl.value.duration
}
function seek(e) {
  const vid = videoEl.value
  if (vid.duration) {
    vid.currentTime = (e.offsetX / e.currentTarget.offsetWidth) * vid.duration
  }
}
</script>

<template>
  <div class="clip-item" :class="{ checked: isChecked }">
    <div class="clip-top-bar">
      <input type="checkbox" class="clip-chk" :checked="isChecked" @change="emit('check', $event.target.checked)" />
      <button class="clip-del-btn" @click="emit('delete')">&#10005;</button>
    </div>
    <div class="clip-video-wrap" @click="togglePlay">
      <video
        ref="videoEl"
        :src="`/clip/${encodeURIComponent(clip.name)}?s=${clip.size}`"
        preload="metadata"
        muted
        playsinline
        @play="onPlay"
        @pause="onPause"
        @ended="onEnded"
        @timeupdate="onTimeUpdate"
        @loadedmetadata="onLoaded"
      ></video>
      <div class="clip-overlay" :class="{ hidden: playing }">
        <div class="clip-play-icon"></div>
      </div>
    </div>
    <div class="clip-controls">
      <button class="clip-ctrl-btn" @click="togglePlay">
        <span v-if="playing">&#9646;&#9646;</span>
        <span v-else>&#9654;</span>
      </button>
      <div class="clip-progress" @click="seek">
        <div class="clip-progress-bar" :style="{ width: progress + '%' }"></div>
      </div>
      <span class="clip-time">{{ timeLabel }}</span>
    </div>
    <div class="clip-info">
      <div class="clip-name">{{ clip.name }}</div>
    </div>
  </div>
</template>
