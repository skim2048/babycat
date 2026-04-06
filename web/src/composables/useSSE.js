import { reactive, readonly } from 'vue'

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
})

let started = false
const MAX_BACKOFF = 30000

function connect() {
  if (started) return
  started = true

  let backoff = 1000

  function open() {
    const es = new EventSource('/events')

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
