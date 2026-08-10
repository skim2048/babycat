<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useCamera } from '../composables/useCamera.js'
import { useAuth } from '../composables/useAuth.js'
import { useLocale } from '../composables/useLocale.js'
import { useSSE } from '../composables/useSSE.js'
import { useStreamProtocol } from '../composables/useStreamProtocol.js'
import { useAnalysis } from '../composables/useAnalysis.js'
import { useInferLog } from '../composables/useInferLog.js'
import { useVlmStatus } from '../composables/useVlmStatus.js'
import { useStreamStats } from '../composables/useStreamStats.js'
import { getHlsUrl, getWhepUrl, APP_ENDPOINTS } from '../endpoints.js'
import { authFetch } from '../composables/useFetch.js'

const emit = defineEmits(['open-sheet'])

const {
  state: sseState,
  pipelineStateLabel,
  pipelineDetailLabel,
} = useSSE()
const { t } = useLocale()

const { accessToken, isAuthenticated, isPersistentSession, sessionRemainingSeconds } = useAuth()
const { configured, connecting, connected, setConnected, setDisconnected, disconnect } = useCamera()
const { analysisActive, busy: analysisBusy, toggle: toggleAnalysis } = useAnalysis()
const { entries: inferLog, removeEntries } = useInferLog()
const { vlmDot, vlmLabel } = useVlmStatus()

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
const loading = ref(false)
const stopped = ref(true)
const fullscreen = ref(false)
const fsLog = ref(true)

// @claude 기기 방향이 전체 화면을 자동 전환한다: 가로 → 진입, 세로 → 종료.
// @claude 버튼으로 한 수동 전환은 다음 방향 전환 때까지 유지된다.
let landscapeMq = null
function onOrientationChange(e) {
  fullscreen.value = e.matches
}

// @claude 가로 상태에서 축소하면 화면을 세로로 잠근다 — 기기가 가로여도
// @claude 일반 UI는 세로로 유지된다. 잠금은 다시 확대할 때 풀린다.
// @claude (브라우저에서는 lock이 전체 화면 밖에서 거부될 수 있어 무시한다.)
function enterFullscreen() {
  try { screen.orientation?.unlock?.() } catch {}
  fullscreen.value = true
}
function exitFullscreen() {
  fullscreen.value = false
  if (landscapeMq?.matches) {
    try { screen.orientation?.lock?.('portrait')?.catch?.(() => {}) } catch {}
  }
}

// ── VLM card: model switch / infer toggle / log ──
const modelMenu = ref(false)
// @claude 모델 id의 마지막 경로 조각만 표기한다
// @claude (예: Efficient-Large-Model/VILA1.5-3b → VILA1.5-3b).
function shortModelName(id) {
  if (!id) return ''
  const parts = id.split('/')
  return parts[parts.length - 1]
}
const modelLabel = computed(() =>
  shortModelName(sseState.vlm_current_model) || t('dashboard.model.unknown'),
)
async function switchModel(name) {
  modelMenu.value = false
  if (!name || name === sseState.vlm_current_model) return
  try {
    await authFetch(APP_ENDPOINTS.vlmSwitch, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: name }),
    })
  } catch {}
}

// @claude 거부되면(스트리밍 꺼짐) 사유 안내가 있는 프롬프트 시트를 연다.
async function onInferClick() {
  const ok = await toggleAnalysis()
  if (!ok) emit('open-sheet', 'prompt')
}

const logQuery = ref('')

