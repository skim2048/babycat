<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import Hls from 'hls.js'

const videoEl = ref(null)
let stallTimer = null

onMounted(() => {
  const hlsUrl = `http://${window.location.hostname}:8888/live/index.m3u8`
  const video = videoEl.value
  const tryPlay = () => video.play().catch(() => {})

  if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = hlsUrl
    video.addEventListener('loadedmetadata', tryPlay)
  } else if (Hls.isSupported()) {
    let hls = null

    function initHls() {
      if (hls) hls.destroy()
      hls = new Hls({
        liveSyncDurationCount: 1,
        liveMaxLatencyDurationCount: 3,
        lowLatencyMode: true,
        backBufferLength: 0,
      })
      hls.loadSource(hlsUrl)
      hls.attachMedia(video)
      hls.on(Hls.Events.MANIFEST_PARSED, tryPlay)
      hls.on(Hls.Events.ERROR, (_, data) => {
        if (data.fatal) {
          hls.destroy()
          hls = null
          setTimeout(initHls, 3000)
        }
      })
    }
    initHls()

    // Stall detection: if video hasn't progressed in 8 seconds while not paused, restart HLS
    let lastTime = 0
    stallTimer = setInterval(() => {
      if (!video.paused && video.currentTime === lastTime && lastTime > 0) {
        console.warn('[LiveStream] stall detected, reinitializing HLS')
        initHls()
      }
      lastTime = video.currentTime
    }, 8000)
  }
})

onUnmounted(() => {
  if (stallTimer) clearInterval(stallTimer)
})
</script>

<template>
  <div class="video-box">
    <div class="video-label">Live Stream</div>
    <video ref="videoEl" autoplay muted playsinline></video>
  </div>
</template>
