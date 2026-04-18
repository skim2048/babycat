import { ref, watch, effectScope } from 'vue'
import { authFetch } from './useFetch.js'
import { useSSE } from './useSSE.js'
import { useAuth } from './useAuth.js'

const clips = ref([])
const checked = ref({})
const searchQuery = ref('')
let knownCount = -1

async function fetchClips() {
  try {
    const res = await authFetch('/clips')
    if (!res.ok) return
    const data = await res.json()
    clips.value = data.clips || []
    checked.value = {}
  } catch {
    // @claude Network error — ignored; the next SSE tick will retry.
  }
}

async function deleteClips(names) {
  try {
    const res = await authFetch('/clips', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ names }),
    })
    if (res.ok) await fetchClips()
  } catch {
    // @claude Network error — ignored.
  }
}

function toggleCheck(name, val) {
  checked.value = { ...checked.value, [name]: val }
}

async function deleteSelected() {
  const names = Object.entries(checked.value)
    .filter(([, v]) => v)
    .map(([k]) => k)
  if (names.length === 0) return
  await deleteClips(names)
}

// @claude Register the watcher in a global effectScope, detached from component lifetimes.
// @claude Only registered once while authenticated; prevents a 401 loop on the login page.
const globalScope = effectScope(true)
let watcherStarted = false
function ensureWatcher() {
  if (watcherStarted) return
  const { isAuthenticated } = useAuth()
  if (!isAuthenticated.value) return
  watcherStarted = true
  globalScope.run(() => {
    const { state: sseState } = useSSE()
    fetchClips()
    watch(
      () => sseState.clip_count,
      (count) => {
        if (count !== knownCount) {
          knownCount = count
          fetchClips()
        }
      },
    )
  })
}

export function useClips() {
  ensureWatcher()
  return {
    clips,
    checked,
    searchQuery,
    deleteClips,
    deleteSelected,
    toggleCheck,
  }
}
