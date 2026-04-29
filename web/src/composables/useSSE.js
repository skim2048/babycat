import { computed, reactive, readonly, watch } from 'vue'
import { useAuth } from './useAuth.js'
import { hasMessage, t } from './useLocale.js'
import { getEventsUrl } from '../endpoints.js'

const state = reactive({
  uptime: '-',
  // @claude Inference
  infer_raw: '',
  infer_ms: 0,
  event_triggered: false,
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
  cfg_n_frames: 0,
  // @claude Hardware
  cpu_percent: 0,
  ram_used_mb: 0,
  ram_total_mb: 0,
  gpu_load: 0,
  cpu_temp: 0,
  gpu_temp: 0,
  // @claude PTZ
  ptz_pan: null,
  ptz_tilt: null,
  ptz_saved_pan: null,
  ptz_saved_tilt: null,
  // @claude Prompt
  inference_prompt: '',
  trigger_keywords: '',
  // @claude Clips
  clip_count: 0,
  // @claude VLM lifecycle — initializing | downloading | compiling | loading | ready | switching | error
  vlm_state: 'initializing',
  vlm_error: '',
  vlm_models: [],
  vlm_current_model: '',
})

let started = false
const MAX_BACKOFF = 30000
let eventSource = null
let reconnectTimer = null
let backoff = 1000
function resetState() {
  state.uptime = '-'
  state.infer_raw = ''
  state.infer_ms = 0
  state.event_triggered = false
  state.frame_w = 0
  state.frame_h = 0
  state.pipeline_state = 'idle'
  state.pipeline_state_detail = 'waiting_for_vlm'
  state.pipeline_source_protocol = ''
  state.pipeline_source_transport = ''
  state.pipeline_active_for_s = null
  state.pipeline_last_frame_age_s = null
  state.pipeline_restart_count = 0
  state.cfg_n_frames = 0
  state.cpu_percent = 0
  state.ram_used_mb = 0
  state.ram_total_mb = 0
  state.gpu_load = 0
  state.cpu_temp = 0
  state.gpu_temp = 0
  state.ptz_pan = null
  state.ptz_tilt = null
  state.ptz_saved_pan = null
  state.ptz_saved_tilt = null
  state.inference_prompt = ''
  state.trigger_keywords = ''
  state.clip_count = 0
  state.vlm_state = 'initializing'
  state.vlm_error = ''
  state.vlm_models = []
  state.vlm_current_model = ''
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
  backoff = Math.min(backoff * 2, MAX_BACKOFF)
}

function openConnection(token) {
  closeConnection()
  if (!token) {
    resetState()
    return
  }

  eventSource = new EventSource(getEventsUrl(token))

  eventSource.onopen = () => {
    backoff = 1000
  }

  eventSource.onmessage = (e) => {
    try {
      Object.assign(state, JSON.parse(e.data))
    } catch {
      // @claude Malformed JSON — ignored.
    }
  }

  eventSource.onerror = () => {
    closeConnection()
    scheduleReconnect(token)
  }
}

function connect() {
  if (started) return
  started = true

  const { accessToken } = useAuth()
  watch(accessToken, (token) => {
    backoff = 1000
    if (!token) {
      closeConnection()
      resetState()
      return
    }
    openConnection(token)
  }, { immediate: true })
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
