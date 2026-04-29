<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { alternateStreamProtocol, useCamera } from '../composables/useCamera.js'
import { useAuth } from '../composables/useAuth.js'
import { useLocale } from '../composables/useLocale.js'
import { useSSE } from '../composables/useSSE.js'
import InferenceOverlay from './InferenceOverlay.vue'
import LiveStreamSystemPanel from './LiveStreamSystemPanel.vue'
import LiveStreamPtzPanel from './LiveStreamPtzPanel.vue'
import { useStreamStats } from '../composables/useStreamStats.js'
import { getHlsUrl, getWhepUrl } from '../endpoints.js'

const {
  state: sseState,
  pipelineStateLabel,
  pipelineDetailLabel,
} = useSSE()
const { isAuthenticated, isPersistentSession, sessionRemainingSeconds } = useAuth()
const { t } = useLocale()

const { accessToken } = useAuth()
const { config, configured, connecting, connected, reconnectKey, preferredStreamProtocol, ptzEnabled, setConnected, setDisconnected, disconnect, save: saveCamera } = useCamera()

watch(reconnectKey, () => {
  if (!configured.value) return
  stopCountdown()
  destroyAll()
  handleConnect()
})

watch(accessToken, (currentToken) => {
  if (!currentToken) {
    handleDisconnect()
  }
})

watch(() => sseState.pipeline_state, (nextState, prevState) => {
  if (!configured.value || stopped.value) return
  if (nextState !== 'streaming' || !prevState || prevState === 'streaming') return
  if (loading.value) return
  schedulePipelineRecovery()
})

const videoRef = ref(null)
const videoWrapRef = ref(null)
const ptzPanelRef = ref(null)
const loading = ref(false)
const timedOut = ref(false)
const stopped = ref(true)
const fullscreen = ref(false)
const inferOpen = ref(false)

// ── Accordion state ──
const sysOpen = ref(true)
const ptzOpen = ref(true)

function stopActivePtzMotion() {
  ptzPanelRef.value?.stopActiveMotion()
}

// ── Stream ──

function toggleFullscreen() {
  const el = videoWrapRef.value
  if (!el) return
  if (!document.fullscreenElement) {
    el.requestFullscreen()
  } else {
    document.exitFullscreen()
  }
}

function onFullscreenChange() {
  fullscreen.value = !!document.fullscreenElement
}

let hls = null
let Hls = null
let stallTimer = null
let timeoutTimer = null
let retryTimer = null
let pipelineRecoveryTimer = null
let countdownTimer = null
let pc = null
let sessionId = 0
let connectDeadline = 0
let fallbackUsed = false
const remainingSec = ref(0)
const STALL_TIMEOUT = 8000
const CONNECT_TIMEOUT = 15000

const activeProtocol = ref(preferredStreamProtocol.value)
const isWebRTC = computed(() => activeProtocol.value === 'webrtc')
const preferredIsWebRTC = computed(() => preferredStreamProtocol.value === 'webrtc')
const fallbackActive = computed(() => activeProtocol.value !== preferredStreamProtocol.value)
const isPlaying = computed(() => connected.value && !loading.value && !timedOut.value && !stopped.value)
const showSessionRemaining = computed(() =>
  isAuthenticated.value && !isPersistentSession.value && sessionRemainingSeconds.value > 0,
)
const sessionRemainingText = computed(() => {
  const total = sessionRemainingSeconds.value
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
})
const { stats, startStats, stopStats } = useStreamStats({
  videoRef,
  isWebRTC,
  getPeerConnection: () => pc,
  getHlsInstance: () => hls,
})

function toggleProtocol() {
  config.stream_protocol = alternateStreamProtocol(preferredStreamProtocol.value)
  saveCamera()
}

function handleConnect() {
  stopped.value = false
  connecting.value = true
  resetPreferredProtocol()
  connectDeadline = Date.now() + CONNECT_TIMEOUT
  startCountdown()
  restartStream()
}

