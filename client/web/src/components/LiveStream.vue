<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useCamera } from '../composables/useCamera.js'
import { useAuth } from '../composables/useAuth.js'
import { useLocale } from '../composables/useLocale.js'
import { useSSE } from '../composables/useSSE.js'
import { useStreamProtocol } from '../composables/useStreamProtocol.js'
import InferenceOverlay from './InferenceOverlay.vue'
import StatCards from './StatCards.vue'
import { useStreamStats } from '../composables/useStreamStats.js'
import { getHlsUrl, getWhepUrl } from '../endpoints.js'
import { usePtz } from '../composables/usePtz.js'

const emit = defineEmits(['open-prompt'])

const {
  state: sseState,
  pipelineStateLabel,
  pipelineDetailLabel,
} = useSSE()
const { t } = useLocale()

const { accessToken } = useAuth()
const { configured, connecting, connected, ptzEnabled, setConnected, setDisconnected, disconnect } = useCamera()

// @claude Profile save no longer touches playback: registration does not
// @claude change the stream (FR-048), so the old save-triggered reconnect
// @claude only produced a black flash — or started playback the user had
// @claude stopped.

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
const loading = ref(false)
const stopped = ref(true)
const fullscreen = ref(false)
const inferOpen = ref(false)
const ptzControlOpen = ref(false)

// ── Toolbar PTZ ──
const { startMove, stopMove, saveHome, gotoHome } = usePtz()
const ptzPressing = ref(null)
const saveState = ref(null) // null | 'saving' | 'ok' | 'fail'
let saveResetTimer = null

async function handleSaveHome() {
  if (!canUseToolbarPtz.value) return
  if (saveState.value === 'saving') return
  saveState.value = 'saving'
  const ok = await saveHome()
  saveState.value = ok ? 'ok' : 'fail'
  if (saveResetTimer) clearTimeout(saveResetTimer)
  saveResetTimer = setTimeout(() => { saveState.value = null }, 1500)
}

// @claude The 3x3 pad renders row-wise; null cells are decorative spacers and
// @claude the center cell is the crosshair.
const ptzDirs = [
  { id: 'up',    pan:  0, tilt:  1, icon: 'ph ph-caret-up' },
  { id: 'down',  pan:  0, tilt: -1, icon: 'ph ph-caret-down' },
  { id: 'left',  pan: -1, tilt:  0, icon: 'ph ph-caret-left' },
  { id: 'right', pan:  1, tilt:  0, icon: 'ph ph-caret-right' },
]
const ptzPad = [
  null, ptzDirs[0], null,
  ptzDirs[2], { id: 'center', icon: 'ph ph-crosshair' }, ptzDirs[3],
  null, ptzDirs[1], null,
]

function ptzDown(dir, event) {
  if (!canUseToolbarPtz.value) return
  event.preventDefault()
  ptzPressing.value = dir.id
  startMove(dir.pan, dir.tilt)
}

function ptzUp(dir) {
  if (ptzPressing.value !== dir.id) return
  ptzPressing.value = null
  stopMove()
}

function stopToolbarPtzMotion() {
  if (ptzPressing.value == null) return
  ptzPressing.value = null
  stopMove()
}

function handleToolbarGotoHome() {
  if (!canUseToolbarPtz.value) return
  gotoHome()
}

