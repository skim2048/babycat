import { ref, watch } from 'vue'
import { useSSE } from './useSSE.js'

const clips = ref([])
const checked = ref({})
const searchQuery = ref('')
let knownCount = -1

async function fetchClips() {
  const res = await fetch('/clips')
  clips.value = await res.json()
  checked.value = {}
}

async function deleteClips(names) {
  await fetch('/clips', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ names }),
  })
  await fetchClips()
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