function startCountdown() {
  if (countdownTimer) clearInterval(countdownTimer)
  const tick = () => {
    const ms = Math.max(0, connectDeadline - Date.now())
    remainingSec.value = Math.ceil(ms / 1000)
    if (ms <= 0) {
      if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null }
      if (loading.value) {
        if (tryFallback(sessionId)) return
        loading.value = false
        timedOut.value = true
        destroyHls()
        destroyWebRTC()
        stopStats()
        if (retryTimer) { clearTimeout(retryTimer); retryTimer = null }
        if (timeoutTimer) { clearTimeout(timeoutTimer); timeoutTimer = null }
        setDisconnected()
      }
    }
  }
  tick()
  countdownTimer = setInterval(tick, 250)
}

function stopCountdown() {
  if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null }
  remainingSec.value = 0
}

function handleDisconnect() {
  stopActivePtzMotion()
  stopped.value = true
  stopCountdown()
  destroyAll()
  disconnect()
}

function resetPreferredProtocol() {
  activeProtocol.value = preferredStreamProtocol.value
  fallbackUsed = false
}

function restartStream({ resetProtocol = false } = {}) {
  if (resetProtocol) resetPreferredProtocol()
  destroyAll()
  initStream()
}

function initStream() {
  if (isWebRTC.value) initWebRTC()
  else initHls()
}

function destroyAll() {
  sessionId++
  clearAllTimers()
  destroyHls()
  destroyWebRTC()
  stopStats()
  loading.value = false
  timedOut.value = false
}

function clearAllTimers() {
  if (timeoutTimer) { clearTimeout(timeoutTimer); timeoutTimer = null }
  if (stallTimer) { clearInterval(stallTimer); stallTimer = null }
  if (retryTimer) { clearTimeout(retryTimer); retryTimer = null }
  if (pipelineRecoveryTimer) { clearTimeout(pipelineRecoveryTimer); pipelineRecoveryTimer = null }
}

function browserPlaybackUnavailable() {
  return !configured.value || stopped.value || loading.value || timedOut.value
}

function getVideoPlaybackStatus(referenceTime = null) {
  const video = videoRef.value
  if (browserPlaybackUnavailable()) return 'inactive'
  if (!video) return 'missing_video'
  if (video.ended) return 'ended'
  if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return 'not_ready'
  if (video.paused) return 'paused'
  if (referenceTime != null && video.currentTime <= referenceTime + 0.05) return 'stalled'
  return 'healthy'
}

function browserPlaybackNeedsReconnect(referenceTime = null) {
  const status = getVideoPlaybackStatus(referenceTime)
  return status !== 'healthy' && status !== 'inactive'
}

function schedulePipelineRecovery() {
  const baselineTime = videoRef.value?.currentTime ?? null
  if (pipelineRecoveryTimer) clearTimeout(pipelineRecoveryTimer)
  pipelineRecoveryTimer = setTimeout(() => {
    pipelineRecoveryTimer = null
    if (!browserPlaybackNeedsReconnect(baselineTime)) return
    restartStream()
  }, 1250)
}

function tryFallback(mySession) {
  if (fallbackUsed || mySession !== sessionId) return false
  fallbackUsed = true
  activeProtocol.value = alternateStreamProtocol(activeProtocol.value)
  connectDeadline = Date.now() + CONNECT_TIMEOUT
  startCountdown()
  initStream()
  return true
}

// ── HLS ──

async function ensureHls() {
  if (Hls) return Hls
  const mod = await import('hls.js/light')
  Hls = mod.default
  return Hls
}

