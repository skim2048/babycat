<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import Hls from 'hls.js'
import { useCamera } from '../composables/useCamera.js'
import { useSSE } from '../composables/useSSE.js'
import SystemOverlay from './SystemOverlay.vue'
import PtzOverlay from './PtzOverlay.vue'
import InferenceOverlay from './InferenceOverlay.vue'

const { state: sseState } = useSSE()

const { config, configured, connecting, connected, reconnectKey, setConnected, setDisconnected, disconnect, save: saveCamera } = useCamera()

// 카메라 프로필 저장 성공 시 자동 재연결 (타임아웃 상태에서도 복구)
watch(reconnectKey, () => {
  if (!configured.value) return
  stopCountdown()
  destroyAll()
  handleConnect()
})

const hasOnvif = computed(() => !!config.onvif_port)

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
let stallTimer = null
let timeoutTimer = null
let retryTimer = null
let countdownTimer = null
let pc = null
let sessionId = 0
let connectDeadline = 0
const remainingSec = ref(0)
const STALL_TIMEOUT = 8000
const CONNECT_TIMEOUT = 15000

const isWebRTC = computed(() => config.stream_protocol === 'webrtc')
const isPlaying = computed(() => connected.value && !loading.value && !timedOut.value && !stopped.value)

function toggleProtocol() {
  config.stream_protocol = isWebRTC.value ? 'hls' : 'webrtc'
  saveCamera()
  if (configured.value && !stopped.value) {
    restartStream()
  }
}

