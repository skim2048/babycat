// Reactive shared state, hydrated by SSE.
//
// Components read directly from `state`. The SSE channel pushes playlist,
// mode, and settings updates. The library is fetched once at boot via
// `refreshLibrary()` because the backend does not currently emit a
// library-changed event.

import { reactive } from 'vue'
import { api, getApiBase } from './api.js'

export const state = reactive({
  library: null,
  playlist: null,
  mode: null,
  settings: null,
  sseConnected: false,
  libraryError: '',
  treeChecked: new Set(),
  playlistChecked: new Set(),
  mutationError: '',
})

let eventSource = null
let reconnectTimer = null

export async function refreshLibrary() {
  try {
    const res = await api.getLibrary()
    state.library = res.tree
    state.libraryError = ''
  } catch (e) {
    state.libraryError = String(e)
  }
}

export function connect() {
  if (eventSource) return
  refreshLibrary()
  openStream()
}

export async function addCheckedToPlaylist() {
  const paths = Array.from(state.treeChecked)
  if (paths.length === 0) return
  state.mutationError = ''
  try {
    await api.addToPlaylist(paths)
  } catch (e) {
    state.mutationError = String(e)
  }
}

export async function removeCheckedFromPlaylist() {
  const paths = Array.from(state.playlistChecked)
  if (paths.length === 0) return
  state.mutationError = ''
  try {
    await api.removeFromPlaylist(paths)
    // @claude Backend removed those items; drop their check entries so the
    // @claude trash button doesn't keep stale references the user can no
    // @claude longer see.
    paths.forEach((p) => state.playlistChecked.delete(p))
  } catch (e) {
    state.mutationError = String(e)
  }
}

function openStream() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  const url = `${getApiBase()}/api/events`
  eventSource = new EventSource(url)
  eventSource.onopen = () => {
    state.sseConnected = true
  }
  eventSource.onerror = () => {
    state.sseConnected = false
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    // @claude Browser EventSource auto-reconnects, but reopening explicitly
    // @claude prevents stale connections when the backend restarts.
    if (!reconnectTimer) {
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null
        openStream()
      }, 2000)
    }
  }
  eventSource.onmessage = (e) => {
    let ev
    try {
      ev = JSON.parse(e.data)
    } catch {
      return
    }
    if (ev.type === 'playlist') state.playlist = ev.playlist
    else if (ev.type === 'mode') state.mode = ev.mode
    else if (ev.type === 'settings') state.settings = ev.settings
  }
}
