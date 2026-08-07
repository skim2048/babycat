import { reactive, readonly, watch } from 'vue'
import { useSSE } from './useSSE.js'

// @claude The mockup's right-hand panel lists inference reports over time, but
// @claude the backend stores only keyword events (/events: trigger + clip).
// @claude The narrative log therefore accumulates client-side from the SSE
// @claude infer_raw stream, newest first, capped for display.
const MAX_LOG = 100

const entries = reactive([])
let started = false

function timestamp() {
  const now = new Date()
  return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
}

export function useInferLog() {
  if (!started) {
    started = true
    const { state } = useSSE()
    watch(() => state.infer_raw, (text) => {
      if (!text) return
      if (entries.length && entries[0].text === text) return
      entries.unshift({ time: timestamp(), text, event: state.event_triggered })
      if (entries.length > MAX_LOG) entries.length = MAX_LOG
    })
  }

  return { entries: readonly(entries) }
}
