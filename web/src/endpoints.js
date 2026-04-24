// Route ownership map for the dashboard.
// `api` owns authentication and persisted client-facing REST behavior.
// `app` owns runtime control, live state, and MJPEG/SSE endpoints.
// MediaMTX owns HLS/WebRTC transport endpoints.

export const API_ENDPOINTS = {
  login: '/api/login',
  refresh: '/api/refresh',
  logout: '/api/logout',
  changePassword: '/api/change-password',
  camera: '/camera',
  clips: '/clips',
  clipFile(name) {
    return `/clips/${encodeURIComponent(name)}`
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

export function getHlsUrl(host = getBrowserHost()) {
  return `http://${host}:8888/live/index.m3u8`
}

export function getWhepUrl(host = getBrowserHost()) {
  return `http://${host}:8889/live/whep`
}

export function getEventsUrl(token) {
  return `${APP_ENDPOINTS.events}?token=${encodeURIComponent(token)}`
}

export function getClipUrl(name, size, token) {
  return `${API_ENDPOINTS.clipFile(name)}?s=${size}&token=${encodeURIComponent(token)}`
}
