<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useCamera } from '../composables/useCamera.js'
import { useAuth } from '../composables/useAuth.js'
import { useLocale } from '../composables/useLocale.js'
import { useSSE } from '../composables/useSSE.js'
import { useStreamProtocol } from '../composables/useStreamProtocol.js'
import { useInferLog } from '../composables/useInferLog.js'
import { useVlmStatus } from '../composables/useVlmStatus.js'
import { useStreamStats } from '../composables/useStreamStats.js'
import { getHlsUrl, getWhepUrl } from '../endpoints.js'
import { usePtz } from '../composables/usePtz.js'

const {
  state: sseState,
  pipelineStateLabel,
  pipelineDetailLabel,
} = useSSE()
const { t } = useLocale()

const { accessToken, isAuthenticated, isPersistentSession, sessionRemainingSeconds } = useAuth()
const { configured, connecting, connected, ptzEnabled, setConnected, setDisconnected, disconnect } = useCamera()
const { entries: inferLog } = useInferLog()
const { vlmDot, vlmLabel } = useVlmStatus()

// @claude Profile save no longer touches playback: registration does not
// @claude change the stream, so the old save-triggered reconnect
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

// ── Fullscreen chrome (커스텀 오버레이 + 접이식 로그 패널) ──
const fsLog = ref(true)
const showSessionRemaining = computed(() =>
  isAuthenticated.value && !isPersistentSession.value && sessionRemainingSeconds.value > 0,
)
const sessionRemainingText = computed(() => {
  const total = sessionRemainingSeconds.value
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
})
const protocolOptions = [
  { key: 'hls', label: 'HLS' },
  { key: 'webrtc', label: 'WebRTC' },
]

