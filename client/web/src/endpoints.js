// Route map for the dashboard.
// The router (port 8000) is the single entry point for everything —
// control, SSE/MJPEG relays, and the HLS/WHEP streaming relays.
// Only WebRTC media (UDP 8189) bypasses it.

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
    return getApiUrl('/prompt')
  },
  get ptz() {
    return getApiUrl('/ptz')
  },
  get analysisStart() {
    return getApiUrl('/analysis/start')
  },
  get analysisStop() {
    return getApiUrl('/analysis/stop')
  },
  get streamingStart() {
    return getApiUrl('/streaming/start')
  },
  get streamingStop() {
    return getApiUrl('/streaming/stop')
  },
  // @claude Live state SSE. The router path is /state (its /events carries the
  // @claude stored event history).
  get events() {
    return getApiUrl('/state')
  },
  get mjpeg() {
    return getApiUrl('/stream')
  },
  get vlmSwitch() {
    return getApiUrl('/vlm/switch')
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

// @claude HLS and WHEP go through the router relay (single entry). Only the
// @claude WebRTC media itself flows directly from the streamer (UDP 8189).
export function getHlsUrl(host = getStreamHost()) {
  return `http://${host}:8000/live/hls/index.m3u8`
}

export function getWhepUrl(host = getStreamHost()) {
  return `http://${host}:8000/live/whep`
}

export function getEventsUrl(token) {
  return `${APP_ENDPOINTS.events}?token=${encodeURIComponent(token)}`
}

export function getClipUrl(name, size, token) {
  return `${API_ENDPOINTS.clipFile(name)}?s=${size}&token=${encodeURIComponent(token)}`
}
