import { reactive, readonly } from 'vue'
import { useAuth } from './useAuth.js'
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
  pipeline_status_reason: 'boot',
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

function connect() {
  if (started) return
  started = true

  let backoff = 1000

  function open() {
    const { getToken } = useAuth()
    const token = getToken()
    const es = new EventSource(getEventsUrl(token))

    es.onopen = () => {
      backoff = 1000
    }

    es.onmessage = (e) => {
      try {
        Object.assign(state, JSON.parse(e.data))
      } catch {
        // @claude Malformed JSON — ignored.
      }
    }

    es.onerror = () => {
      es.close()
      setTimeout(open, backoff)
      backoff = Math.min(backoff * 2, MAX_BACKOFF)
    }
  }

  open()
}

export function useSSE() {
  connect()
  return { state: readonly(state) }
}
