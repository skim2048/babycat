import { ref } from 'vue'
import { authFetch } from './useFetch.js'
import { APP_ENDPOINTS } from '../endpoints.js'

// @claude ONVIF velocity is normalized to [-1, 1]; the three levels map the
// @claude mockup's 저속·보통·고속 onto it. The backend passes values through.
const SPEED_FACTORS = [0.25, 0.5, 0.9]

const speedLevel = ref(1)

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
  const factor = SPEED_FACTORS[speedLevel.value] ?? SPEED_FACTORS[1]
  post({ action: 'move', pan: pan * factor, tilt: tilt * factor })
}

function stopMove() {
  post({ action: 'stop' })
}

function setSpeedLevel(level) {
  if (level >= 0 && level < SPEED_FACTORS.length) speedLevel.value = level
}

async function savePreset(slot) {
  const data = await post({ action: 'save', slot })
  return !!data?.ok
}

async function gotoPreset(slot) {
  const data = await post({ action: 'goto', slot })
  return !!data?.ok
}

export function usePtz() {
  return { speedLevel, setSpeedLevel, startMove, stopMove, savePreset, gotoPreset }
}