function localDate(offsetDays = 0) {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// @claude 시안: 날짜가 바뀌는 지점에만 구분선을 넣되 오늘은 생략하고,
// @claude 어제는 문구로, 그보다 이전은 YY-MM-DD로 표기한다.
function annotateDays(list) {
  const today = localDate()
  const yesterday = localDate(-1)
  let prevDay = null
  return list.map((entry) => {
    let header = null
    if (entry.day !== prevDay && entry.day !== today) {
      header = entry.day === yesterday ? t('dashboard.day.yesterday') : entry.day.slice(2)
    }
    prevDay = entry.day
    return { ...entry, header }
  })
}

const visibleLog = computed(() => {
  const q = logQuery.value.trim().toLowerCase()
  const filtered = q
    ? inferLog.filter((l) => l.text.toLowerCase().includes(q) || l.time.includes(q))
    : [...inferLog]
  return annotateDays(filtered)
})
const fsLogEntries = computed(() => annotateDays([...inferLog]))

// @claude 로그 선택·삭제 — 웹 대시보드와 동일한 규칙. 이 로그는 서버에
// @claude 저장되지 않는 세션 내 데이터이므로 삭제는 화면 목록에서의 제거다.
const logSelectMode = ref(false)
const logSelected = ref(new Set())

function toggleLogSelect() {
  logSelectMode.value = !logSelectMode.value
  logSelected.value = new Set()
}
function toggleLogEntry(id) {
  if (!logSelectMode.value) return
  const next = new Set(logSelected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  logSelected.value = next
}
const allLogSelected = computed(() =>
  visibleLog.value.length > 0 && visibleLog.value.every((l) => logSelected.value.has(l.id)),
)
function toggleLogSelectAll() {
  logSelected.value = allLogSelected.value
    ? new Set()
    : new Set(visibleLog.value.map((l) => l.id))
}
function deleteSelectedLogs() {
  if (!logSelected.value.size) return
  removeEntries([...logSelected.value])
  logSelected.value = new Set()
  logSelectMode.value = false
}

// ── Fullscreen chrome ──
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

// ── Stream (client/web LiveStream과 동일한 연결 논리) ──

let hls = null
let Hls = null
let stallTimer = null
let retryTimer = null
let pipelineRecoveryTimer = null
let pc = null
let sessionId = 0
const STALL_TIMEOUT = 8000
const RETRY_BACKOFF = 3000

// @claude The preference is shared with the top bar's pill.
const { preferredProtocol, setProtocol } = useStreamProtocol()
const activeProtocol = ref(preferredProtocol.value)
const isWebRTC = computed(() => activeProtocol.value === 'webrtc')
const isPlaying = computed(() => connected.value && !loading.value && !stopped.value)

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
  landscapeMq = window.matchMedia('(orientation: landscape)')
  landscapeMq.addEventListener('change', onOrientationChange)
  if (landscapeMq.matches) fullscreen.value = true
})

onBeforeUnmount(() => {
  landscapeMq?.removeEventListener('change', onOrientationChange)
  destroyAll()
})
</script>

