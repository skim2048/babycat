<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { alternateStreamProtocol, normalizeStreamProtocol, useCamera } from '../composables/useCamera.js'
import { useAuth } from '../composables/useAuth.js'
import { useSSE } from '../composables/useSSE.js'
import { useAuth } from '../composables/useAuth.js'
import SystemOverlay from './SystemOverlay.vue'
import PtzOverlay from './PtzOverlay.vue'
import InferenceOverlay from './InferenceOverlay.vue'
import { getHlsUrl, getWhepUrl } from '../endpoints.js'

const {
  state: sseState,
  pipelineStateLabel,
  pipelineReasonLabel,
  pipelineStatusText,
  pipelineStatusTone,
} = useSSE()
const { isAuthenticated, isPersistentSession, sessionRemainingSeconds } = useAuth()

const { accessToken } = useAuth()
const { config, configured, connecting, connected, reconnectKey, preferredStreamProtocol, ptzEnabled, setConnected, setDisconnected, disconnect, save: saveCamera } = useCamera()

// @claude Auto-reconnect after a successful camera-profile save (recovers from timeout state too).
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

const videoRef = ref(null)
const videoWrapRef = ref(null)
const loading = ref(false)
const timedOut = ref(false)
const stopped = ref(true)
const fullscreen = ref(false)
const activePanel = ref(null) // 'sys' | 'stats' | 'ptz' | null
const inferOpen = ref(false)

const stats = reactive({
  resolution: '',
  fps: '',
  bitrate: '',
  codec: '',
  rtt: '',
  packetLoss: '',
})
let statsTimer = null
let prevBytes = 0
let prevTime = 0

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
function formatSeconds(value) {
  if (value == null || Number.isNaN(value)) return '-'
  return `${Number(value).toFixed(1)}초`
}

function toggleProtocol() {
  config.stream_protocol = alternateStreamProtocol(preferredStreamProtocol.value)
  saveCamera()
  if (configured.value && !stopped.value) {
    restartStream({ resetProtocol: true })
  }
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
  stopped.value = true
  stopCountdown()
  destroyAll()
  disconnect()
}

// ── Lifecycle ──

function resetPreferredProtocol() {
  activeProtocol.value = preferredStreamProtocol.value
  fallbackUsed = false
}

function restartStream({ resetProtocol = false } = {}) {
  if (resetProtocol) {
    resetPreferredProtocol()
  }
  destroyAll()
  initStream()
}

function initStream() {
  if (isWebRTC.value) {
    initWebRTC()
  } else {
    initHls()
  }
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
    hls.on(HlsLib.Events.MANIFEST_PARSED, () => {
      video.play().catch(() => {})
    })
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
    video.addEventListener('loadedmetadata', () => {
      video.play().catch(() => {})
    })
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
    if (peerConnection.iceGatheringState === 'complete') {
      resolve()
      return
    }
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
      if (mySession !== sessionId) return
      if (!pc) return
      const state = pc.connectionState
      console.log('[WebRTC] connectionState:', state)
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

    console.log('[WebRTC] sending WHEP offer to', getWhepUrl())
    const res = await fetch(getWhepUrl(), {
      method: 'POST',
      headers: { 'Content-Type': 'application/sdp' },
      body: pc.localDescription.sdp,
    })

    if (mySession !== sessionId) return

    if (!res.ok) {
      const errBody = await res.text()
      console.error('[WebRTC] WHEP error:', res.status, errBody)
      throw new Error(`WHEP ${res.status}`)
    }

    const answerSdp = await res.text()
    console.log('[WebRTC] received WHEP answer, setting remote description')
    await pc.setRemoteDescription(new RTCSessionDescription({
      type: 'answer',
      sdp: answerSdp,
    }))
  } catch (e) {
    console.error('[WebRTC] init failed:', e)
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
  if (activePanel.value === 'stats') startStats()
}

