// Compose the externally-visible RTSP URL from the current settings snapshot.
// The host comes from where the browser sees the page, not the API base —
// VLC/babycat will connect to the same host.

export function streamHost() {
  return window.location.hostname || 'localhost'
}

export function buildRtspUrl(settings) {
  if (!settings) return ''
  const host = streamHost()
  const port = settings.port
  const path = settings.rtsp_path || '/'
  return `rtsp://${host}:${port}${path}`
}

export function buildRtspUrlWithAuth(settings) {
  if (!settings) return ''
  const host = streamHost()
  const user = encodeURIComponent(settings.auth_user || '')
  const password = encodeURIComponent(settings.auth_password || '')
  return `rtsp://${user}:${password}@${host}:${settings.port}${settings.rtsp_path || '/'}`
}