<template>
  <div class="live-mobile">

    <!-- ── Video (전체 화면 시 가로 회전 캔버스가 된다) ── -->
    <div class="video-wrap" :class="{ fs: fullscreen }">
      <div class="rotor">
        <div class="videobox">
          <video ref="videoRef" muted playsinline />

          <span v-if="isPlaying" class="live-badge"><span class="live-dot"></span>LIVE</span>
          <span v-if="fullscreen && isPlaying" class="fs-status">
            {{ pipelineStateLabel }} · {{ stats.resolution || '–' }} · {{ stats.fps || 0 }} FPS
          </span>

          <button v-if="stopped" class="video-overlay" @click="handleConnect">
            <span class="play-ring"><i class="ph-fill ph-play"></i></span>
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
              @click="enterFullscreen"
            ><i class="ph ph-corners-out"></i></button>
          </div>

          <!-- 전체 화면: 세션 · 프로토콜 · 연결 해제 · 로그 · 종료 -->
          <div v-else class="fs-cluster">
            <span v-if="showSessionRemaining" class="fs-chip">
              <i class="ph ph-clock"></i>{{ sessionRemainingText }}
            </span>
            <!-- 시안: 알약의 어느 부분을 눌러도 반대 프로토콜로 전환된다 -->
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
              @click="exitFullscreen"
            ><i class="ph ph-corners-in"></i></button>
          </div>
        </div>

        <!-- 전체 화면: 접이식 추론 로그 패널 -->
        <aside v-if="fullscreen && fsLog" class="fs-log">
          <div class="fs-log-head">
            <span class="fs-vlm">
              <span class="fs-vlm-dot" :style="{ background: vlmDot }"></span>{{ vlmLabel }}
            </span>
            <button class="fs-log-x" @click="fsLog = false"><i class="ph ph-x"></i></button>
          </div>
          <div class="fs-log-list">
            <div v-if="!fsLogEntries.length" class="log-none">{{ t('dashboard.log.waiting') }}</div>
            <template v-for="entry in fsLogEntries" :key="entry.id">
              <div v-if="entry.header" class="log-day">
                <span class="log-day-rule"></span>
                <span>{{ entry.header }}</span>
                <span class="log-day-rule"></span>
              </div>
              <div class="log-entry">
                <span class="log-time">{{ entry.time }}</span>
                <span>{{ entry.text }}</span>
              </div>
            </template>
          </div>
        </aside>
      </div>
    </div>

    <!-- ── Status line ── -->
    <div class="status-line">
      <span class="pipe">
        <span class="pipe-dot" :class="{ on: isPlaying }"></span>{{ pipelineStateLabel }}
      </span>
      <template v-if="pipelineDetailLabel">
        <span class="sep">·</span><span class="detail">{{ pipelineDetailLabel }}</span>
      </template>
      <span class="metrics">{{ stats.resolution || '–' }} · {{ stats.fps || 0 }} FPS</span>
    </div>

    <!-- ── VLM log card ── -->
    <div class="vlm-card">
      <div class="vlm-head">
        <span class="vlm-status">
          <span class="vlm-dot" :style="{ background: vlmDot }"></span>{{ vlmLabel }}
        </span>
        <div class="vlm-actions">
          <div class="model-wrap">
            <button
              class="model-btn"
              :aria-expanded="modelMenu"
              @click="modelMenu = !modelMenu"
              @keydown.esc="modelMenu = false"
            >
              {{ modelLabel }}<i :class="modelMenu ? 'ph ph-caret-up' : 'ph ph-caret-down'"></i>
            </button>
            <div v-if="modelMenu" class="menu-backdrop" @click="modelMenu = false"></div>
            <div v-if="modelMenu" class="model-menu" @keydown.esc="modelMenu = false">
              <button
                v-for="m in sseState.vlm_models"
                :key="m"
                class="model-opt"
                :class="{ current: m === sseState.vlm_current_model }"
                :title="m"
                @click="switchModel(m)"
              ><span>{{ shortModelName(m) }}</span></button>
              <div v-if="!sseState.vlm_models.length" class="model-none">{{ t('dashboard.model.none') }}</div>
            </div>
          </div>
          <button
            class="infer-btn"
            :class="{ on: analysisActive }"
            :disabled="analysisBusy"
            @click="onInferClick"
          >{{ analysisActive ? t('prompt.action.stop') : t('prompt.action.start') }}</button>
        </div>
      </div>

      <div class="log-controls">
        <div class="log-search">
          <i class="ph ph-magnifying-glass"></i>
          <input v-model="logQuery" :placeholder="t('dashboard.log.search')" />
          <button v-if="logQuery" class="log-clear" @click="logQuery = ''"><i class="ph ph-x"></i></button>
        </div>
        <button class="log-pill" :class="{ on: logSelectMode }" @click="toggleLogSelect">
          {{ logSelectMode ? t('dashboard.log.cancel') : t('dashboard.log.select') }}
        </button>
        <button v-if="logSelectMode" class="log-pill" @click="toggleLogSelectAll">
          {{ allLogSelected ? t('dashboard.log.deselectAll') : t('dashboard.log.selectAll') }}
        </button>
        <button
          v-if="logSelectMode"
          class="log-pill danger"
          :disabled="!logSelected.size"
          @click="deleteSelectedLogs"
        >{{ t('dashboard.log.delete') }}</button>
      </div>

      <div class="log-rule"></div>

      <div class="log-list">
        <div v-if="!visibleLog.length" class="log-none">
          {{ logQuery ? t('dashboard.log.none') : t('dashboard.log.waiting') }}
        </div>
        <template v-for="(entry, i) in visibleLog" :key="entry.id">
          <div v-if="entry.header" class="log-day">
            <span class="log-day-rule"></span>
            <span>{{ entry.header }}</span>
            <span class="log-day-rule"></span>
          </div>
          <div
            class="log-entry"
            :class="{ latest: i === 0 && !logQuery, selecting: logSelectMode, picked: logSelected.has(entry.id) }"
            @click="toggleLogEntry(entry.id)"
          >
            <span v-if="logSelectMode" class="log-check" :class="{ on: logSelected.has(entry.id) }">
              <svg v-if="logSelected.has(entry.id)" class="check-glyph" viewBox="0 0 12 12" aria-hidden="true"><polyline points="2.5,6.5 5,9 9.5,3.5" /></svg>
            </span>
            <span class="log-time">{{ entry.time }}</span>
            <span class="log-text">{{ entry.text }}</span>
          </div>
        </template>
      </div>
    </div>

  </div>
</template>

