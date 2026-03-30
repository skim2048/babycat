<script setup>
import { ref, onMounted } from 'vue'
import Hls from 'hls.js'

const videoEl = ref(null)

onMounted(() => {
  const hlsUrl = `http://${window.location.hostname}:8888/live/index.m3u8`
  const video = videoEl.value
  const tryPlay = () => video.play().catch(() => {})

  if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = hlsUrl
    video.addEventListener('loadedmetadata', tryPlay)
  } else if (Hls.isSupported()) {
    function initHls() {
      const hls = new Hls({
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
          setTimeout(initHls, 3000)
        }
      })
    }
    initHls()
  }
})
</script>

<template>
  <div class="video-box">
    <div class="video-label">Live Stream</div>
    <video ref="videoEl" autoplay muted playsinline></video>
  </div>
</template>
