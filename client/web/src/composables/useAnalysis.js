import { computed, ref } from 'vue'
import { useSSE } from './useSSE.js'
import { authFetch } from './useFetch.js'
import { APP_ENDPOINTS } from '../endpoints.js'

// @claude Saving prompt settings never starts analysis; the explicit start
// @claude fans out to the analyzer and the recorder. The router rejects a
// @claude start while live streaming is inactive — the rejected flag routes
// @claude the reason notice into the prompt panel.
const busy = ref(false)
const rejected = ref(false)

export function useAnalysis() {
  const { state } = useSSE()

  // @claude The analyzer reports whether an analysis is in progress; the
  // @claude client does not infer it from pipeline or streaming state.
  const analysisActive = computed(() => !!state.analysis_active)

  async function start() {
    try {
      const res = await authFetch(APP_ENDPOINTS.analysisStart, { method: 'POST' })
      if (res.ok) return true
      if (res.status === 409) rejected.value = true
      return false
    } catch {
      return false
    }
  }

  // @claude Stop analysis and buffering while streaming stays up.
  async function stop() {
    try {
      const res = await authFetch(APP_ENDPOINTS.analysisStop, { method: 'POST' })
      return res.ok
    } catch {
      return false
    }
  }

  // @claude Returns false when the start was rejected so the caller can bring
  // @claude the prompt panel (which shows the reason) into view.
  async function toggle() {
    if (busy.value) return true
    if (!analysisActive.value && !state.streaming_active) {
      rejected.value = true
      return false
    }
    busy.value = true
    try {
      if (analysisActive.value) {
        await stop()
        return true
      }
      const ok = await start()
      return ok || !rejected.value
    } finally {
      busy.value = false
    }
  }

  function clearRejected() {
    rejected.value = false
  }

  return { analysisActive, busy, rejected, toggle, clearRejected }
}
