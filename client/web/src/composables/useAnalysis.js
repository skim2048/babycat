import { computed, ref } from 'vue'
import { useSSE } from './useSSE.js'
import { authFetch } from './useFetch.js'
import { APP_ENDPOINTS } from '../endpoints.js'

// @claude FR-024/FR-025: saving prompt settings never starts analysis; the
// @claude explicit start fans out to the analyzer and the recorder. FR-050:
// @claude the router rejects a start while live streaming is inactive — the
// @claude rejected flag routes the 사유 안내 into the prompt panel.
const busy = ref(false)
const rejected = ref(false)

export function useAnalysis() {
  const { state } = useSSE()

  // @claude idle means the pipeline waits for an explicit start (FR-024), so a
  // @claude streaming pipeline that is not idle is an analysis in progress.
  const analysisActive = computed(() => state.streaming_active && state.pipeline_state !== 'idle')

  async function start() {
    try {
      const res = await authFetch(APP_ENDPOINTS.analysisStart, { method: 'POST' })
      const data = await res.json()
      if (res.ok && data.ok) return true
      if (res.status === 409) rejected.value = true
      return false
    } catch {
      return false
    }
  }

  // @claude FR-051: stop analysis and buffering while streaming stays up.
  async function stop() {
    try {
      const res = await authFetch(APP_ENDPOINTS.analysisStop, { method: 'POST' })
      const data = await res.json()
      return res.ok && data.ok
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