async function initHls() {
  const mySession = ++sessionId
  clearAllTimers()
  destroyHls()
  destroyWebRTC()
  loading.value = true
  timedOut.value = false

  const video = videoRef.value
  if (!video) return

  const HlsLib = await ensureHls().catch(() => null)
  if (mySession !== sessionId) return

  if (HlsLib && HlsLib.isSupported()) {
    hls = new HlsLib({
      liveSyncDurationCount: 1,
      liveMaxLatencyDurationCount: 3,
      maxBufferLength: 3,
      maxMaxBufferLength: 6,
    })
    hls.loadSource(getHlsUrl())
    hls.attachMedia(video)
    hls.on(HlsLib.Events.MANIFEST_PARSED, () => { video.play().catch(() => {}) })
    hls.on(HlsLib.Events.ERROR, (_, data) => {
      if (data.fatal && mySession === sessionId && Date.now() < connectDeadline) {
        if (tryFallback(mySession)) return
        retryTimer = setTimeout(() => {
          if (mySession === sessionId && Date.now() < connectDeadline) initHls()
        }, 3000)
      }
    })
  } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = getHlsUrl()
    video.addEventListener('loadedmetadata', () => { video.play().catch(() => {}) })
  }

  video.addEventListener('playing', onPlaying)
  startStallDetection(mySession)
}

function destroyHls() {
  const video = videoRef.value
  if (video) {
    video.removeEventListener('playing', onPlaying)
    video.src = ''
    video.load()
  }
  if (hls) { hls.destroy(); hls = null }
}

// ── WebRTC (WHEP) ──

function waitForIceGathering(peerConnection) {
  return new Promise((resolve) => {
    if (peerConnection.iceGatheringState === 'complete') { resolve(); return }
    peerConnection.addEventListener('icegatheringstatechange', function handler() {
      if (peerConnection.iceGatheringState === 'complete') {
        peerConnection.removeEventListener('icegatheringstatechange', handler)
        resolve()
      }
    })
  })
}

async function initWebRTC() {
  const mySession = ++sessionId
  clearAllTimers()
  destroyHls()
  destroyWebRTC()
  loading.value = true
  timedOut.value = false

  const video = videoRef.value
  if (!video) return

  try {
    pc = new RTCPeerConnection({ iceServers: [] })
    pc.addTransceiver('video', { direction: 'recvonly' })
    pc.addTransceiver('audio', { direction: 'recvonly' })

    pc.ontrack = (e) => {
      if (mySession !== sessionId) return
      if (e.streams && e.streams[0]) {
        video.srcObject = e.streams[0]
        video.play().catch(() => {})
      }
    }

    pc.onconnectionstatechange = () => {
      if (mySession !== sessionId || !pc) return
      const state = pc.connectionState
      if (state === 'connected') {
        onPlaying()
      } else if ((state === 'failed' || state === 'disconnected') && Date.now() < connectDeadline) {
        if (tryFallback(mySession)) return
        retryTimer = setTimeout(() => {
          if (mySession === sessionId && Date.now() < connectDeadline) initWebRTC()
        }, 3000)
      }
    }

    const offer = await pc.createOffer()
    if (mySession !== sessionId) return
    await pc.setLocalDescription(offer)
    await waitForIceGathering(pc)
    if (mySession !== sessionId) return

    const res = await fetch(getWhepUrl(), {
      method: 'POST',
      headers: { 'Content-Type': 'application/sdp' },
      body: pc.localDescription.sdp,
    })
    if (mySession !== sessionId) return
    if (!res.ok) throw new Error(`WHEP ${res.status}`)

    const answerSdp = await res.text()
    await pc.setRemoteDescription(new RTCSessionDescription({ type: 'answer', sdp: answerSdp }))
  } catch (e) {
    if (mySession !== sessionId) return
    if (Date.now() < connectDeadline) {
      if (tryFallback(mySession)) return
      retryTimer = setTimeout(() => {
        if (mySession === sessionId && Date.now() < connectDeadline) initWebRTC()
      }, 3000)
    }
  }
}

function destroyWebRTC() {
  if (pc) {
    pc.ontrack = null
    pc.onconnectionstatechange = null
    pc.close()
    pc = null
  }
  const video = videoRef.value
  if (video) video.srcObject = null
}

