// fakecam backend client wrapper.
//
// The backend is on the same host as the web origin but on a different port
// (default 8090). The host is derived from window.location and can be
// overridden with the VITE_FAKECAM_API_BASE env at build time when needed.

const DEFAULT_API_PORT = 8090

function defaultBase() {
  if (import.meta.env.VITE_FAKECAM_API_BASE) {
    return import.meta.env.VITE_FAKECAM_API_BASE.replace(/\/$/, '')
  }
  const host = window.location.hostname || 'localhost'
  return `${window.location.protocol}//${host}:${DEFAULT_API_PORT}`
}

let apiBase = defaultBase()

export function getApiBase() {
  return apiBase
}

export function setApiBase(base) {
  apiBase = base.replace(/\/$/, '')
}

async function request(path, init = {}) {
  const res = await fetch(`${apiBase}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init.headers || {}) },
    ...init,
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}: ${detail}`)
  }
  return res.json()
}

export const api = {
  getLibrary: () => request('/api/library'),
  getPlaylist: () => request('/api/playlist'),
  getSettings: () => request('/api/settings'),
  addToPlaylist: (paths) =>
    request('/api/playlist/add', { method: 'POST', body: JSON.stringify({ paths }) }),
  removeFromPlaylist: (paths) =>
    request('/api/playlist/remove', { method: 'POST', body: JSON.stringify({ paths }) }),
  play: () => request('/api/playback/play', { method: 'POST' }),
  stop: () => request('/api/playback/stop', { method: 'POST' }),
  setMode: (patch) =>
    request('/api/playback/mode', { method: 'PUT', body: JSON.stringify(patch) }),
  updateSettings: (patch) =>
    request('/api/settings', { method: 'PUT', body: JSON.stringify(patch) }),
}
