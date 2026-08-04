import { ref } from 'vue'
import { authFetch } from './useFetch.js'
import { t } from './useLocale.js'
import { APP_ENDPOINTS } from '../endpoints.js'

const PTZ_SPEED = 0.5
const status = ref(t('ptz.idle'))

async function post(body) {
  try {
    const res = await authFetch(APP_ENDPOINTS.ptz, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

function startMove(pan, tilt) {
  const panSpeed = pan * PTZ_SPEED
  const tiltSpeed = tilt * PTZ_SPEED
  status.value =
    panSpeed > 0 ? t('ptz.move.right') :
    panSpeed < 0 ? t('ptz.move.left') :
    tiltSpeed > 0 ? t('ptz.move.up') : t('ptz.move.down')
  post({ action: 'move', pan: panSpeed, tilt: tiltSpeed })
}

function stopMove() {
  status.value = t('ptz.stop')
  post({ action: 'stop' })
}

function forceStop() {
  status.value = t('ptz.forceStop')
  post({ action: 'stop' })
}

async function saveHome() {
  status.value = t('ptz.saving')
  const data = await post({ action: 'save' })
  status.value = data?.ok ? t('ptz.saved') : t('ptz.saveFailed')
  return !!data?.ok
}

async function gotoHome() {
  status.value = t('ptz.going')
  const data = await post({ action: 'goto' })
  status.value = data?.ok ? t('ptz.arrived') : t('ptz.noSavedHome')
}

export function usePtz() {
  return { status, startMove, stopMove, forceStop, saveHome, gotoHome }
}