// ── Common handlers ──

function onPlaying() {
  loading.value = false
  timedOut.value = false
  setConnected()
  stopCountdown()
  if (timeoutTimer) { clearTimeout(timeoutTimer); timeoutTimer = null }
  startStats()
}

function startStallDetection(mySession) {
  if (stallTimer) clearInterval(stallTimer)
  let lastTime = 0
  stallTimer = setInterval(() => {
    if (mySession !== sessionId) { clearInterval(stallTimer); stallTimer = null; return }
    const video = videoRef.value
    if (!video) return
    if (browserPlaybackNeedsReconnect(lastTime)) {
      restartStream()
      return
    }
    lastTime = video.currentTime
  }, STALL_TIMEOUT)
}

onMounted(() => {
  document.addEventListener('fullscreenchange', onFullscreenChange)
})
onBeforeUnmount(() => {
  stopActivePtzMotion()
  destroyAll()
  document.removeEventListener('fullscreenchange', onFullscreenChange)
})
</script>

<template>
  <div class="video-box">
    <div class="video-box-body">

      <!-- ── Left Sidebar ── -->
      <div class="video-sidebar">
        <LiveStreamSystemPanel :open="sysOpen" @toggle="sysOpen = !sysOpen" />
        <LiveStreamPtzPanel
          v-if="ptzEnabled"
          ref="ptzPanelRef"
          :open="ptzOpen"
          :disabled="!isPlaying"
          @toggle="ptzOpen = !ptzOpen"
        />
      </div>

      <!-- ── Video wrap ── -->
      <div class="video-wrap" ref="videoWrapRef">
        <video ref="videoRef" muted playsinline />

        <div class="video-top-bar">
          <div v-if="showSessionRemaining" class="session-remaining-badge">
            {{ t('live.sessionRemaining', { time: sessionRemainingText }) }}
          </div>
          <div class="proto-toggle" @click="toggleProtocol">
            <span class="proto-opt" :class="{ active: !preferredIsWebRTC }">HLS</span>
            <span class="proto-opt" :class="{ active: preferredIsWebRTC }">WebRTC</span>
          </div>
        </div>

        <div v-if="stopped" class="video-overlay clickable" @click="handleConnect">
          <div class="play-icon">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
              <circle cx="24" cy="24" r="23" stroke="rgba(255,255,255,0.4)" stroke-width="2"/>
              <polygon points="19,14 19,34 36,24" fill="rgba(255,255,255,0.85)"/>
            </svg>
          </div>
          <span class="overlay-text">{{ t('live.connectIdle') }}</span>
        </div>

        <div v-else-if="loading" class="video-overlay">
          <div class="spinner" />
          <span class="overlay-text">{{ t('live.connecting', { protocol: activeProtocol.toUpperCase(), seconds: remainingSec }) }}</span>
        </div>

        <div v-else-if="timedOut" class="video-overlay">
          <span class="overlay-text timeout">{{ t('live.timeout') }}</span>
          <button class="retry-btn" @click="handleConnect">{{ t('live.retry') }}</button>
        </div>

        <div v-if="isPlaying && fallbackActive" class="protocol-badge">
          {{ t('live.fallback', { protocol: activeProtocol.toUpperCase() }) }}
        </div>

        <button v-if="!stopped" class="disconnect-btn" @click="handleDisconnect" :title="t('live.disconnect')">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
            <line x1="3" y1="3" x2="13" y2="13" />
            <line x1="13" y1="3" x2="3" y2="13" />
          </svg>
        </button>

        <InferenceOverlay :open="inferOpen && isPlaying" />

        <!-- Bottom-right toolbar -->
        <div class="video-bar">
          <!-- Inference toggle -->
          <button
            class="toolbar-btn infer-btn"
            :class="{ 'infer-triggered': sseState.event_triggered, 'toolbar-btn-disabled': !isPlaying }"
            :disabled="!isPlaying"
            @click.stop="inferOpen = !inferOpen"
            :title="t('live.inference')"
          >
            <svg v-if="!sseState.event_triggered" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M5.5 14 L10.5 14" />
              <path d="M6 12 L6 10.5 Q4 9 4 6.5 Q4 3 8 2 Q12 3 12 6.5 Q12 9 10 10.5 L10 12 Z" fill="none" />
            </svg>
            <svg v-else width="16" height="16" viewBox="0 0 16 16" fill="none" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M5.5 14 L10.5 14" stroke="rgba(255,220,50,0.9)" />
              <path d="M6 12 L6 10.5 Q4 9 4 6.5 Q4 3 8 2 Q12 3 12 6.5 Q12 9 10 10.5 L10 12 Z" fill="rgba(255,220,50,0.3)" stroke="rgba(255,220,50,0.9)" />
              <line x1="8" y1="0" x2="8" y2="1" stroke="rgba(255,220,50,0.6)" />
              <line x1="2" y1="3" x2="3" y2="4" stroke="rgba(255,220,50,0.6)" />
              <line x1="14" y1="3" x2="13" y2="4" stroke="rgba(255,220,50,0.6)" />
              <line x1="1" y1="7" x2="2.5" y2="7" stroke="rgba(255,220,50,0.6)" />
              <line x1="15" y1="7" x2="13.5" y2="7" stroke="rgba(255,220,50,0.6)" />
            </svg>
          </button>

          <!-- Fullscreen -->
          <button class="toolbar-btn" @click="toggleFullscreen" :title="fullscreen ? t('live.fullscreen.exit') : t('live.fullscreen.enter')">
            <svg v-if="!fullscreen" width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="11,1 17,1 17,7" />
              <polyline points="7,17 1,17 1,11" />
            </svg>
            <svg v-else width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="17,7 11,7 11,1" />
              <polyline points="1,11 7,11 7,17" />
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Status bar -->
    <div class="status-bar">
      <span class="sb-item">
        <span class="sb-key">{{ t('live.pipeline') }}</span>
        <span class="sb-val">{{ pipelineStateLabel }}<template v-if="pipelineDetailLabel"> ({{ pipelineDetailLabel }})</template></span>
      </span>
      <span class="sb-sep">·</span>
      <span class="sb-item"><span class="sb-key">{{ t('live.resolution') }}</span><span class="sb-val">{{ stats.resolution || '–' }}</span></span>
      <span class="sb-sep">·</span>
      <span class="sb-item"><span class="sb-key">FPS</span><span class="sb-val">{{ stats.fps || '–' }}</span></span>
      <span class="sb-sep">·</span>
      <span class="sb-item"><span class="sb-key">{{ t('live.bitrate') }}</span><span class="sb-val">{{ stats.bitrate || '–' }}</span></span>
      <span class="sb-sep">·</span>
      <span class="sb-item"><span class="sb-key">{{ t('live.codec') }}</span><span class="sb-val">{{ stats.codec || '–' }}</span></span>
      <span class="sb-sep">·</span>
      <span class="sb-item"><span class="sb-key">{{ t('live.latency') }}</span><span class="sb-val">{{ stats.rtt || '–' }}</span></span>
      <span class="sb-sep">·</span>
      <span class="sb-item"><span class="sb-key">{{ t('live.packetLoss') }}</span><span class="sb-val">{{ stats.packetLoss || '–' }}</span></span>
    </div>
  </div>
