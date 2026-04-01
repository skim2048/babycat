import { ref, reactive } from 'vue'

const config = reactive({
  ip: '',
  onvif_port: 2020,
  rtsp_port: 554,
  username: '',
  password: '',
  stream_path: 'stream1',
})
const configured = ref(false)
const status = ref('')
let loaded = false

async function load() {
  if (loaded) return
  loaded = true
  try {
    const res = await fetch('/camera')
    const data = await res.json()
    if (data.configured) {
      config.ip = data.ip || ''
      config.onvif_port = data.onvif_port || 2020
      config.rtsp_port = data.rtsp_port || 554
      config.username = data.username || ''
      config.password = data.password || ''
      config.stream_path = data.stream_path || 'stream1'
      configured.value = true
    }
  } catch {
    status.value = '설정 로드 실패'
  }
}

async function save() {
  status.value = '적용 중...'
  try {
    const res = await fetch('/camera', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...config }),
    })
    const data = await res.json()
    if (data.ok) {
      configured.value = true
      status.value = '적용 완료'
    } else {
      status.value = `오류: ${data.error || '알 수 없음'}`
    }
  } catch {
    status.value = '연결 실패'
  }
}

export function useCamera() {
  return { config, configured, status, load, save }
}