function handleConnect() {
  stopped.value = false
  connecting.value = true
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

function getHlsUrl() {
  const host = window.location.hostname
  return `http://${host}:8888/live/index.m3u8`
}

function getWhepUrl() {
  const host = window.location.hostname
  return `http://${host}:8889/live/whep`
}

// ── Lifecycle ──

function restartStream() {
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

// ── HLS ──

function initHls() {
  const mySession = ++sessionId
  clearAllTimers()
  destroyHls()
  destroyWebRTC()
  loading.value = true
  timedOut.value = false

  const video = videoRef.value
  if (!video) return

  if (Hls.isSupported()) {
    hls = new Hls({
      liveSyncDurationCount: 1,
      liveMaxLatencyDurationCount: 3,
      maxBufferLength: 3,
      maxMaxBufferLength: 6,
    })
    hls.loadSource(getHlsUrl())
    hls.attachMedia(video)
    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      video.play().catch(() => {})
    })
    hls.on(Hls.Events.ERROR, (_, data) => {
      if (data.fatal && mySession === sessionId && Date.now() < connectDeadline) {
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

  // 해상도 (공통)
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
        // FPS
        if (r.framesPerSecond != null) {
          stats.fps = `${Math.round(r.framesPerSecond)}`
        }
        // 비트레이트
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
        // 코덱
        if (r.codecId && codecs[r.codecId]) {
          const c = codecs[r.codecId]
          stats.codec = c.mimeType ? c.mimeType.replace('video/', '') : ''
        }
        // 패킷 손실
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
  // FPS
  if (level && level.attrs && level.attrs['FRAME-RATE']) {
    stats.fps = `${Math.round(parseFloat(level.attrs['FRAME-RATE']))}`
  }
  // 비트레이트
  if (hls.bandwidthEstimate) {
    const bps = hls.bandwidthEstimate
    if (bps >= 1_000_000) {
      stats.bitrate = `${(bps / 1_000_000).toFixed(1)} Mbps`
    } else {
      stats.bitrate = `${Math.round(bps / 1000)} kbps`
    }
  }
  // 코덱
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
      <div class="protocol-toggle" @click="toggleProtocol">
        <span class="protocol-label" :class="{ active: !isWebRTC }">HLS</span>
        <div class="toggle-track" :class="{ on: isWebRTC }">
          <div class="toggle-thumb" />
        </div>
        <span class="protocol-label" :class="{ active: isWebRTC }">WebRTC</span>
      </div>
    </div>
    <div class="video-wrap" ref="videoWrapRef">
      <video ref="videoRef" muted playsinline />

      <!-- 연결 대기중: 재생 아이콘 클릭으로 연결 -->
      <div v-if="stopped" class="video-overlay clickable" @click="handleConnect">
        <div class="play-icon">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <circle cx="24" cy="24" r="23" stroke="rgba(255,255,255,0.4)" stroke-width="2"/>
            <polygon points="19,14 19,34 36,24" fill="rgba(255,255,255,0.85)"/>
          </svg>
        </div>
        <span class="overlay-text">연결 대기중</span>
      </div>

      <!-- 연결 중 -->
      <div v-else-if="loading" class="video-overlay">
        <div class="spinner" />
        <span class="overlay-text">연결 중... {{ remainingSec }}초</span>
      </div>

      <!-- 연결 시간 초과 -->
      <div v-else-if="timedOut" class="video-overlay">
        <span class="overlay-text timeout">네트워크 상태 또는 카메라 프로필을 확인하세요.</span>
        <button class="retry-btn" @click="handleConnect">재연결</button>
      </div>


      <!-- 하단 중앙: 추론 결과 패널 -->
      <InferenceOverlay :open="inferOpen && isPlaying" />

      <!-- 좌하단: 추론 결과 토글 버튼 -->
      <div class="infer-area">
        <button class="toolbar-btn infer-btn" :class="{ 'infer-triggered': sseState.event_triggered }" @click.stop="inferOpen = !inferOpen" title="추론 결과">
          <!-- 평상시: 꺼진 전구 -->
          <svg v-if="!sseState.event_triggered" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5.5 14 L10.5 14" />
            <path d="M6 12 L6 10.5 Q4 9 4 6.5 Q4 3 8 2 Q12 3 12 6.5 Q12 9 10 10.5 L10 12 Z" fill="none" />
          </svg>
          <!-- 이벤트 발생: 켜진 전구 -->
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
      </div>

      <!-- 우하단 패널 영역 -->
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
          </div>
        </Transition>

        <PtzOverlay v-if="hasOnvif" :open="activePanel === 'ptz' && isPlaying" />
      </div>

      <!-- 우하단 툴바 -->
      <div class="video-toolbar">
        <!-- 시스템 모니터 (파형 시그널 아이콘) -->
        <button class="toolbar-btn" @click.stop="togglePanel('sys')" title="시스템 모니터">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <polyline points="1,8 3,8 5,3 7,13 9,5 11,11 13,7 15,8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
          </svg>
        </button>

        <!-- 송수신 정보 (교차 화살표 아이콘) -->
        <button class="toolbar-btn" @click.stop="togglePanel('stats')" title="송수신 정보">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="5" y1="1" x2="5" y2="15" />
            <polyline points="2,4 5,1 8,4" />
            <line x1="11" y1="15" x2="11" y2="1" />
            <polyline points="8,12 11,15 14,12" />
          </svg>
        </button>

        <!-- PTZ 조작 -->
        <button v-if="hasOnvif" class="toolbar-btn" @click.stop="togglePanel('ptz')" title="PTZ 조작">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <circle cx="8" cy="8" r="3" fill="none"/>
            <line x1="8" y1="1" x2="8" y2="4" />
            <line x1="8" y1="12" x2="8" y2="15" />
            <line x1="1" y1="8" x2="4" y2="8" />
            <line x1="12" y1="8" x2="15" y2="8" />
          </svg>
        </button>

        <!-- 연결 해제 -->
        <button
          class="toolbar-btn"
          :class="isPlaying ? 'toolbar-btn-danger' : 'toolbar-btn-disabled'"
          :disabled="!isPlaying"
          @click="handleDisconnect"
          title="연결 해제"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="3" y1="3" x2="13" y2="13" />
            <line x1="13" y1="3" x2="3" y2="13" />
          </svg>
        </button>

        <!-- 확대/축소 -->
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

/* 좌하단: 추론 결과 */
.infer-area {
  position: absolute;
  bottom: 8px;
  left: 8px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  z-index: 5;
}
.infer-btn {
  align-self: flex-start;
}
.infer-triggered {
  background: rgba(255, 220, 50, 0.25);
}

/* 우하단 툴바 */
.video-toolbar {
  position: absolute;
  bottom: 8px;
  right: 8px;
  display: flex;
  gap: 4px;
  z-index: 5;
}
.toolbar-btn {
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.5);
  color: rgba(255, 255, 255, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.toolbar-btn:hover {
  background: rgba(0, 0, 0, 0.75);
  color: rgba(255, 255, 255, 1);
}
.toolbar-btn-danger {
  color: rgba(255, 255, 255, 0.7);
}
.toolbar-btn-danger:hover {
  background: rgba(208, 56, 56, 0.7);
  color: rgba(255, 255, 255, 0.95);
}
.toolbar-btn-disabled {
  color: rgba(255, 255, 255, 0.2);
  cursor: default;
  pointer-events: none;
}

/* 패널 영역 (툴바 위) */
.toolbar-panels {
  position: absolute;
  bottom: 46px;
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