</template>

<style scoped>

.video-box {
  gap: 0;
  background: var(--bg-surface);
}

.video-box-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: row;
}

/* ── Sidebar ── */
.video-sidebar {
  width: 210px;
  flex-shrink: 0;
  background: var(--bg-surface-secondary);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 1px;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-gutter: stable;
}
.video-sidebar::-webkit-scrollbar { width: 4px; }
.video-sidebar::-webkit-scrollbar-track { background: transparent; }
.video-sidebar::-webkit-scrollbar-thumb { background: var(--scrollbar); border-radius: 2px; }

/* ── Sidebar separators ── */
.video-sidebar :deep(.vsb-acc + .vsb-acc) {
  border-top: 1px solid var(--border);
}
/* ── Status bar ── */
.status-bar {
  flex-shrink: 0;
  height: 26px;
  background: var(--bg-surface);
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  padding: 0 8px;
  overflow: hidden;
}
.sb-item {
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.sb-sep {
  margin: 0 7px;
  color: var(--border-accent);
  font-size: 10px;
  flex-shrink: 0;
}
.sb-key {
  font-size: 10px;
  color: var(--text-4);
  font-weight: 600;
}
.sb-val {
  font-size: 10px;
  color: var(--text-2);
  font-weight: 700;
}

/* ── Video wrap ── */
.video-wrap {
  flex: 1;
  min-height: 0;
  min-width: 0;
  position: relative;
}
.video-wrap video {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #000;
  clip-path: inset(0 0 1px 0);
}
.video-wrap:fullscreen { background: #000; }
.video-wrap:fullscreen video { clip-path: none; }

.video-top-bar {
  position: absolute;
  top: 8px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 4;
  display: flex;
  align-items: center;
  gap: 6px;
}
.session-remaining-badge {
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.14);
  background: rgba(0,0,0,0.65);
  color: rgba(255,255,255,0.9);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.2px;
  white-space: nowrap;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
.proto-toggle {
  display: flex;
  align-items: center;
  background: rgba(0,0,0,0.65);
  border: 1px solid rgba(255,255,255,0.14);
  border-radius: 999px;
  padding: 2px;
  gap: 2px;
  cursor: pointer;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  user-select: none;
}
.proto-opt {
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: rgba(255,255,255,0.38);
  transition: background 0.22s, color 0.22s;
}
.proto-opt.active {
  background: rgba(255,255,255,0.15);
  color: rgba(255,255,255,0.95);
}
.disconnect-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 4;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 6px;
  background: rgba(0,0,0,0.55);
  color: rgba(255,255,255,0.8);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.disconnect-btn:hover {
  background: rgba(208,56,56,0.7);
  color: #fff;
}
.protocol-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 4;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(0,0,0,0.65);
  color: rgba(255,255,255,0.82);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.2px;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
.video-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgba(0,0,0,0.6);
}
.video-overlay.clickable { cursor: pointer; }
.video-overlay.clickable:hover .play-icon svg circle { stroke: rgba(255,255,255,0.7); }
.video-overlay.clickable:hover .play-icon { transform: scale(1.08); }
.play-icon { transition: transform 0.15s; }

.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid rgba(255,255,255,0.15);
  border-top-color: rgba(255,255,255,0.8);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.overlay-text {
  font-size: 13px;
  color: rgba(255,255,255,0.7);
  font-weight: 500;
}
.overlay-text.timeout { color: var(--danger); }

.retry-btn {
  font-size: 12px;
  font-weight: 600;
  padding: 6px 16px;
  border: 1px solid rgba(255,255,255,0.3);
  border-radius: var(--radius);
  background: rgba(255,255,255,0.1);
  color: rgba(255,255,255,0.8);
  cursor: pointer;
  transition: background 0.15s;
}
.retry-btn:hover { background: rgba(255,255,255,0.2); }

/* ── Video bar ── */
.video-bar {
  position: absolute;
  bottom: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 6px;
  background: rgba(0,0,0,0.55);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  z-index: 5;
}

.toolbar-btn {
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 6px;
  background: rgba(255,255,255,0.06);
  color: rgba(255,255,255,0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.toolbar-btn:hover {
  background: rgba(255,255,255,0.16);
  color: #fff;
}
.toolbar-btn-disabled {
  color: rgba(255,255,255,0.25);
  cursor: default;
  pointer-events: none;
}
.infer-triggered {
  background: rgba(255,220,50,0.25);
}
</style>
