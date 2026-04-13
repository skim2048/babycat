import { ref, reactive } from 'vue'
import { authFetch } from './useFetch.js'

const config = reactive({
  ip: '',
  rtsp_port: 554,
  username: '',
  password: '',
  stream_path: 'stream1',
  onvif_port: null,
  stream_protocol: 'hls',
})

// configured: camera.json에 설정이 저장된 상태 (영속)
// connecting: 스트림 연결 시도 중 (transient)
// connected:  스트림이 실제 재생 중 (transient, LiveStream이 설정)
const configured = ref(false)
const connecting = ref(false)
const connected = ref(false)
const status = ref('')
const reconnectKey = ref(0)  // 프로필 저장 성공 시 증가 → LiveStream이 자동 재연결
let loaded = false

async function load() {
  if (loaded) return
  loaded = true
  try {
    const res = await authFetch('/camera')
    if (!res.ok) return
    const data = await res.json()
    if (data.configured) {
      config.ip = data.ip || ''
      config.rtsp_port = data.rtsp_port || 554
      config.username = data.username || ''
      config.password = data.password || ''
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
      password: config.password,
      stream_path: config.stream_path,
    }
    if (config.onvif_port) {
      body.onvif_port = config.onvif_port
    }
    body.stream_protocol = config.stream_protocol
    const res = await authFetch('/camera', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await res.json()
    if (data.ok) {
      configured.value = true
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

function deleteProfile() {
  configured.value = false
  connecting.value = false
  connected.value = false
  status.value = ''
}

export function useCamera() {
  return {
    config, configured, connecting, connected, status, reconnectKey,
    load, save, disconnect, deleteProfile, setConnected, setDisconnected,
  }
}
