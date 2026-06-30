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

// @claude Host typed on the login page for the current page load. Kept in memory so the
// @claude login request can target it before the host is known to be reachable;
// @claude persistBabycatHost() writes it to localStorage only after the backend responds.
let sessionBabycatHost = ''

function getBabycatHost() {
  return sessionBabycatHost || getStoredBabycatHost() || getBrowserHost()
}

function getApiUrl(path) {
  return `http://${getBabycatHost()}:8000${path}`
}

function getAppUrl(path) {
  return `http://${getBabycatHost()}:8080${path}`
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
  get prompt() {
    return getAppUrl('/prompt')
  },
  get ptz() {
    return getAppUrl('/ptz')
  },
  get events() {
    return getAppUrl('/events')
  },
  get mjpeg() {
    return getAppUrl('/stream')
  },
  get vlmSwitch() {
    return getAppUrl('/vlm/switch')
  },
}

export function getBrowserHost() {
  return window.location.hostname
}

export function getEditableBabycatHost() {
  return sessionBabycatHost || getStoredBabycatHost() || (hasWindow() ? getBrowserHost() : '')
}

// @claude Activate a host for the current page load without persisting it. The login
// @claude request targets this value; call persistBabycatHost() once the backend responds.
export function applyBabycatHost(host) {
  sessionBabycatHost = normalizeHost(host)
  return sessionBabycatHost
}

// @claude Persist the active host once the backend has responded (i.e. the host is
// @claude reachable). An empty host clears the stored value so resolution falls back
// @claude to the browser host.
export function persistBabycatHost() {
  if (!hasWindow()) return
  if (sessionBabycatHost) {
    window.localStorage.setItem(BABYCAT_HOST_STORAGE_KEY, sessionBabycatHost)
  } else {
    window.localStorage.removeItem(BABYCAT_HOST_STORAGE_KEY)
  }
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