function startStallDetection(mySession) {
  if (stallTimer) clearInterval(stallTimer)
  let lastTime = 0
  stallTimer = setInterval(() => {
    if (mySession !== sessionId) { clearInterval(stallTimer); stallTimer = null; return }
    const video = videoRef.value
    if (!video) return
    if (video.currentTime === lastTime && !video.paused) {
      restartStream()
    }
    lastTime = video.currentTime
  }, STALL_TIMEOUT)
}

// ── Stats ──

function startStats() {
  stopStats()
  prevBytes = 0
  prevTime = performance.now()
  statsTimer = setInterval(collectStats, 1000)
}

function stopStats() {
  if (statsTimer) { clearInterval(statsTimer); statsTimer = null }
  stats.resolution = ''
  stats.fps = ''
  stats.bitrate = ''
  stats.codec = ''
  stats.rtt = ''
  stats.packetLoss = ''
}

async function collectStats() {
  const video = videoRef.value
  if (!video) return

  if (video.videoWidth && video.videoHeight) {
    stats.resolution = `${video.videoWidth}×${video.videoHeight}`
  }

  if (isWebRTC.value && pc) {
    await collectWebRTCStats()
  } else if (hls) {
    collectHlsStats()
  }
}

async function collectWebRTCStats() {
  if (!pc) return
  try {
    const reports = await pc.getStats()
    const codecs = {}
    reports.forEach((r) => {
      if (r.type === 'codec') codecs[r.id] = r
    })

    reports.forEach((r) => {
      if (r.type === 'inbound-rtp' && r.kind === 'video') {
        if (r.framesPerSecond != null) {
          stats.fps = `${Math.round(r.framesPerSecond)}`
        }
        const now = performance.now()
        const bytes = r.bytesReceived || 0
        if (prevBytes > 0 && now > prevTime) {
          const bps = ((bytes - prevBytes) * 8) / ((now - prevTime) / 1000)
          if (bps >= 1_000_000) {
            stats.bitrate = `${(bps / 1_000_000).toFixed(1)} Mbps`
          } else {
            stats.bitrate = `${Math.round(bps / 1000)} kbps`
          }
        }
        prevBytes = bytes
        prevTime = now
        if (r.codecId && codecs[r.codecId]) {
          const c = codecs[r.codecId]
          stats.codec = c.mimeType ? c.mimeType.replace('video/', '') : ''
        }
        if (r.packetsLost != null && r.packetsReceived != null) {
          const total = r.packetsReceived + r.packetsLost
          if (total > 0) {
            const pct = ((r.packetsLost / total) * 100).toFixed(1)
            stats.packetLoss = `${r.packetsLost} (${pct}%)`
          }
        }
      }
      if (r.type === 'candidate-pair' && r.state === 'succeeded') {
        if (r.currentRoundTripTime != null) {
          stats.rtt = `${Math.round(r.currentRoundTripTime * 1000)} ms`
        }
      }
    })
  } catch { /* ignore */ }
}

function collectHlsStats() {
  if (!hls) return
  const level = hls.levels && hls.levels[hls.currentLevel]
  if (level && level.attrs && level.attrs['FRAME-RATE']) {
    stats.fps = `${Math.round(parseFloat(level.attrs['FRAME-RATE']))}`
  }
  if (hls.bandwidthEstimate) {
    const bps = hls.bandwidthEstimate
    if (bps >= 1_000_000) {
      stats.bitrate = `${(bps / 1_000_000).toFixed(1)} Mbps`
    } else {
      stats.bitrate = `${Math.round(bps / 1000)} kbps`
    }
  }
  if (level && level.videoCodec) {
    stats.codec = level.videoCodec
  } else if (level && level.codecSet) {
    stats.codec = level.codecSet
  }
  stats.rtt = ''
  stats.packetLoss = ''
}

function togglePanel(name) {
  if (activePanel.value === name) {
    activePanel.value = null
    if (name === 'stats') stopStats()
  } else {
    if (activePanel.value === 'stats') stopStats()
    activePanel.value = name
    if (name === 'stats' && isPlaying.value) startStats()
  }
}

