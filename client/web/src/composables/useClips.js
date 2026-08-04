import { ref, watch, effectScope } from 'vue'
import { authFetch } from './useFetch.js'
import { useSSE } from './useSSE.js'
import { useAuth } from './useAuth.js'
import { API_ENDPOINTS } from '../endpoints.js'

// Increments whenever server clip state may have changed (auth, SSE, delete).
// Components watch this to know when to re-fetch.
const clipVersion = ref(0)
let knownCount = -1

async function deleteClips(names) {
  try {
    const res = await authFetch(API_ENDPOINTS.clips, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ names }),
    })
    if (res.ok) clipVersion.value++
  } catch {
    // @claude Network error — ignored; clipVersion not incremented so caller retains stale data.
  }
}

const globalScope = effectScope(true)
let watcherStarted = false

function ensureWatcher() {
  if (watcherStarted) return
  watcherStarted = true
  globalScope.run(() => {
    const { isAuthenticated } = useAuth()
    const { state: sseState } = useSSE()
    watch(
      isAuthenticated,
      (authenticated) => {
        if (!authenticated) knownCount = -1
        clipVersion.value++
      },
      { immediate: true },
    )
    watch(
      () => (isAuthenticated.value ? sseState.clip_count : null),
      (count) => {
        if (count == null) return
        if (count !== knownCount) {
          knownCount = count
          clipVersion.value++
        }
      },
    )
  })
}

export function useClips() {
  ensureWatcher()
  return { clipVersion, deleteClips }
}