function stopActivePtzMotion() {
  stopToolbarPtzMotion()
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
let retryTimer = null
let pipelineRecoveryTimer = null
let pc = null
let sessionId = 0
const STALL_TIMEOUT = 8000
const RETRY_BACKOFF = 3000

// @claude The preference is shared with the dashboard top bar's pill.
const { preferredProtocol } = useStreamProtocol()
const activeProtocol = ref(preferredProtocol.value)
const isWebRTC = computed(() => activeProtocol.value === 'webrtc')
const isPlaying = computed(() => connected.value && !loading.value && !stopped.value)
const showToolbarPtz = computed(() => ptzEnabled.value && !stopped.value)
const canUseToolbarPtz = computed(() => showToolbarPtz.value && isPlaying.value)
watch(canUseToolbarPtz, (nextValue) => {
  if (nextValue) return
  stopToolbarPtzMotion()
  ptzControlOpen.value = false
})

watch(preferredProtocol, (protocol) => {
  activeProtocol.value = protocol
  if (stopped.value) return
  restartStream()
})

const { stats, startStats, stopStats } = useStreamStats({
  videoRef,
  isWebRTC,
  getPeerConnection: () => pc,
  getHlsInstance: () => hls,
})

function handleConnect() {
  stopped.value = false
  connecting.value = true
  resetRuntimeProtocol()
  restartStream()
}

function handleDisconnect() {
  stopActivePtzMotion()
  ptzControlOpen.value = false
  inferOpen.value = false
  stopped.value = true
  destroyAll()
  disconnect()
}

function resetRuntimeProtocol() {
  activeProtocol.value = preferredProtocol.value
}

function restartStream({ resetProtocol = false } = {}) {
  if (resetProtocol) resetRuntimeProtocol()
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
}

function clearAllTimers() {
  if (stallTimer) { clearInterval(stallTimer); stallTimer = null }
  if (retryTimer) { clearTimeout(retryTimer); retryTimer = null }
  if (pipelineRecoveryTimer) { clearTimeout(pipelineRecoveryTimer); pipelineRecoveryTimer = null }
}

function browserPlaybackUnavailable() {
  return !configured.value || stopped.value || loading.value
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

function clearVideoElementMedia() {
  const video = videoRef.value
  if (!video) return
  video.pause()
  video.srcObject = null
  video.removeAttribute('src')
  video.load()
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
      // @claude The HLS relay sits behind the router and every request —
      // @claude playlist and segments alike — must carry the access token.
      xhrSetup: (xhr) => {
        if (accessToken.value) xhr.setRequestHeader('Authorization', `Bearer ${accessToken.value}`)
      },
    })
    hls.loadSource(getHlsUrl())
    hls.attachMedia(video)
    hls.on(HlsLib.Events.MANIFEST_PARSED, () => { video.play().catch(() => {}) })
    hls.on(HlsLib.Events.ERROR, (_, data) => {
      if (!data.fatal || mySession !== sessionId) return
      retryTimer = setTimeout(() => {
        if (mySession === sessionId) initHls()
      }, RETRY_BACKOFF)
    })
  } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
    // @claude Native HLS cannot set headers; the token rides the playlist URL.
    // @claude Segment requests do not inherit it, so native-only browsers are
    // @claude limited — hls.js above is the supported path.
    video.src = `${getHlsUrl()}?token=${encodeURIComponent(accessToken.value || '')}`
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
      } else if (state === 'failed' || state === 'disconnected' || state === 'closed') {
        handleWebRTCConnectionLoss(mySession)
      }
    }

    const offer = await pc.createOffer()
    if (mySession !== sessionId) return
    await pc.setLocalDescription(offer)
    await waitForIceGathering(pc)
    if (mySession !== sessionId) return

    const res = await fetch(getWhepUrl(), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/sdp',
        // @claude WHEP signaling passes the router relay and needs the token;
        // @claude the WebRTC media itself then flows directly (UDP 8890).
        ...(accessToken.value ? { Authorization: `Bearer ${accessToken.value}` } : {}),
      },
      body: pc.localDescription.sdp,
    })
    if (mySession !== sessionId) return
    if (!res.ok) throw new Error(`WHEP ${res.status}`)

    const answerSdp = await res.text()
    await pc.setRemoteDescription(new RTCSessionDescription({ type: 'answer', sdp: answerSdp }))
  } catch (e) {
    if (mySession !== sessionId) return
    retryTimer = setTimeout(() => {
      if (mySession === sessionId) initWebRTC()
    }, RETRY_BACKOFF)
  }
}

function handleWebRTCConnectionLoss(mySession) {
  if (mySession !== sessionId) return
  clearVideoElementMedia()
  stopStats()
  setDisconnected()
  if (stopped.value) return
  loading.value = true
  if (retryTimer) clearTimeout(retryTimer)
  retryTimer = setTimeout(() => {
    if (mySession === sessionId) initWebRTC()
  }, RETRY_BACKOFF)
}

function destroyWebRTC() {
  if (pc) {
    pc.ontrack = null
    pc.onconnectionstatechange = null
    pc.close()
    pc = null
  }
  clearVideoElementMedia()
}

// ── Common handlers ──