onMounted(() => document.addEventListener('fullscreenchange', onFullscreenChange))
onBeforeUnmount(() => {
  destroyAll()
  stopStats()
  document.removeEventListener('fullscreenchange', onFullscreenChange)
})
</script>

<template>
  <div class="video-box">
    <div class="video-header">
      <span class="video-label">실시간 스트림</span>
      <div class="protocol-toggle" @click="toggleProtocol()">
        <span class="protocol-label" :class="{ active: !preferredIsWebRTC }">HLS</span>
        <div class="toggle-track" :class="{ on: preferredIsWebRTC }">
          <div class="toggle-thumb" />
        </div>
        <span class="protocol-label" :class="{ active: preferredIsWebRTC }">WebRTC</span>
      </div>
    </div>
    <div class="video-wrap" ref="videoWrapRef">
      <video ref="videoRef" muted playsinline />

      <div v-if="showSessionRemaining" class="session-remaining-badge">
        세션 남은 시간 {{ sessionRemainingText }}
      </div>

      <!-- @claude Awaiting connection: click the play icon to connect. -->
      <div v-if="stopped" class="video-overlay clickable" @click="handleConnect">
        <div class="play-icon">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <circle cx="24" cy="24" r="23" stroke="rgba(255,255,255,0.4)" stroke-width="2"/>
            <polygon points="19,14 19,34 36,24" fill="rgba(255,255,255,0.85)"/>
          </svg>
        </div>
        <span class="overlay-text">연결 대기중</span>
      </div>

      <!-- @claude Connecting. -->
      <div v-else-if="loading" class="video-overlay">
        <div class="spinner" />
        <span class="overlay-text">연결 중... {{ activeProtocol.toUpperCase() }} {{ remainingSec }}초</span>
      </div>

      <!-- @claude Connection timeout. -->
      <div v-else-if="timedOut" class="video-overlay">
        <span class="overlay-text timeout">네트워크 상태 또는 카메라 프로필을 확인하세요.</span>
        <button class="retry-btn" @click="handleConnect">재연결</button>
      </div>

      <div v-if="isPlaying && fallbackActive" class="protocol-badge">
        현재 재생: {{ activeProtocol.toUpperCase() }} (저장된 선호값에서 폴백됨)
      </div>

      <div class="pipeline-badge" :class="`pipeline-${pipelineStatusTone}`">
        앱 파이프라인: {{ pipelineStatusText }}
      </div>


      <!-- @claude Bottom-center: inference result panel. -->
      <InferenceOverlay :open="inferOpen && isPlaying" />

      <!-- @claude Bottom-right panel area (anchored above the unified bar). -->
      <div class="toolbar-panels">
        <SystemOverlay :open="activePanel === 'sys'" />

        <Transition name="fade">
          <div v-if="activePanel === 'stats' && isPlaying" class="stats-panel">
            <div class="stats-row" v-if="stats.resolution">
              <span class="stats-key">해상도</span>
              <span class="stats-val">{{ stats.resolution }}</span>
            </div>
            <div class="stats-row" v-if="stats.fps">
              <span class="stats-key">FPS</span>
              <span class="stats-val">{{ stats.fps }}</span>
            </div>
            <div class="stats-row" v-if="stats.bitrate">
              <span class="stats-key">비트레이트</span>
              <span class="stats-val">{{ stats.bitrate }}</span>
            </div>
            <div class="stats-row" v-if="stats.codec">
              <span class="stats-key">코덱</span>
              <span class="stats-val">{{ stats.codec }}</span>
            </div>
            <div class="stats-row" v-if="stats.rtt">
              <span class="stats-key">지연시간</span>
              <span class="stats-val">{{ stats.rtt }}</span>
            </div>
            <div class="stats-row" v-if="stats.packetLoss">
              <span class="stats-key">패킷 손실</span>
              <span class="stats-val">{{ stats.packetLoss }}</span>
            </div>
            <div class="stats-row">
              <span class="stats-key">파이프라인</span>
              <span class="stats-val">{{ pipelineStateLabel }}</span>
            </div>
            <div class="stats-row" v-if="pipelineReasonLabel">
              <span class="stats-key">상태 이유</span>
              <span class="stats-val">{{ pipelineReasonLabel }}</span>
            </div>
            <div class="stats-row" v-if="sseState.pipeline_last_frame_age_s != null">
              <span class="stats-key">마지막 프레임</span>
              <span class="stats-val">{{ formatSeconds(sseState.pipeline_last_frame_age_s) }} 전</span>
            </div>
            <div class="stats-row" v-if="sseState.pipeline_active_for_s != null">
              <span class="stats-key">활성 시간</span>
              <span class="stats-val">{{ formatSeconds(sseState.pipeline_active_for_s) }}</span>
            </div>
            <div class="stats-row">
              <span class="stats-key">재시작 횟수</span>
              <span class="stats-val">{{ sseState.pipeline_restart_count }}</span>
            </div>
          </div>
        </Transition>

        <PtzOverlay v-if="ptzEnabled" :open="activePanel === 'ptz' && isPlaying" />
      </div>

      <!-- @claude Unified bottom bar (right-aligned, always visible). -->
      <div class="video-bar">
        <!-- @claude System monitor (waveform signal icon). -->
        <button class="toolbar-btn" @click.stop="togglePanel('sys')" title="시스템 모니터">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <polyline points="1,8 3,8 5,3 7,13 9,5 11,11 13,7 15,8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
          </svg>
        </button>

        <!-- @claude Throughput info (crossed-arrows icon). -->
        <button
          class="toolbar-btn"
          :class="{ 'toolbar-btn-disabled': !isPlaying }"
          :disabled="!isPlaying"
          @click.stop="togglePanel('stats')"
          title="송수신 정보"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="5" y1="1" x2="5" y2="15" />
            <polyline points="2,4 5,1 8,4" />
            <line x1="11" y1="15" x2="11" y2="1" />
            <polyline points="8,12 11,15 14,12" />
          </svg>
        </button>

        <!-- @claude Disconnect. -->
        <button
          class="toolbar-btn"
          :class="{ 'toolbar-btn-disabled': !isPlaying }"
          :disabled="!isPlaying"
          @click="handleDisconnect"
          title="연결 해제"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="3" y1="3" x2="13" y2="13" />
            <line x1="13" y1="3" x2="3" y2="13" />
          </svg>
        </button>

        <!-- @claude PTZ controls. -->
        <button
          v-if="ptzEnabled"
          class="toolbar-btn"
          :class="{ 'toolbar-btn-disabled': !isPlaying }"
          :disabled="!isPlaying"
          @click.stop="togglePanel('ptz')"
          title="PTZ 조작"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <circle cx="8" cy="8" r="3" fill="none"/>
            <line x1="8" y1="1" x2="8" y2="4" />
            <line x1="8" y1="12" x2="8" y2="15" />
            <line x1="1" y1="8" x2="4" y2="8" />
            <line x1="12" y1="8" x2="15" y2="8" />
          </svg>
        </button>

        <!-- @claude Inference-result toggle. -->
        <button
          class="toolbar-btn infer-btn"
          :class="{ 'infer-triggered': sseState.event_triggered, 'toolbar-btn-disabled': !isPlaying }"
          :disabled="!isPlaying"
          @click.stop="inferOpen = !inferOpen"
          title="추론 결과"
        >
          <!-- @claude Idle: unlit bulb. -->
          <svg v-if="!sseState.event_triggered" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5.5 14 L10.5 14" />
            <path d="M6 12 L6 10.5 Q4 9 4 6.5 Q4 3 8 2 Q12 3 12 6.5 Q12 9 10 10.5 L10 12 Z" fill="none" />
          </svg>
          <!-- @claude Event fired: lit bulb. -->
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

        <!-- @claude Zoom in/out. -->
        <button class="toolbar-btn" @click="toggleFullscreen" :title="fullscreen ? '축소' : '확대'">
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
</template>