<style scoped>
.check-glyph {
  width: 10px;
  height: 10px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2.2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.live-mobile {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-bottom: 12px;
}

/* — video — */
.video-wrap {
  position: relative;
  flex: none;
  height: 220px;
  background: linear-gradient(160deg, #101413 0%, #17201c 55%, #0d100f 100%);
  overflow: hidden;
}
.rotor {
  position: absolute;
  inset: 0;
  display: flex;
}
.videobox {
  position: relative;
  flex: 1;
  min-width: 0;
}
.videobox video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
/* 전체 화면: 세로 기기에서 가로 캔버스로 회전 (시안 방식) */
.video-wrap.fs {
  position: fixed;
  inset: 0;
  z-index: 150;
  height: auto;
  background: #0b0c12;
}
/* 세로 화면: 가로 캔버스를 90° 회전해 채운다.
   inset은 top·left의 축약형이므로 반드시 top/left보다 먼저 두어야 한다. */
.video-wrap.fs .rotor {
  inset: auto;
  top: 50%;
  left: 50%;
  width: 100vh;
  height: 100vw;
  transform: translate(-50%, -50%) rotate(90deg);
}
/* 이미 가로 화면이면 회전 없이 그대로 채운다.
   inset: 0이 네 변을 모두 지정하므로 top/left를 다시 선언하지 않는다. */
@media (orientation: landscape) {
  .video-wrap.fs .rotor {
    inset: 0;
    width: auto;
    height: auto;
    transform: none;
  }
}

.live-badge {
  position: absolute;
  top: 10px;
  left: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  letter-spacing: 0.1em;
  color: #e9e9ed;
  background: rgba(0, 0, 0, 0.45);
  padding: 4px 8px;
  border-radius: 5px;
  backdrop-filter: blur(6px);
  z-index: 3;
}
.live-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #e05b6a;
}
.fs-status {
  position: absolute;
  bottom: 14px;
  left: 18px;
  font-size: 11.5px;
  color: rgba(233, 233, 237, 0.6);
  background: rgba(0, 0, 0, 0.45);
  padding: 5px 9px;
  border-radius: 5px;
  font-variant-numeric: tabular-nums;
  z-index: 3;
}
.video-actions {
  position: absolute;
  top: 10px;
  right: 12px;
  display: flex;
  gap: 6px;
  align-items: center;
  z-index: 5;
}
.video-action {
  width: 32px; height: 32px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(0, 0, 0, 0.42);
  backdrop-filter: blur(8px);
  color: #e9e9ed;
  font-size: 15px;
  cursor: pointer;
}
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
  gap: 10px;
  cursor: pointer;
  font-family: inherit;
  z-index: 4;
}
.play-ring {
  width: 62px; height: 62px;
  border-radius: 50%;
  border: 1px solid var(--color-accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
  color: var(--color-accent);
}
.spinner {
  width: 34px; height: 34px;
  border-radius: 50%;
  border: 2px solid var(--color-neutral-800);
  border-top-color: var(--color-accent);
  animation: live-spin 900ms linear infinite;
}
@keyframes live-spin { to { transform: rotate(360deg); } }
.overlay-text {
  font-size: 13px;
  color: var(--color-neutral-300);
}

/* — fullscreen chrome — */
.fs-cluster {
  position: absolute;
  top: 12px;
  right: 18px;
  display: flex;
  align-items: center;
  gap: 8px;
  z-index: 6;
}
.fs-chip {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  color: rgba(233, 233, 237, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 20px;
  padding: 5px 10px;
  font-variant-numeric: tabular-nums;
}
.fs-chip i { font-size: 13px; }
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
  padding: 5px 11px;
  font-size: 11.5px;
  font-weight: 700;
  background: transparent;
  color: rgba(233, 233, 237, 0.92);
}
.fs-pill-opt.active {
  background: var(--color-accent);
  color: #12131c;
}
.fs-round {
  width: 40px; height: 40px;
  border-radius: 100px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(0, 0, 0, 0.45);
  color: #e9e9ed;
  font-size: 17.5px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fs-round.on { background: color-mix(in srgb, var(--color-accent) 42%, transparent); }

.fs-log {
  width: 300px;
  flex: none;
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
}
.fs-log-head {
  flex: none;
  height: 52px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 6px 0 16px;
  border-bottom: 1px solid var(--color-divider);
}
.fs-vlm {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
  min-width: 0;
}
.fs-vlm-dot {
  width: 6px; height: 6px;
  flex: none;
  border-radius: 50%;
}
.fs-log-x {
  width: 40px; height: 40px;
  border: none;
  border-radius: 100px;
  background: none;
  color: var(--color-neutral-300);
  font-size: 17px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fs-log-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 16px;
}

/* — status line — */
.status-line {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 30px;
  padding: 0 12px;
  font-size: 11.5px;
  color: var(--color-neutral-400);
  white-space: nowrap;
  overflow: hidden;
}
.pipe {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--color-text);
}
.pipe-dot {
  width: 5px; height: 5px;
  border-radius: 50%;
  background: var(--color-neutral-500);
}
.pipe-dot.on { background: #5fbf8a; }
.sep { color: var(--color-neutral-700); }
.detail {
  overflow: hidden;
  text-overflow: ellipsis;
}
.metrics {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}

/* — VLM log card — */
.vlm-card {
  flex: 1;
  min-height: 150px;
  border-radius: 16px;
  padding: 14px;
  margin: 0 16px;
  background: var(--color-neutral-900);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.vlm-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.vlm-status {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
  min-width: 0;
}
.vlm-dot {
  width: 6px; height: 6px;
  flex: none;
  border-radius: 50%;
}
.vlm-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}
.model-wrap { position: relative; }
.model-btn {
  height: 30px;
  padding: 0 8px 0 10px;
  border-radius: 100px;
  border: none;
  background: var(--color-neutral-800);
  color: var(--color-text);
  font-family: inherit;
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 5px;
  max-width: 130px;
  white-space: nowrap;
  overflow: hidden;
}
.model-btn i { font-size: 11px; color: var(--color-neutral-400); }
.menu-backdrop {
  position: fixed;
  inset: 0;
  z-index: 19;
}
.model-menu {
  position: absolute;
  top: 36px;
  right: 0;
  z-index: 20;
  width: 160px;
  background: var(--color-surface);
  border-radius: 12px;
  padding: 4px;
  box-shadow: var(--shadow-md);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.model-opt {
  height: 36px;
  padding: 0 10px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: var(--color-text);
  font-family: inherit;
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  text-align: left;
}
.model-opt span {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.model-opt.current { background: color-mix(in srgb, var(--color-accent) 16%, transparent); }
.model-none {
  padding: 8px 10px;
  font-size: 12.5px;
  color: var(--color-neutral-500);
}
.infer-btn {
  height: 30px;
  flex: none;
  padding: 0 11px;
  border-radius: 100px;
  border: none;
  background: var(--color-neutral-800);
  color: var(--color-text);
  font-family: inherit;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}
.infer-btn.on { background: color-mix(in srgb, var(--color-accent) 28%, transparent); }
.infer-btn:disabled { opacity: 0.6; cursor: default; }

.log-controls {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
}
.log-pill {
  flex: none;
  height: 36px;
  padding: 0 12px;
  border-radius: 100px;
  border: none;
  background: var(--color-neutral-800);
  color: var(--color-text);
  font-size: 12.5px;
  font-family: inherit;
  cursor: pointer;
}
.log-pill.on { background: color-mix(in srgb, var(--color-accent) 22%, transparent); }
.log-pill.danger { color: #e07a86; }
.log-pill:disabled { opacity: 0.45; cursor: default; }
.log-search {
  position: relative;
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
}
.log-search > i {
  position: absolute;
  left: 11px;
  font-size: 14px;
  color: var(--color-neutral-500);
  pointer-events: none;
}
.log-search input {
  width: 100%;
  box-sizing: border-box;
  height: 36px;
  border-radius: 100px;
  border: none;
  background: var(--color-neutral-800);
  color: var(--color-text);
  padding: 0 32px;
  font-size: 12.5px;
  font-family: inherit;
  outline: none;
}
.log-search input:focus-visible { outline: 2px solid var(--color-accent); }
.log-clear {
  position: absolute;
  right: 7px;
  width: 24px; height: 24px;
  border: none;
  background: none;
  color: var(--color-neutral-400);
  font-size: 13px;
  cursor: pointer;
  border-radius: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.log-rule {
  flex: none;
  height: 1px;
  background: var(--color-divider);
}
.log-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-right: 8px;
}
.log-none {
  padding: 10px 2px;
  font-size: 12.5px;
  color: var(--color-neutral-400);
}
.log-day {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 0;
  font-size: 11.5px;
  color: var(--color-neutral-500);
}
.log-day-rule {
  flex: 1;
  height: 1px;
  background: var(--color-divider);
}
.log-entry {
  flex: none;
  display: flex;
  gap: 8px;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--color-neutral-400);
  border-radius: 6px;
}
.log-entry.selecting {
  cursor: pointer;
  padding: 4px 6px;
}
.log-entry.picked { background: color-mix(in srgb, var(--color-accent) 16%, transparent); }
.log-entry.latest,
.log-entry.latest .log-text { color: var(--color-text); }
.log-check {
  flex: none;
  width: 16px; height: 16px;
  margin-top: 2px;
  border-radius: 4px;
  border: 1px solid var(--color-neutral-700);
  color: #12131c;
  font-size: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.log-check.on {
  border-color: var(--color-accent);
  background: var(--color-accent);
}
.log-time {
  flex: none;
  color: var(--color-neutral-500);
  font-variant-numeric: tabular-nums;
}
</style>