function fsLocalDate(offsetDays = 0) {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// @claude 날짜 구분선 규칙은 대시보드 로그 패널과 동일: 오늘 생략, 어제는
// @claude 문구, 그 이전은 YY-MM-DD.
const fsLogEntries = computed(() => {
  const today = fsLocalDate()
  const yesterday = fsLocalDate(-1)
  let prevDay = null
  return inferLog.map((entry) => {
    let header = null
    if (entry.day !== prevDay && entry.day !== today) {
      header = entry.day === yesterday ? t('dashboard.day.yesterday') : entry.day.slice(2)
    }
    prevDay = entry.day
    return { ...entry, header }
  })
})

// ── PTZ panel ──
const { speedLevel, setSpeedLevel, startMove, stopMove, savePreset, gotoPreset } = usePtz()
const ptzPressing = ref(null)
const ptzSaveMode = ref(false)
const ptzMessage = ref('') // '' | 'saveFailed' | 'gotoEmpty'

const savedSlots = computed(() => new Set(sseState.ptz_presets || []))

const ptzDirs = [
  { id: 'up',    pan:  0, tilt:  1, icon: 'ph ph-caret-up' },
  { id: 'down',  pan:  0, tilt: -1, icon: 'ph ph-caret-down' },
  { id: 'left',  pan: -1, tilt:  0, icon: 'ph ph-caret-left' },
  { id: 'right', pan:  1, tilt:  0, icon: 'ph ph-caret-right' },
]

function ptzDown(dir, event) {
  if (ptzOff.value) return
  event.preventDefault()
  ptzPressing.value = dir.id
  startMove(dir.pan, dir.tilt)
}

function ptzUp(dir) {
  if (ptzPressing.value !== dir.id) return
  ptzPressing.value = null
  stopMove()
}

function stopPtzMotion() {
  if (ptzPressing.value == null) return
  ptzPressing.value = null
  stopMove()
}

// @claude 패드 가운데의 정지 버튼: 누름 상태와 무관하게 즉시 Stop을 보낸다.
function ptzStopNow() {
  if (ptzOff.value) return
  ptzPressing.value = null
  stopMove()
}

async function onPresetClick(slot) {
  if (ptzOff.value) return
  ptzMessage.value = ''
  if (ptzSaveMode.value) {
    const ok = await savePreset(slot)
    if (!ok) ptzMessage.value = 'saveFailed'
    ptzSaveMode.value = false
  } else {
    const ok = await gotoPreset(slot)
    if (!ok) ptzMessage.value = 'gotoEmpty'
  }
}

const ptzHint = computed(() => {
  if (ptzMessage.value === 'saveFailed') return t('live.ptz.saveFailed')
  if (ptzMessage.value === 'gotoEmpty') return t('live.ptz.gotoEmpty')
  return ptzSaveMode.value ? t('live.ptz.saveHint') : t('live.ptz.gotoHint')
})

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
// @claude 8 s without currentTime advancing: longer than one HLS segment plus
// @claude jitter, so a healthy live stream is never mistaken for a stall.
const STALL_TIMEOUT = 8000
// @claude 3 s between retries: lets the relay recover without hammering it.
const RETRY_BACKOFF = 3000
// @claude 1.25 s after the pipeline reports streaming again: enough for the
// @claude first new segment to reach the player before deciding to reconnect.
const PIPELINE_RECOVERY_DELAY = 1250

// @claude The preference is shared with the dashboard top bar's pill.
const { preferredProtocol, setProtocol } = useStreamProtocol()
const activeProtocol = ref(preferredProtocol.value)
const isWebRTC = computed(() => activeProtocol.value === 'webrtc')
const isPlaying = computed(() => connected.value && !loading.value && !stopped.value)

// @claude 낙관적 활성 정책: 사전 비활성은 스트림 미연결과
// @claude PTZ 포트 미입력뿐이다. 명령 실패는 잠그지 않고 안내 줄로만 알린다.
// @claude isPlaying 선언 뒤에 있어야 한다 — watch가 setup 중에 초기값을 즉시
// @claude 평가하므로, 앞에 두면 TDZ 참조로 마운트가 실패한다.
const ptzOff = computed(() => !ptzEnabled.value || !isPlaying.value)
watch(ptzOff, (off) => {
  if (!off) return
  stopPtzMotion()
  ptzSaveMode.value = false
  ptzMessage.value = ''
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
  stopPtzMotion()
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
  }, PIPELINE_RECOVERY_DELAY)
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

  // @claude hls.js is the only HLS path: segment requests must carry the
  // @claude access token in a header, which native HLS playback cannot do.
  if (!HlsLib || !HlsLib.isSupported()) {
    console.warn('hls.js is unavailable in this browser; HLS playback is not possible')
    handleDisconnect()
    return
  }
  hls = new HlsLib({
    // @claude Low-latency live tuning: sit 1 segment behind the live edge,
    // @claude jump forward past 3, and keep the forward buffer at 3 s (6 s
    // @claude hard cap) so a stall shows up quickly instead of playing old video.
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
        // @claude the WebRTC media itself then flows directly (UDP 8189).
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
  stopPtzMotion()
  destroyAll()
  document.removeEventListener('fullscreenchange', onFullscreenChange)
})
</script>

<template>
  <div class="live">

    <!-- ── Video ── -->
    <div ref="videoWrapRef" class="video-card" :class="{ 'fs-open': fullscreen && fsLog }">
      <video ref="videoRef" muted playsinline />

      <span class="fs-topleft">
        <span v-if="isPlaying" class="live-badge"><span class="live-dot"></span>LIVE</span>
        <span v-if="fullscreen && isPlaying" class="fs-status">
          {{ pipelineStateLabel }} · {{ stats.resolution || '–' }} · {{ stats.fps || 0 }} FPS
        </span>
      </span>

      <button v-if="stopped" class="video-overlay" @click="handleConnect">
        <span class="play-ring"><i class="ph ph-play"></i></span>
        <span class="overlay-text">{{ t('live.connectIdle') }}</span>
      </button>

      <button v-else-if="loading" class="video-overlay" @click="handleDisconnect">
        <span class="spinner"></span>
        <span class="overlay-text">{{ t('live.connectingCancel', { protocol: activeProtocol.toUpperCase() }) }}</span>
      </button>

      <!-- 축소 화면: 연결 해제 + 전체 화면 -->
      <div v-if="!fullscreen" class="video-actions">
        <button
          v-if="isPlaying"
          class="video-action"
          :title="t('live.disconnect')"
          @click="handleDisconnect"
        ><i class="ph ph-plugs"></i></button>
        <button
          class="video-action"
          :title="t('live.fullscreen.enter')"
          @click="toggleFullscreen"
        ><i class="ph ph-corners-out"></i></button>
      </div>

      <!-- 전체 화면: 세션 · 프로토콜 · 연결 해제 · 로그 패널 · 종료 -->
      <div v-else class="fs-cluster">
        <span v-if="showSessionRemaining" class="fs-chip">
          <i class="ph ph-clock"></i>{{ sessionRemainingText }}
        </span>
        <!-- 알약의 어느 부분을 눌러도 반대 프로토콜로 전환된다 -->
        <button
          class="fs-pill"
          role="switch"
          :aria-checked="preferredProtocol === 'webrtc'"
          :aria-label="t('live.protocolToggle')"
          @click="setProtocol(preferredProtocol === 'hls' ? 'webrtc' : 'hls')"
        >
          <span
            v-for="p in protocolOptions"
            :key="p.key"
            class="fs-pill-opt"
            :class="{ active: preferredProtocol === p.key }"
          >{{ p.label }}</span>
        </button>
        <button
          v-if="isPlaying"
          class="fs-round"
          :title="t('live.disconnect')"
          @click="handleDisconnect"
        ><i class="ph ph-plugs"></i></button>
        <button
          class="fs-round"
          :class="{ on: fsLog }"
          :title="t('dashboard.panel.log')"
          :aria-pressed="fsLog"
          @click="fsLog = !fsLog"
        ><i class="ph ph-list-dashes"></i></button>
        <button
          class="fs-round"
          :title="t('live.fullscreen.exit')"
          @click="toggleFullscreen"
        ><i class="ph ph-corners-in"></i></button>
      </div>

      <!-- 전체 화면: 접이식 세션 로그 패널 -->
      <aside v-if="fullscreen && fsLog" class="fs-log">
        <div class="fs-log-head">
          <span class="fs-vlm">
            <span class="fs-vlm-dot" :style="{ background: vlmDot }"></span>{{ vlmLabel }}
          </span>
          <button class="fs-log-x" @click="fsLog = false"><i class="ph ph-x"></i></button>
        </div>
        <div class="fs-log-list">
          <div v-if="!fsLogEntries.length" class="fs-log-none">{{ t('dashboard.log.waiting') }}</div>
          <template v-for="entry in fsLogEntries" :key="entry.id">
            <div v-if="entry.header" class="fs-log-day">
              <span class="fs-log-day-rule"></span>
              <span>{{ entry.header }}</span>
              <span class="fs-log-day-rule"></span>
            </div>
            <div class="fs-log-entry">
              <span class="fs-log-time">{{ entry.time }}</span>
              <span>{{ entry.text }}</span>
            </div>
          </template>
        </div>
      </aside>
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

    <!-- ── PTZ panel (항상 표시, 미지원·미재생 시 비활성) ── -->
    <div class="ptz-card" :class="{ off: ptzOff }" :aria-disabled="ptzOff">

      <div class="ptz-pad">
        <button
          v-for="dir in ptzDirs"
          :key="dir.id"
          class="ptz-dir"
          :class="[dir.id, { pressing: ptzPressing === dir.id }]"
          :title="t(`live.ptz.${dir.id}`)"
          @mousedown="(e) => ptzDown(dir, e)"
          @mouseup="ptzUp(dir)"
          @mouseleave="ptzUp(dir)"
          @touchstart.prevent="(e) => ptzDown(dir, e)"
          @touchend="ptzUp(dir)"
        ><i :class="dir.icon"></i></button>
        <button
          class="ptz-stop"
          :title="t('live.ptz.stop')"
          @click="ptzStopNow"
        >STOP</button>
      </div>

      <div class="ptz-mid">
        <div class="ptz-speed">
          <span class="ptz-row-label">{{ t('live.ptz.speed') }}</span>
          <div class="ptz-speed-seg">
            <button
              v-for="(label, i) in [t('live.ptz.speedSlow'), t('live.ptz.speedNormal'), t('live.ptz.speedFast')]"
              :key="i"
              class="ptz-speed-opt"
              :class="{ active: speedLevel === i }"
              @click="setSpeedLevel(i)"
            >{{ label }}</button>
          </div>
        </div>
      </div>

      <div class="ptz-presets">
        <div class="ptz-presets-head">
          <span class="ptz-row-label">{{ t('live.ptz.presets') }}</span>
          <button class="ptz-save-toggle" @click="ptzSaveMode = !ptzSaveMode; ptzMessage = ''">
            {{ ptzSaveMode ? t('live.ptz.saveCancel') : t('live.ptz.savePosition') }}
          </button>
        </div>
        <div class="ptz-slots">
          <button
            v-for="slot in [1, 2, 3, 4]"
            :key="slot"
            class="ptz-slot"
            :class="{ saved: savedSlots.has(slot) }"
            @click="onPresetClick(slot)"
          >
            <i v-if="ptzSaveMode" class="ph ph-bookmark-simple"></i>{{ slot }}
          </button>
        </div>
        <span class="ptz-hint" :class="{ err: !!ptzMessage }">{{ ptzHint }}</span>
      </div>

    </div>

  </div>
</template>

<style scoped>
.live {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* — video — */
.video-card {
  position: relative;
  flex: 1;
  min-height: 240px;
  border-radius: 10px;
  overflow: hidden;
  background: linear-gradient(160deg, #101413 0%, #17201c 55%, #0d100f 100%);
}
.video-card video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
/* 전체 화면에서 로그 패널이 열리면 영상 영역이 그만큼 줄어든다 */
.video-card.fs-open video,
.video-card.fs-open .video-overlay {
  width: calc(100% - 360px);
}
.fs-topleft {
  position: absolute;
  top: 12px;
  left: 14px;
  display: flex;
  align-items: center;
  gap: 12px;
  z-index: 5;
}
.fs-status {
  font-size: 13px;
  color: rgba(233, 233, 237, 0.6);
  font-variant-numeric: tabular-nums;
}
.live-badge {
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
.video-actions {
  position: absolute;
  top: 12px;
  right: 14px;
  display: flex;
  gap: 8px;
  align-items: center;
  z-index: 5;
}
.video-action {
  width: 34px; height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 17px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(0, 0, 0, 0.42);
  backdrop-filter: blur(8px);
  color: #e9e9ed;
  font-size: 15.5px;
  cursor: pointer;
}
.video-action:hover { background: rgba(0, 0, 0, 0.62); }
.video-overlay {
  position: absolute;
  inset: 0;
  border: none;
  background: rgba(10, 12, 11, 0.55);
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
  font-size: 13.5px;
  color: var(--color-neutral-300);
}

/* — status line — */
.status-line {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  height: 32px;
  font-size: 12.5px;
  color: var(--color-neutral-400);
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
  background: var(--color-neutral-500);
}
.pipe-dot.on { background: #5fbf8a; }
.sep { color: var(--color-neutral-700); }
.metrics {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}

/* 쌓임 배치(1100px 이하): 영상은 채움 대신 16:9 고정 비율로 자연 높이를
   갖는다. 채움을 유지하면 좌측 열이 화면 높이로 압축되어 넘친 패널이
   스크롤 없이 잘린다. */
@media (max-width: 1100px) {
  .live { flex: none; min-height: auto; }
  .video-card {
    flex: none;
    aspect-ratio: 16 / 9;
    min-height: 0;
  }
}

/* — PTZ panel — */
.ptz-card {
  flex: none;
  border-radius: 8px;
  background: var(--color-neutral-900);
  padding: 14px 16px;
  display: flex;
  gap: 22px;
  align-items: stretch;
}
.ptz-card.off {
  opacity: 0.45;
  pointer-events: none;
  user-select: none;
}
.ptz-pad {
  position: relative;
  width: 132px;
  height: 132px;
  flex: none;
  align-self: center;
  border-radius: 50%;
  background: var(--color-neutral-800);
}
.ptz-dir {
  position: absolute;
  width: 40px; height: 40px;
  border-radius: 50%;
  border: none;
  background: transparent;
  color: var(--color-text);
  font-size: 19px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.ptz-dir.up    { top: 6px; left: 50%; transform: translateX(-50%); }
.ptz-dir.down  { bottom: 6px; left: 50%; transform: translateX(-50%); }
.ptz-dir.left  { left: 6px; top: 50%; transform: translateY(-50%); }
.ptz-dir.right { right: 6px; top: 50%; transform: translateY(-50%); }
.ptz-dir.pressing,
.ptz-dir:hover { color: var(--color-accent); }
.ptz-stop {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 42px; height: 42px;
  border-radius: 50%;
  border: none;
  background: color-mix(in srgb, var(--color-accent) 28%, transparent);
  color: var(--color-text);
  font-size: 10px;
  font-weight: 700;
  font-family: inherit;
  letter-spacing: 0.04em;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}
.ptz-stop:hover { background: color-mix(in srgb, var(--color-accent) 42%, transparent); }

.ptz-mid {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 14px;
}
.ptz-speed { display: flex; flex-direction: column; gap: 7px; }
.ptz-row-label {
  font-size: 12.5px;
  color: var(--color-neutral-400);
}
.ptz-speed-seg {
  display: flex;
  gap: 6px;
  background: var(--color-neutral-800);
  border-radius: 9px;
  padding: 3px;
}
.ptz-speed-opt {
  flex: 1;
  height: 32px;
  border-radius: 7px;
  border: none;
  background: transparent;
  color: var(--color-text);
  font-size: 12.5px;
  font-family: inherit;
  cursor: pointer;
}
.ptz-speed-opt.active {
  background: color-mix(in srgb, var(--color-accent) 28%, transparent);
}

.ptz-presets {
  width: 200px;
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.ptz-presets-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ptz-save-toggle {
  border: none;
  background: none;
  padding: 0;
  color: var(--color-accent-300);
  font-size: 12.5px;
  font-family: inherit;
  cursor: pointer;
}
.ptz-slots {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 8px;
}
.ptz-slot {
  flex: 1;
  min-height: 38px;
  border-radius: 8px;
  border: none;
  background: var(--color-neutral-800);
  color: var(--color-text);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
}
.ptz-slot.saved {
  background: color-mix(in srgb, var(--color-accent) 28%, transparent);
}
.ptz-slot i {
  font-size: 14px;
  color: var(--color-accent-300);
}
.ptz-hint {
  font-size: 12px;
  color: var(--color-neutral-400);
  line-height: 1.45;
}
.ptz-hint.err { color: #e07a86; }

/* — fullscreen chrome — */
.fs-cluster {
  position: absolute;
  top: 16px;
  right: 22px;
  display: flex;
  align-items: center;
  gap: 10px;
  z-index: 6;
}
.video-card.fs-open .fs-cluster { right: calc(360px + 22px); }
.fs-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: rgba(233, 233, 237, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 20px;
  padding: 6px 11px;
  font-variant-numeric: tabular-nums;
}
.fs-chip i { font-size: 14.5px; }
.fs-pill {
  display: flex;
  background: rgba(0, 0, 0, 0.62);
  border: 1px solid rgba(255, 255, 255, 0.24);
  border-radius: 20px;
  padding: 2px;
  cursor: pointer;
  font-family: inherit;
}
.fs-pill-opt {
  border-radius: 18px;
  padding: 5px 12px;
  font-size: 13px;
  font-weight: 700;
  background: transparent;
  color: rgba(233, 233, 237, 0.92);
}
.fs-pill-opt.active {
  background: var(--color-accent);
  color: #12131c;
}
.fs-round {
  width: 42px; height: 42px;
  border-radius: 21px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(0, 0, 0, 0.45);
  color: #e9e9ed;
  font-size: 19.5px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fs-round.on { background: color-mix(in srgb, var(--color-accent) 42%, transparent); }

.fs-log {
  position: absolute;
  top: 0; right: 0; bottom: 0;
  width: 360px;
  background: var(--color-surface);
  border-left: 1px solid var(--color-divider);
  display: flex;
  flex-direction: column;
  z-index: 7;
}
.fs-log-head {
  flex: none;
  height: 52px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 8px 0 16px;
  border-bottom: 1px solid var(--color-divider);
}
.fs-vlm {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  min-width: 0;
}
.fs-vlm-dot {
  width: 6px; height: 6px;
  flex: none;
  border-radius: 50%;
}
.fs-log-x {
  width: 34px; height: 34px;
  border: none;
  border-radius: 8px;
  background: none;
  color: var(--color-neutral-300);
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fs-log-x:hover { background: var(--color-neutral-900); color: var(--color-text); }
.fs-log-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
}
.fs-log-none {
  padding: 14px 2px;
  font-size: 13.5px;
  color: var(--color-neutral-500);
}
.fs-log-day {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 0 2px;
  font-size: 12px;
  color: var(--color-neutral-500);
}
.fs-log-day-rule {
  flex: 1;
  height: 1px;
  background: var(--color-divider);
}
.fs-log-entry {
  flex: none;
  display: flex;
  gap: 9px;
  font-size: 13.5px;
  line-height: 1.5;
  color: var(--color-neutral-400);
}
.fs-log-entry:first-of-type { color: var(--color-text); }
.fs-log-time {
  flex: none;
  color: var(--color-neutral-500);
  font-variant-numeric: tabular-nums;
}
</style>