<style scoped>
.video-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  flex-shrink: 0;
}
.video-header .video-label {
  margin-bottom: 0;
}

.protocol-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  user-select: none;
  transition: opacity 0.15s;
}
.protocol-toggle.disabled {
  cursor: default;
  pointer-events: none;
  opacity: 0.4;
}
.protocol-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-4);
  transition: color 0.15s;
}
.protocol-label.active {
  color: var(--accent);
}
.toggle-track {
  width: 32px;
  height: 16px;
  border-radius: 8px;
  background: var(--bar-bg);
  position: relative;
  transition: background 0.2s;
}
.toggle-track.on {
  background: var(--accent);
}
.toggle-thumb {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #fff;
  position: absolute;
  top: 2px;
  left: 2px;
  transition: transform 0.2s;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}
.toggle-track.on .toggle-thumb {
  transform: translateX(16px);
}

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
.video-wrap:fullscreen {
  background: #000;
}
.video-wrap:fullscreen video {
  border: none;
  border-radius: 0;
  box-shadow: none;
}
.session-remaining-badge {
  position: absolute;
  top: 8px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 4;
  min-width: 132px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(0, 0, 0, 0.65);
  color: rgba(255, 255, 255, 0.9);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.2px;
  text-align: center;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
.protocol-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 4;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.65);
  color: rgba(255, 255, 255, 0.82);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.2px;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
