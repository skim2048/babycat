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
    // 네트워크 오류 — 무시 (다음 SSE 갱신 시 재시도)
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
    // 네트워크 오류
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

// 컴포넌트 생명주기와 분리된 글로벌 effectScope에 워처 등록.
// 인증된 상태에서만 1회 등록하여 로그인 페이지에서 401 루프를 방지한다.
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
