import { reactive, readonly } from 'vue'
import { useAuth } from './useAuth.js'

const state = reactive({
  uptime: '-',
  // Inference
  infer_raw: '',
  infer_ms: 0,
  event_triggered: false,
  // Pipeline
  frame_w: 0,
  frame_h: 0,
  cfg_n_frames: 0,
  // Hardware
  cpu_percent: 0,
  ram_used_mb: 0,
  ram_total_mb: 0,
  gpu_load: 0,
  cpu_temp: 0,
  gpu_temp: 0,
  // PTZ
  ptz_pan: null,
  ptz_tilt: null,
  ptz_saved_pan: null,
  ptz_saved_tilt: null,
  // Prompt
  inference_prompt: '',
  trigger_keywords: '',
  // Clips
  clip_count: 0,
  // VLM lifecycle — loading | ready | error
  vlm_state: 'loading',
  vlm_error: '',
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
    const es = new EventSource(`/events?token=${encodeURIComponent(token)}`)

    es.onopen = () => {
      backoff = 1000
    }

    es.onmessage = (e) => {
      try {
        Object.assign(state, JSON.parse(e.data))
      } catch {
        // malformed JSON — 무시
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