.pipeline-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 4;
  max-width: calc(100% - 16px);
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.65);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: rgba(255, 255, 255, 0.82);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.2px;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
.pipeline-badge.pipeline-ok {
  border-color: rgba(74, 222, 128, 0.35);
  color: rgba(187, 247, 208, 1);
}
.pipeline-badge.pipeline-warn {
  border-color: rgba(251, 191, 36, 0.35);
  color: rgba(253, 224, 71, 1);
}
.pipeline-badge.pipeline-err {
  border-color: rgba(248, 113, 113, 0.35);
  color: rgba(254, 202, 202, 1);
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
.video-overlay.clickable {
  cursor: pointer;
}
.video-overlay.clickable:hover .play-icon svg circle {
  stroke: rgba(255, 255, 255, 0.7);
}
.video-overlay.clickable:hover .play-icon {
  transform: scale(1.08);
}
.play-icon {
  transition: transform 0.15s;
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
  font-size: 13px;
  color: rgba(255, 255, 255, 0.7);
  font-weight: 500;
}
.overlay-text.timeout {
  color: var(--danger);
}
.overlay-subtext {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.55);
  text-align: center;
  max-width: 360px;
  line-height: 1.5;
  padding: 0 16px;
}

.retry-btn {
  font-size: 12px;
  font-weight: 600;
  padding: 6px 16px;
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: var(--radius);
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.8);
  cursor: pointer;
  transition: background 0.15s;
}
.retry-btn:hover {
  background: rgba(255, 255, 255, 0.2);
}

/* @claude Unified bottom bar: infer-area + video-toolbar group. */
.video-bar {
  position: absolute;
  bottom: 8px;
  right: 8px;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
  z-index: 5;
}
.infer-triggered {
  background: rgba(255, 220, 50, 0.25);
}

.toolbar-btn {
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.toolbar-btn:hover {
  background: rgba(255, 255, 255, 0.16);
  color: rgba(255, 255, 255, 1);
}
.toolbar-btn-disabled {
  color: rgba(255, 255, 255, 0.25);
  cursor: default;
  pointer-events: none;
}

/* @claude Panel area (above the unified bar). */
.toolbar-panels {
  position: absolute;
  bottom: 60px;
  right: 8px;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  z-index: 5;
  pointer-events: none;
}
.toolbar-panels > * {
  pointer-events: auto;
}

.stats-panel {
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(8px);
  border-radius: 6px;
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  pointer-events: none;
}
.stats-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}
.stats-key {
  font-size: 0.8rem;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.5);
  white-space: nowrap;
}
.stats-val {
  font-size: 0.8rem;
  font-weight: 700;
  font-family: var(--font-mono);
  color: rgba(255, 255, 255, 0.9);
  white-space: nowrap;
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
