import { computed, ref, reactive } from 'vue'
import { authFetch } from './useFetch.js'
import { API_ENDPOINTS } from '../endpoints.js'

const config = reactive({
  source_type: 'rtsp_camera',
  ip: '',
  rtsp_port: 554,
  username: '',
  password: '',
  password_set: false,
  stream_path: 'stream1',
  onvif_port: null,
  stream_protocol: 'hls',
})

export function normalizeStreamProtocol(value) {
  return value === 'webrtc' ? 'webrtc' : 'hls'
}

export function alternateStreamProtocol(value) {
  return normalizeStreamProtocol(value) === 'webrtc' ? 'hls' : 'webrtc'
}

// @claude configured: profile is persisted in camera.json (durable).
// @claude connecting: stream connection attempt in progress (transient).
// @claude connected:  stream is actually playing (transient; set by LiveStream).
const configured = ref(false)
const connecting = ref(false)
const connected = ref(false)
const status = ref('')
const reconnectKey = ref(0)  // @claude Bumped on successful profile save so LiveStream auto-reconnects.
let loaded = false

const preferredStreamProtocol = computed(() => normalizeStreamProtocol(config.stream_protocol))
const ptzEnabled = computed(() => config.onvif_port != null)
const cameraViewState = computed(() => {
  if (!configured.value) return 'unconfigured'
  if (connecting.value) return 'connecting'
  if (connected.value) return 'connected'
  return 'configured'
})

async function readCameraBody(res) {
  try {
    return await res.json()
  } catch {
    return null
  }
}

function cameraErrorMessage(body, fallback) {
  return body?.error || body?.detail || fallback
}

async function load() {
  if (loaded) return
  loaded = true
  try {
    const res = await authFetch(API_ENDPOINTS.camera)
    const data = await readCameraBody(res)
    if (!res.ok) {
      status.value = cameraErrorMessage(data, `카메라 설정을 불러오지 못했습니다. (${res.status})`)
      return
    }
    if (data.configured) {
      config.source_type = data.source_type || 'rtsp_camera'
      config.ip = data.ip || ''
      config.rtsp_port = data.rtsp_port || 554
      config.username = data.username || ''
      config.password = ''
      config.password_set = !!data.password_set
      config.stream_path = data.stream_path || 'stream1'
      config.onvif_port = data.onvif_port || null
      config.stream_protocol = normalizeStreamProtocol(data.stream_protocol)
      configured.value = true
      status.value = ''
    }
  } catch {
    status.value = '카메라 설정을 불러오지 못했습니다.'
  }
}

async function save() {
  status.value = ''
  try {
    const body = {
      source_type: config.source_type || 'rtsp_camera',
      ip: config.ip,
      rtsp_port: config.rtsp_port,
      username: config.username,
      stream_path: config.stream_path,
      onvif_port: config.onvif_port,
    }
    if (config.password) {
      body.password = config.password
    }
    body.stream_protocol = normalizeStreamProtocol(config.stream_protocol)
    const res = await authFetch(API_ENDPOINTS.camera, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await readCameraBody(res)
    if (!res.ok) {
      status.value = cameraErrorMessage(data, `저장 실패 (${res.status})`)
      return false
    }
    if (data?.ok) {
      configured.value = true
      config.password = ''
      config.password_set = true
      status.value = ''
      reconnectKey.value += 1
      return true
    } else {
      status.value = cameraErrorMessage(data, '저장 실패')
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
    preferredStreamProtocol, ptzEnabled, cameraViewState,
    load, save, disconnect, setConnected, setDisconnected,
  }
}
