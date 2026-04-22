import { ref, reactive } from 'vue'
import { authFetch } from './useFetch.js'
import { APP_ENDPOINTS } from '../endpoints.js'

const config = reactive({
  ip: '',
  rtsp_port: 554,
  username: '',
  password: '',
  password_set: false,
  stream_path: 'stream1',
  onvif_port: null,
  stream_protocol: 'hls',
})

// @claude configured: profile is persisted in camera.json (durable).
// @claude connecting: stream connection attempt in progress (transient).
// @claude connected:  stream is actually playing (transient; set by LiveStream).
const configured = ref(false)
const connecting = ref(false)
const connected = ref(false)
const status = ref('')
const reconnectKey = ref(0)  // @claude Bumped on successful profile save so LiveStream auto-reconnects.
let loaded = false

async function load() {
  if (loaded) return
  loaded = true
  try {
    const res = await authFetch(APP_ENDPOINTS.camera)
    if (!res.ok) return
    const data = await res.json()
    if (data.configured) {
      config.ip = data.ip || ''
      config.rtsp_port = data.rtsp_port || 554
      config.username = data.username || ''
      config.password = ''
      config.password_set = !!data.password_set
      config.stream_path = data.stream_path || 'stream1'
      config.onvif_port = data.onvif_port || null
      config.stream_protocol = data.stream_protocol || 'hls'
      configured.value = true
    }
  } catch {
    status.value = 'Failed to load config'
  }
}

async function save() {
  status.value = ''
  try {
    const body = {
      ip: config.ip,
      rtsp_port: config.rtsp_port,
      username: config.username,
      stream_path: config.stream_path,
    }
    if (config.password) {
      body.password = config.password
    }
    if (config.onvif_port) {
      body.onvif_port = config.onvif_port
    }
    body.stream_protocol = config.stream_protocol
    const res = await authFetch(APP_ENDPOINTS.camera, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await res.json()
    if (data.ok) {
      configured.value = true
      config.password = ''
      config.password_set = true
      reconnectKey.value += 1
      return true
    } else {
      status.value = `Error: ${data.error || 'unknown'}`
    }
  } catch {
    status.value = '저장 실패'
  }
  return false
}

function setConnected() {
  connecting.value = false
  connected.value = true
}

function setDisconnected() {
  connecting.value = false
  connected.value = false
}

function disconnect() {
  connecting.value = false
  connected.value = false
}

export function useCamera() {
  return {
    config, configured, connecting, connected, status, reconnectKey,
    load, save, disconnect, setConnected, setDisconnected,
  }
}
