import { ref } from 'vue'

const PTZ_SPEED = 0.5
const status = ref('대기')

function post(body) {
  return fetch('/ptz', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

function startMove(pan, tilt) {
  const p = pan * PTZ_SPEED
  const t = tilt * PTZ_SPEED
  status.value =
    p > 0 ? '→ 오른쪽 이동 중' :
    p < 0 ? '← 왼쪽 이동 중' :
    t > 0 ? '↑ 위 이동 중' : '↓ 아래 이동 중'
  post({ action: 'move', pan: p, tilt: t })
}

function stopMove() {
  status.value = '정지'
  post({ action: 'stop' })
}

function forceStop() {
  status.value = '강제 정지'
  post({ action: 'stop' })
}

async function saveHome() {
  status.value = '저장 중...'
  const res = await post({ action: 'save' })
  const data = await res.json()
  status.value = data.ok ? '저장 완료' : '저장 실패 (위치 미확인)'
}

async function gotoHome() {
  status.value = '이동 중...'
  const res = await post({ action: 'goto' })
  const data = await res.json()
  status.value = data.ok ? '이동 완료' : '저장된 위치 없음'
}

export function usePtz() {
  return { status, startMove, stopMove, forceStop, saveHome, gotoHome }
}
