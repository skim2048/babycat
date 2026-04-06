<script setup>
import { ref, onMounted, watch, onBeforeUnmount } from 'vue'
import Hls from 'hls.js'
import { useCamera } from '../composables/useCamera.js'

const { configured, setConnected, setDisconnected } = useCamera()

const videoRef = ref(null)
const loading = ref(false)
const timedOut = ref(false)
let hls = null
let stallTimer = null
let timeoutTimer = null
const STALL_TIMEOUT = 8000
const CONNECT_TIMEOUT = 10000

function getStreamUrl() {
  const host = window.location.hostname
  return `http://${host}:8888/live/index.m3u8`
}

function initHls() {
  destroyHls()
  loading.value = true
  timedOut.value = false
  const video = videoRef.value
  if (!video) return

  const url = getStreamUrl()

  timeoutTimer = setTimeout(() => {
    if (loading.value) {
      loading.value = false
      timedOut.value = true
      setDisconnected()
    }
  }, CONNECT_TIMEOUT)

  if (Hls.isSupported()) {
    hls = new Hls({
      liveSyncDurationCount: 1,
      liveMaxLatencyDurationCount: 3,
      maxBufferLength: 3,
      maxMaxBufferLength: 6,
    })
    hls.loadSource(url)
    hls.attachMedia(video)
    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      video.play().catch(() => {})
    })
    hls.on(Hls.Events.ERROR, (_, data) => {
      if (data.fatal) {
        setTimeout(initHls, 3000)
      }
    })
  } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = url
    video.addEventListener('loadedmetadata', () => {
      video.play().catch(() => {})
    })
  }

  video.addEventListener('playing', onPlaying)
  startStallDetection()
}

function onPlaying() {
  loading.value = false
  timedOut.value = false
  setConnected()
  if (timeoutTimer) {
    clearTimeout(timeoutTimer)
    timeoutTimer = null
  }
}

function destroyHls() {
  if (timeoutTimer) {
    clearTimeout(timeoutTimer)
    timeoutTimer = null
  }
  stopStallDetection()
  const video = videoRef.value
  if (video) {
    video.removeEventListener('playing', onPlaying)
  }
  if (hls) {
    hls.destroy()
    hls = null
  }
}

function startStallDetection() {
  stopStallDetection()
  let lastTime = 0
  stallTimer = setInterval(() => {
    const video = videoRef.value
    if (!video) return
    if (video.currentTime === lastTime && !video.paused) {
      initHls()
    }
    lastTime = video.currentTime
  }, STALL_TIMEOUT)
}

function stopStallDetection() {
  if (stallTimer) {
    clearInterval(stallTimer)
    stallTimer = null
  }
}

onMounted(() => {
  if (configured.value) initHls()
})

watch(configured, (val) => {
  if (val) {
    initHls()
  } else {
    destroyHls()
    loading.value = false
    timedOut.value = false
  }
})

onBeforeUnmount(destroyHls)
</script>

<template>
  <div class="video-box">
    <span class="video-label">실시간 스트림</span>
    <div class="video-wrap">
      <video ref="videoRef" muted playsinline />
      <div v-if="loading" class="video-overlay">
        <div class="spinner" />
        <span class="overlay-text">연결 중...</span>
      </div>
      <div v-else-if="timedOut" class="video-overlay">
        <span class="overlay-text timeout">연결 시간 초과</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.video-wrap {
  flex: 1;
  min-height: 0;
  position: relative;
}
.video-wrap video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  border: 1px solid var(--border);
  background: #000;
  border-radius: var(--radius);
  box-shadow: var(--shadow-md);
}
.video-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgba(0, 0, 0, 0.6);
  border-radius: var(--radius);
}
.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid rgba(255, 255, 255, 0.15);
  border-top-color: rgba(255, 255, 255, 0.8);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.overlay-text {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
  font-weight: 500;
}
.overlay-text.timeout {
  color: var(--danger);
}
</style>
