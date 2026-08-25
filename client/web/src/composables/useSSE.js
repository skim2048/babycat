import { computed, effectScope, reactive, readonly, watch } from 'vue'
import { useAuth } from './useAuth.js'
import { authFetch } from './useFetch.js'
import { hasMessage, t } from './useLocale.js'
import { API_ENDPOINTS, getEventsUrl } from '../endpoints.js'

// @claude Initial values for every /state field the client reads. resetState()
// @claude restores these and drops any other key the server may have merged in,
// @claude so nothing from a previous session survives logout.
const INITIAL_STATE = Object.freeze({
  uptime: '-',
  // @claude Inference
  infer_raw: '',
  infer_ms: 0,
  event_triggered: false,
  analysis_active: false,
  // @claude Pipeline
  frame_w: 0,
  frame_h: 0,
  pipeline_state: 'idle',
  pipeline_state_detail: 'waiting_for_vlm',
  pipeline_source_protocol: '',
  pipeline_source_transport: '',
  pipeline_active_for_s: null,
  pipeline_last_frame_age_s: null,
  pipeline_restart_count: 0,
  // @claude Hardware
  cpu_percent: 0,
  ram_used_mb: 0,
  ram_total_mb: 0,
  disk_used_mb: 0,
  disk_total_mb: 0,
  disk_free_mb: 0,
  disk_path: '',
  gpu_load: 0,
  cpu_temp: 0,
  gpu_temp: 0,
  // @claude Streaming
  streaming_active: false,
  profile_pending: false,
  // @claude PTZ — ptz_presets lists the slot numbers holding a saved position.
  ptz_pan: null,
  ptz_tilt: null,
  ptz_presets: [],
  // @claude Prompt
  inference_prompt: '',
  trigger_keywords: '',
  // @claude Clips
  clip_count: 0,
  segment_recorder_state: 'disabled',
  segment_recorder_error: '',
  segment_recorder_segment_count: 0,
  segment_recorder_last_segment_age_s: null,
  // @claude VLM lifecycle — initializing | downloading | compiling | loading | ready | switching | error
  vlm_state: 'initializing',
  vlm_error: '',
  vlm_models: [],
  vlm_current_model: '',
})

function initialValue(key) {
  const value = INITIAL_STATE[key]
  return Array.isArray(value) ? [] : value
}

const state = reactive(Object.fromEntries(Object.keys(INITIAL_STATE).map((key) => [key, initialValue(key)])))

let started = false
// @claude Reconnect backoff: 1 s first retry, doubling to a 30 s ceiling so a
// @claude backend that is down for long is not polled every second.
const INITIAL_BACKOFF_MS = 1000
const MAX_BACKOFF_MS = 30000
let eventSource = null
let reconnectTimer = null
let backoff = INITIAL_BACKOFF_MS

function resetState() {
  for (const key of Object.keys(state)) {
    if (Object.prototype.hasOwnProperty.call(INITIAL_STATE, key)) {
      state[key] = initialValue(key)
    } else {
      delete state[key]
    }
  }
}

function closeConnection() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}

function scheduleReconnect(token) {
  if (!token || reconnectTimer) return
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    openConnection(token)
  }, backoff)
  backoff = Math.min(backoff * 2, MAX_BACKOFF_MS)
}

// @claude EventSource cannot expose the 401 a replaced session receives on
// @claude reconnect, so a broken stream triggers a throttled probe through
// @claude authFetch, whose 401 handling classifies and notifies.
// @claude 5 s throttle: a flapping stream must not turn into a request storm.
const PROBE_MIN_INTERVAL_MS = 5000
let lastProbeAt = 0
function probeSession() {
  const now = Date.now()
  if (now - lastProbeAt < PROBE_MIN_INTERVAL_MS) return
  lastProbeAt = now
  authFetch(API_ENDPOINTS.camera).catch(() => {
    // @claude Network-level failure — reconnect backoff already covers it.
  })
}

function openConnection(token) {
  closeConnection()
  if (!token) {
    resetState()
    return
  }

  eventSource = new EventSource(getEventsUrl(token))

  eventSource.onopen = () => {
    backoff = INITIAL_BACKOFF_MS
  }

  eventSource.onmessage = (e) => {
    try {
      Object.assign(state, JSON.parse(e.data))
    } catch (err) {
      console.warn('SSE: malformed state payload ignored', err)
    }
  }

  eventSource.onerror = () => {
    closeConnection()
    probeSession()
    scheduleReconnect(token)
  }
}

function connect() {
  if (started) return
  started = true

  // @claude The watcher lives in a detached scope: registered inside a
  // @claude component it would die with that component's unmount while the
  // @claude started flag stays true, silently ending reconnection.
  effectScope(true).run(() => {
    const { accessToken } = useAuth()
    watch(accessToken, (token) => {
      backoff = INITIAL_BACKOFF_MS
      if (!token) {
        closeConnection()
        resetState()
        return
      }
      openConnection(token)
    }, { immediate: true })
  })
}

export function useSSE() {
  connect()
  const readonlyState = readonly(state)
  const pipelineStateLabel = computed(() => {
    const key = `sse.pipeline.${readonlyState.pipeline_state}`
    if (hasMessage(key)) return t(key)
    return readonlyState.pipeline_state || t('sse.unknown')
  })
  const pipelineDetailLabel = computed(() => {
    const detail = readonlyState.pipeline_state_detail
    if (!detail) return ''
    const key = `sse.detail.${detail}`
    return hasMessage(key) ? t(key) : detail
  })
  return {
    state: readonlyState,
    pipelineStateLabel,
    pipelineDetailLabel,
  }
}
