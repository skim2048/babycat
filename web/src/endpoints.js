// Route ownership map for the dashboard.
// `api` owns authentication and persisted client-facing REST behavior.
// `app` owns runtime control, live state, and MJPEG/SSE endpoints.
// MediaMTX owns HLS/WebRTC transport endpoints.

export const API_ENDPOINTS = {
  login: '/api/login',
  refresh: '/api/refresh',
  changePassword: '/api/change-password',
  clips: '/clips',
  clipFile(name) {
    return `/clips/${encodeURIComponent(name)}`
  },
}

export const APP_ENDPOINTS = {
  camera: '/camera',
  prompt: '/prompt',
  ptz: '/ptz',
  events: '/events',
  mjpeg: '/stream',
  vlmSwitch: '/vlm/switch',
}

export function getHlsUrl(host) {
  return `http://${host}:8888/live/index.m3u8`
}

export function getWhepUrl(host) {
  return `http://${host}:8889/live/whep`
}

export function getEventsUrl(token) {
  return `${APP_ENDPOINTS.events}?token=${encodeURIComponent(token)}`
}

export function getClipUrl(name, size, token) {
  return `${API_ENDPOINTS.clipFile(name)}?s=${size}&token=${encodeURIComponent(token)}`
}