function onPlaying() {
  loading.value = false
  setConnected()
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
  <div class="live">

    <!-- ── Video ── -->
    <div ref="videoWrapRef" class="video-card">
      <video ref="videoRef" muted playsinline />

      <span v-if="isPlaying" class="live-badge"><span class="live-dot"></span>LIVE</span>

      <button
        class="fs-btn"
        :title="fullscreen ? t('live.fullscreen.exit') : t('live.fullscreen.enter')"
        @click="toggleFullscreen"
      >
        <i :class="fullscreen ? 'ph ph-corners-in' : 'ph ph-corners-out'"></i>
      </button>

      <InferenceOverlay :open="inferOpen && isPlaying" />

      <button v-if="stopped" class="video-overlay" @click="handleConnect">
        <span class="play-ring"><i class="ph-fill ph-play"></i></span>
        <span class="overlay-text">{{ t('live.connectIdle') }}</span>
      </button>

      <button v-else-if="loading" class="video-overlay" @click="handleDisconnect">
        <span class="spinner"></span>
        <span class="overlay-text">{{ t('live.connectingCancel', { protocol: activeProtocol.toUpperCase() }) }}</span>
      </button>
    </div>

    <!-- ── Status line ── -->
    <div class="status-line">
      <span class="pipe">
        <span class="pipe-dot" :class="{ on: isPlaying }"></span>{{ pipelineStateLabel }}
      </span>
      <template v-if="pipelineDetailLabel">
        <span class="sep">·</span><span>{{ pipelineDetailLabel }}</span>
      </template>
      <span class="metrics">{{ stats.resolution || '–' }} · {{ stats.fps || 0 }} FPS</span>
    </div>

    <!-- ── Toolbar ── -->
    <div class="tool-row">
      <button
        class="tool-btn"
        :class="{ on: inferOpen && isPlaying }"
        :disabled="!isPlaying"
        @click="inferOpen = !inferOpen"
      >
        <i :class="sseState.event_triggered && isPlaying ? 'ph-fill ph-lightbulb' : 'ph ph-lightbulb'"></i>
        {{ t('live.inference') }}
      </button>
      <button class="tool-btn" @click="emit('open-prompt')">
        <i class="ph ph-chat-text"></i>{{ t('dashboard.menu.promptShort') }}
      </button>
      <button
        v-if="ptzEnabled"
        class="tool-btn"
        :class="{ on: ptzControlOpen }"
        :disabled="!canUseToolbarPtz"
        @click="ptzControlOpen = !ptzControlOpen"
      >
        <i class="ph ph-arrows-out-cardinal"></i>PTZ
      </button>
      <button class="tool-btn" :disabled="stopped" @click="handleDisconnect">
        <i class="ph ph-plugs"></i>{{ t('live.disconnect') }}
      </button>
    </div>

    <!-- ── Hardware ── -->
    <StatCards />

    <!-- ── PTZ pad ── -->
    <div v-if="ptzControlOpen && canUseToolbarPtz" class="ptz-card">
      <div class="ptz-pad">
        <template v-for="(cell, i) in ptzPad" :key="i">
          <span v-if="!cell" class="ptz-cell empty"></span>
          <span v-else-if="cell.id === 'center'" class="ptz-cell center"><i :class="cell.icon"></i></span>
          <button
            v-else
            class="ptz-cell"
            :class="{ pressing: ptzPressing === cell.id }"
            :title="t(`live.ptz.${cell.id}`)"
            @mousedown="(e) => ptzDown(cell, e)"
            @mouseup="ptzUp(cell)"
            @mouseleave="ptzUp(cell)"
            @touchstart.prevent="(e) => ptzDown(cell, e)"
            @touchend="ptzUp(cell)"
          >
            <i :class="cell.icon"></i>
          </button>
        </template>
      </div>
      <div class="ptz-side">
        <span class="ptz-label">PTZ</span>
        <button
          class="ptz-action primary"
          :class="{ ok: saveState === 'ok', fail: saveState === 'fail' }"
          :disabled="saveState === 'saving'"
          @click="handleSaveHome"
        >{{ t('live.ptz.saveHome') }}</button>
        <button class="ptz-action" @click="handleToolbarGotoHome">{{ t('live.ptz.gotoHome') }}</button>
      </div>
    </div>

  </div>
</template>

<style scoped>
.live {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* — video — */
.video-card {
  position: relative;
  aspect-ratio: 16 / 9;
  border-radius: 10px;
  overflow: hidden;
  background: linear-gradient(160deg, #10121c 0%, #1a1d2e 55%, #0d0f18 100%);
}
.video-card video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.live-badge {
  position: absolute;
  top: 12px;
  left: 14px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  letter-spacing: 0.1em;
  color: #e9e9ed;
  background: rgba(0, 0, 0, 0.45);
  padding: 5px 9px;
  border-radius: 5px;
  backdrop-filter: blur(6px);
}
.live-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #e05b6a;
}
.fs-btn {
  position: absolute;
  top: 12px;
  right: 14px;
  width: 34px; height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 17px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(0, 0, 0, 0.42);
  backdrop-filter: blur(8px);
  color: #e9e9ed;
  font-size: 15px;
  cursor: pointer;
  z-index: 5;
}
.video-overlay {
  position: absolute;
  inset: 0;
  border: none;
  background: rgba(10, 11, 18, 0.55);
  color: #e9e9ed;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  cursor: pointer;
  font-family: inherit;
  z-index: 4;
}
.play-ring {
  width: 70px; height: 70px;
  border-radius: 50%;
  border: 1px solid var(--color-accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 30px;
  color: var(--color-accent);
}
.spinner {
  width: 38px; height: 38px;
  border-radius: 50%;
  border: 2px solid var(--color-neutral-800);
  border-top-color: var(--color-accent);
  animation: live-spin 900ms linear infinite;
}
@keyframes live-spin { to { transform: rotate(360deg); } }
.overlay-text {
  font-size: 13px;
  color: var(--color-neutral-400);
}

/* — status line — */
.status-line {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 32px;
  font-size: 11.5px;
  color: var(--color-neutral-500);
  border-bottom: 1px solid var(--color-divider);
}
.pipe {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text);
}
.pipe-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--color-neutral-600);
}
.pipe-dot.on { background: #5fbf8a; }
.sep { color: var(--color-neutral-700); }
.metrics {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}

/* — toolbar — */
.tool-row {
  display: flex;
  gap: 10px;
}
.tool-btn {
  flex: 1;
  height: 48px;
  border-radius: 8px;
  border: 1px solid var(--color-neutral-800);
  background: transparent;
  color: var(--color-text);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-family: inherit;
  font-size: 13px;
}
.tool-btn i { font-size: 17px; }
.tool-btn:hover:not(:disabled) { border-color: var(--color-accent); }
.tool-btn.on {
  background: color-mix(in srgb, var(--color-accent) 16%, transparent);
  color: var(--color-accent);
  border-color: var(--color-accent);
}
.tool-btn:disabled { opacity: 0.45; cursor: default; }

/* — PTZ card — */
.ptz-card {
  border: 1px solid var(--color-neutral-800);
  border-radius: 8px;
  padding: 14px;
  display: flex;
  gap: 16px;
  align-items: center;
  background: var(--color-neutral-900);
}
.ptz-pad {
  display: grid;
  grid-template-columns: repeat(3, 44px);
  grid-template-rows: repeat(3, 44px);
  gap: 5px;
}
.ptz-cell {
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: var(--color-neutral-900);
  border-radius: 7px;
  color: var(--color-text);
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.ptz-cell.empty,
.ptz-cell.center {
  border-color: transparent;
  background: transparent;
  cursor: default;
}
.ptz-cell.center { color: var(--color-neutral-500); }
.ptz-cell.pressing {
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 16%, transparent);
}
.ptz-side {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 220px;
  flex: 1;
}
.ptz-label {
  font-size: 11px;
  color: var(--color-neutral-500);
  letter-spacing: 0.06em;
}
.ptz-action {
  height: 38px;
  border-radius: 7px;
  border: 1px solid var(--color-neutral-800);
  background: none;
  color: var(--color-text);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
}
.ptz-action.primary {
  border-color: var(--color-accent);
  color: var(--color-accent);
}
.ptz-action.primary.ok { border-color: #5fbf8a; color: #5fbf8a; }
.ptz-action.primary.fail { border-color: var(--danger); color: var(--danger); }
.ptz-action:hover:not(:disabled) { background: color-mix(in srgb, var(--color-text) 6%, transparent); }
</style>
