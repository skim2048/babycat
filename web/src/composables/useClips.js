import { ref, watch } from 'vue'
import { authFetch } from './useFetch.js'
import { useSSE } from './useSSE.js'

const clips = ref([])
const checked = ref({})
const searchQuery = ref('')
let knownCount = -1

async function fetchClips() {
  try {
    const res = await authFetch('/clips')
    if (!res.ok) return
    clips.value = await res.json()
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

async function deleteAll() {
  const names = clips.value.map((c) => c.name)
  if (names.length === 0) return
  await deleteClips(names)
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

let initialized = false

export function useClips() {
  if (!initialized) {
    initialized = true
    fetchClips()

    const { state } = useSSE()
    watch(
      () => state.clip_count,
      (count) => {
        if (count !== knownCount) {
          knownCount = count
          fetchClips()
        }
      },
    )
  }

  return {
    clips,
    checked,
    searchQuery,
    fetchClips,
    deleteClips,
    deleteAll,
    deleteSelected,
    toggleCheck,
  }
}
