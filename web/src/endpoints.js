// Route ownership map for the dashboard.
// `api` owns authentication and persisted client-facing REST behavior.
// `app` owns runtime control, live state, and MJPEG/SSE endpoints.
// MediaMTX owns HLS/WebRTC transport endpoints.

const BABYCAT_HOST_STORAGE_KEY = 'babycat_host'

function hasWindow() {
  return typeof window !== 'undefined'
}

function normalizeHost(value) {
  const raw = String(value || '').trim()
  if (!raw) return ''
  try {
    return new URL(raw.includes('://') ? raw : `http://${raw}`).hostname
  } catch {
    return raw.replace(/^https?:\/\//, '').split('/')[0].split(':')[0]
  }
}

function getStoredBabycatHost() {
  if (!hasWindow()) return ''
  return normalizeHost(window.localStorage.getItem(BABYCAT_HOST_STORAGE_KEY))
}

function getConfiguredBabycatHost() {
  return normalizeHost(import.meta.env.VITE_BABYCAT_HOST)
}

function getBabycatHost() {
  return getStoredBabycatHost() || getConfiguredBabycatHost() || getBrowserHost()
}

function getApiUrl(path) {
  return `http://${getBabycatHost()}:8000${path}`
}

export const API_ENDPOINTS = {
  get login() {
    return getApiUrl('/api/login')
  },
  get refresh() {
    return getApiUrl('/api/refresh')
  },
  get logout() {
    return getApiUrl('/api/logout')
  },
  get changePassword() {
    return getApiUrl('/api/change-password')
  },
  get camera() {
    return getApiUrl('/camera')
  },
  get clips() {
    return getApiUrl('/clips')
  },
  clipFile(name) {
    return getApiUrl(`/clips/${encodeURIComponent(name)}`)
  },
}

export const APP_ENDPOINTS = {
  prompt: '/prompt',
  ptz: '/ptz',
  events: '/events',
  mjpeg: '/stream',
  vlmSwitch: '/vlm/switch',
}

export function getBrowserHost() {
  return window.location.hostname
}

export function getEditableBabycatHost() {
  return getStoredBabycatHost() || getConfiguredBabycatHost() || (hasWindow() ? getBrowserHost() : '')
}

export function setStoredBabycatHost(host) {
  if (!hasWindow()) return ''
  const normalizedHost = normalizeHost(host)
  if (normalizedHost) {
    window.localStorage.setItem(BABYCAT_HOST_STORAGE_KEY, normalizedHost)
  } else {
    window.localStorage.removeItem(BABYCAT_HOST_STORAGE_KEY)
  }
  return normalizedHost
}

export function getStreamHost() {
  return getBabycatHost()
}

export function getHlsUrl(host = getStreamHost()) {
  return `http://${host}:8888/live/index.m3u8`
}

export function getWhepUrl(host = getStreamHost()) {
  return `http://${host}:8889/live/whep`
}

export function getEventsUrl(token) {
  return `${APP_ENDPOINTS.events}?token=${encodeURIComponent(token)}`
}

export function getClipUrl(name, size, token) {
  return `${API_ENDPOINTS.clipFile(name)}?s=${size}&token=${encodeURIComponent(token)}`
}
