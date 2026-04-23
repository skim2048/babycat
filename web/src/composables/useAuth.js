import { computed, readonly, ref } from 'vue'
import { API_ENDPOINTS } from '../endpoints.js'

const WARNING_LEAD_MS = 60_000

const token = ref(localStorage.getItem('token') || '')
const refreshToken = ref(localStorage.getItem('refresh_token') || '')
const expiresAt = ref(0)
const warningVisible = ref(false)
const remainingSeconds = ref(0)
const extendingSession = ref(false)

let warningTimer = null
let logoutTimer = null
let countdownTimer = null
let refreshPromise = null

function clearTimer(timer) {
  if (timer) {
    clearTimeout(timer)
  }
  return null
}

function clearIntervalTimer(timer) {
  if (timer) {
    clearInterval(timer)
  }
  return null
}

function decodeTokenPayload(jwt) {
  try {
    const parts = jwt.split('.')
    if (parts.length !== 3) return null
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const json = decodeURIComponent(
      atob(base64)
        .split('')
        .map((char) => `%${char.charCodeAt(0).toString(16).padStart(2, '0')}`)
        .join(''),
    )
    return JSON.parse(json)
  } catch {
    return null
  }
}

function resolveExpiryMs(jwt, expiresInSeconds) {
  const payload = decodeTokenPayload(jwt)
  if (payload?.exp) {
    return Number(payload.exp) * 1000
  }
  if (Number.isFinite(expiresInSeconds)) {
    return Date.now() + (Number(expiresInSeconds) * 1000)
  }
  return 0
}

function stopCountdown() {
  countdownTimer = clearIntervalTimer(countdownTimer)
  remainingSeconds.value = 0
}

function hideWarning() {
  warningVisible.value = false
  stopCountdown()
}

function clearSessionTimers() {
  warningTimer = clearTimer(warningTimer)
  logoutTimer = clearTimer(logoutTimer)
  stopCountdown()
}

function updateRemainingSeconds() {
  if (!expiresAt.value) {
    remainingSeconds.value = 0
    return
  }
  remainingSeconds.value = Math.max(0, Math.ceil((expiresAt.value - Date.now()) / 1000))
}

function showWarning() {
  if (!token.value || !expiresAt.value) return
  warningVisible.value = true
  updateRemainingSeconds()
  countdownTimer = clearIntervalTimer(countdownTimer)
  countdownTimer = setInterval(() => {
    updateRemainingSeconds()
  }, 1000)
}

function redirectToLogin() {
  if (typeof window === 'undefined') return
  if (window.location.pathname === '/login') return
  window.location.replace('/login')
}

function terminateSession({ redirect = true } = {}) {
  token.value = ''
  refreshToken.value = ''
  expiresAt.value = 0
  extendingSession.value = false
  clearSessionTimers()
  localStorage.removeItem('token')
  localStorage.removeItem('refresh_token')
  if (redirect) {
    redirectToLogin()
  }
}

function scheduleSessionTimers() {
  clearSessionTimers()
  if (!token.value || !expiresAt.value) return

  const now = Date.now()
  if (expiresAt.value <= now) {
    terminateSession({ redirect: true })
    return
  }

  const warningAt = expiresAt.value - WARNING_LEAD_MS
  if (warningAt <= now) {
    showWarning()
  } else {
    warningTimer = setTimeout(() => {
      showWarning()
    }, warningAt - now)
  }

  logoutTimer = setTimeout(() => {
    terminateSession({ redirect: true })
  }, expiresAt.value - now)
}

function applySession(data) {
  token.value = data.token
  localStorage.setItem('token', data.token)
  if (data.refresh_token) {
    refreshToken.value = data.refresh_token
    localStorage.setItem('refresh_token', data.refresh_token)
  } else {
    refreshToken.value = ''
    localStorage.removeItem('refresh_token')
  }
  expiresAt.value = resolveExpiryMs(data.token, data.expires_in)
  hideWarning()
  scheduleSessionTimers()
}

function initializeSession() {
  if (!token.value) {
    clearSessionTimers()
    return
  }
  expiresAt.value = resolveExpiryMs(token.value)
  if (!expiresAt.value || expiresAt.value <= Date.now()) {
    terminateSession({ redirect: false })
    return
  }
  scheduleSessionTimers()
}

initializeSession()

export function useAuth() {
  const isAuthenticated = computed(() => !!token.value)
  const canExtendSession = computed(() => !!refreshToken.value)

  async function login(username, password, rememberMe = false) {
    const res = await fetch(API_ENDPOINTS.login, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, remember_me: rememberMe }),
    })
    if (res.status === 429) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || 'too many attempts')
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || 'login failed')
    }
    const data = await res.json()
    applySession(data)
  }

  function logout(options) {
    terminateSession(options)
  }

  async function refreshAccessToken({ interactive = false } = {}) {
    if (!refreshToken.value) return false
    if (refreshPromise) return refreshPromise

    if (interactive) {
      extendingSession.value = true
    }

    refreshPromise = (async () => {
      const res = await fetch(API_ENDPOINTS.refresh, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken.value }),
      })
      if (!res.ok) {
        terminateSession({ redirect: true })
        return false
      }

      const data = await res.json()
      applySession(data)
      return true
    })().finally(() => {
      extendingSession.value = false
      refreshPromise = null
    })

    return refreshPromise
  }

  async function extendSession() {
    return refreshAccessToken({ interactive: true })
  }

  function getToken() {
    return token.value
  }

  return {
    accessToken: readonly(token),
    storedRefreshToken: readonly(refreshToken),
    sessionExpiresAt: readonly(expiresAt),
    warningVisible: readonly(warningVisible),
    remainingSeconds: readonly(remainingSeconds),
    extendingSession: readonly(extendingSession),
    isAuthenticated,
    canExtendSession,
    login,
    logout,
    refreshAccessToken,
    extendSession,
    getToken,
  }
}
