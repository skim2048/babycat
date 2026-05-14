// Route ownership map for the dashboard.
// `api` owns authentication and persisted client-facing REST behavior.
// `app` owns runtime control, live state, and MJPEG/SSE endpoints.
// MediaMTX owns HLS/WebRTC transport endpoints.

const BACKEND_HOST_STORAGE_KEY = 'babycat_backend_host'

function hasWindow() {
  return typeof window !== 'undefined'
}

function stripTrailingSlash(value) {
  return value.replace(/\/+$/, '')
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

function getStoredBackendHost() {
  if (!hasWindow()) return ''
  return normalizeHost(window.localStorage.getItem(BACKEND_HOST_STORAGE_KEY))
}

function getConfiguredBackendHost() {
  return normalizeHost(import.meta.env.VITE_BABYCAT_HOST || import.meta.env.VITE_BACKEND_HOST)
}

function getConfiguredUrl(name) {
  return stripTrailingSlash(import.meta.env[name] || '')
}

function getBackendHost() {
  return getStoredBackendHost() || getConfiguredBackendHost()
}

function getServiceUrl(configName, port, path) {
  const configuredUrl = getConfiguredUrl(configName)
  if (configuredUrl && !getStoredBackendHost()) return `${configuredUrl}${path}`
  const backendHost = getBackendHost()
  if (backendHost) return `http://${backendHost}:${port}${path}`
  return path
}

export const API_ENDPOINTS = {
  get login() {
    return getServiceUrl('VITE_BABYCAT_API_URL', 8000, '/api/login')
  },
  get refresh() {
    return getServiceUrl('VITE_BABYCAT_API_URL', 8000, '/api/refresh')
  },
  get logout() {
    return getServiceUrl('VITE_BABYCAT_API_URL', 8000, '/api/logout')
  },
  get changePassword() {
    return getServiceUrl('VITE_BABYCAT_API_URL', 8000, '/api/change-password')
  },
  get camera() {
    return getServiceUrl('VITE_BABYCAT_API_URL', 8000, '/camera')
  },
  get clips() {
    return getServiceUrl('VITE_BABYCAT_API_URL', 8000, '/clips')
  },
  clipFile(name) {
    return getServiceUrl('VITE_BABYCAT_API_URL', 8000, `/clips/${encodeURIComponent(name)}`)
  },
}

export const APP_ENDPOINTS = {
  get prompt() {
    return getServiceUrl('VITE_BABYCAT_APP_URL', 8080, '/prompt')
  },
  get ptz() {
    return getServiceUrl('VITE_BABYCAT_APP_URL', 8080, '/ptz')
  },
  get events() {
    return getServiceUrl('VITE_BABYCAT_APP_URL', 8080, '/events')
  },
  get mjpeg() {
    return getServiceUrl('VITE_BABYCAT_APP_URL', 8080, '/stream')
  },
  get vlmSwitch() {
    return getServiceUrl('VITE_BABYCAT_APP_URL', 8080, '/vlm/switch')
  },
}

export function getBrowserHost() {
  return window.location.hostname
}

export function getEditableBackendHost() {
  return getStoredBackendHost() || getConfiguredBackendHost() || (hasWindow() ? getBrowserHost() : '')
}

export function setStoredBackendHost(host) {
  if (!hasWindow()) return ''
  const normalizedHost = normalizeHost(host)
  if (normalizedHost) {
    window.localStorage.setItem(BACKEND_HOST_STORAGE_KEY, normalizedHost)
  } else {
    window.localStorage.removeItem(BACKEND_HOST_STORAGE_KEY)
  }
  return normalizedHost
}

export function getStreamHost() {
  return getBackendHost() || getBrowserHost()
}

export function getHlsUrl(host = getStreamHost()) {
  const configuredUrl = getConfiguredUrl('VITE_BABYCAT_HLS_URL')
  if (configuredUrl && !getStoredBackendHost()) return configuredUrl
  return `http://${host}:8888/live/index.m3u8`
}

export function getWhepUrl(host = getStreamHost()) {
  const configuredUrl = getConfiguredUrl('VITE_BABYCAT_WHEP_URL')
  if (configuredUrl && !getStoredBackendHost()) return configuredUrl
  return `http://${host}:8889/live/whep`
}

export function getEventsUrl(token) {
  return `${APP_ENDPOINTS.events}?token=${encodeURIComponent(token)}`
}

export function getClipUrl(name, size, token) {
  return `${API_ENDPOINTS.clipFile(name)}?s=${size}&token=${encodeURIComponent(token)}`
}
