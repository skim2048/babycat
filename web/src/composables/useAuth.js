import { computed, readonly, ref } from 'vue'
import { API_ENDPOINTS } from '../endpoints.js'

const WARNING_LEAD_MS = 60_000
const AUTO_REFRESH_LEAD_MS = 60_000
const SESSION_KIND_KEY = 'session_kind'
const SESSION_KIND_PERSISTENT = 'persistent'
const SESSION_KIND_EPHEMERAL = 'ephemeral'

const token = ref('')
const refreshToken = ref('')
const expiresAt = ref(0)
const sessionKind = ref(SESSION_KIND_PERSISTENT)
const warningVisible = ref(false)
const remainingSeconds = ref(0)
const sessionRemainingSeconds = ref(0)
const extendingSession = ref(false)

let warningTimer = null
let logoutTimer = null
let countdownTimer = null
let autoRefreshTimer = null
let sessionClockTimer = null
let refreshPromise = null

function hasWindow() {
  return typeof window !== 'undefined'
}

function getStorages() {
  if (!hasWindow()) return []
  return [
    [SESSION_KIND_PERSISTENT, window.localStorage],
    [SESSION_KIND_EPHEMERAL, window.sessionStorage],
  ]
}

function clearTimer(timer) {
  if (timer) clearTimeout(timer)
  return null
}

function clearIntervalTimer(timer) {
  if (timer) clearInterval(timer)
  return null
}

function clearStoredSession() {
  for (const [, storage] of getStorages()) {
    storage.removeItem('token')
    storage.removeItem('refresh_token')
    storage.removeItem(SESSION_KIND_KEY)
  }
}

function writeStoredSession(kind, sessionToken, sessionRefreshToken) {
  clearStoredSession()
  if (!hasWindow()) return
  const storage = kind === SESSION_KIND_PERSISTENT ? window.localStorage : window.sessionStorage
  storage.setItem('token', sessionToken)
  storage.setItem('refresh_token', sessionRefreshToken)
  storage.setItem(SESSION_KIND_KEY, kind)
}

function loadStoredSession() {
  for (const [kind, storage] of getStorages()) {
    const storedToken = storage.getItem('token') || ''
    const storedRefreshToken = storage.getItem('refresh_token') || ''
    if (!storedToken) continue
    return {
      kind: storage.getItem(SESSION_KIND_KEY) || kind,
      token: storedToken,
      refreshToken: storedRefreshToken,
    }
  }
  return { kind: SESSION_KIND_PERSISTENT, token: '', refreshToken: '' }
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

function stopSessionClock() {
  sessionClockTimer = clearIntervalTimer(sessionClockTimer)
  sessionRemainingSeconds.value = 0
}

function hideWarning() {
  warningVisible.value = false
  stopCountdown()
}

function updateSessionRemainingSeconds() {
  if (!expiresAt.value) {
    sessionRemainingSeconds.value = 0
    return
  }
  sessionRemainingSeconds.value = Math.max(0, Math.ceil((expiresAt.value - Date.now()) / 1000))
}

function startSessionClock() {
  stopSessionClock()
  if (!token.value || !expiresAt.value) return
  updateSessionRemainingSeconds()
  sessionClockTimer = setInterval(() => {
    updateSessionRemainingSeconds()
  }, 1000)
}

function updateRemainingSeconds() {
  if (!expiresAt.value) {
    remainingSeconds.value = 0
    return
  }
  remainingSeconds.value = Math.max(0, Math.ceil((expiresAt.value - Date.now()) / 1000))
}

function showWarning() {
  if (!token.value || !expiresAt.value || sessionKind.value === SESSION_KIND_PERSISTENT) return
  warningVisible.value = true
  updateRemainingSeconds()
  countdownTimer = clearIntervalTimer(countdownTimer)
  countdownTimer = setInterval(() => {
    updateRemainingSeconds()
  }, 1000)
}

function clearSessionTimers() {
  warningTimer = clearTimer(warningTimer)
  logoutTimer = clearTimer(logoutTimer)
  autoRefreshTimer = clearTimer(autoRefreshTimer)
  stopCountdown()
}

function redirectToLogin() {
  if (!hasWindow()) return
  if (window.location.pathname === '/login') return
  window.location.replace('/login')
}

function finishSession({ redirect = true } = {}) {
  token.value = ''
  refreshToken.value = ''
  expiresAt.value = 0
  sessionKind.value = SESSION_KIND_PERSISTENT
  extendingSession.value = false
  hideWarning()
  clearSessionTimers()
  clearStoredSession()
  if (redirect) {
    redirectToLogin()
  }
}

async function revokeRefreshToken(sessionRefreshToken) {
  if (!sessionRefreshToken) return
  try {
    await fetch(API_ENDPOINTS.logout, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: sessionRefreshToken }),
    })
  } catch {
    // @claude Best-effort server-side logout; local cleanup is still required.
  }
}

function applySession(data, kind = sessionKind.value) {
  token.value = data.token
  refreshToken.value = data.refresh_token || ''
  sessionKind.value = kind
  expiresAt.value = resolveExpiryMs(data.token, data.expires_in)
  writeStoredSession(kind, token.value, refreshToken.value)
  hideWarning()
  startSessionClock()
  scheduleSessionTimers()
}

async function terminateSession(options = {}) {
  const { redirect = true, revoke = true } = options
  const sessionRefreshToken = refreshToken.value
  finishSession({ redirect })
  if (revoke) {
    await revokeRefreshToken(sessionRefreshToken)
  }
}

async function refreshAccessToken({ interactive = false } = {}) {
  if (!refreshToken.value) return false
  if (refreshPromise) return refreshPromise

  if (interactive) {
    extendingSession.value = true
  }

  const currentKind = sessionKind.value
  refreshPromise = (async () => {
    const res = await fetch(API_ENDPOINTS.refresh, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken.value }),
    })
    if (!res.ok) {
      await terminateSession({ redirect: true, revoke: false })
      return false
    }

    const data = await res.json()
    applySession(data, currentKind)
    return true
  })().finally(() => {
    extendingSession.value = false
    refreshPromise = null
  })

  return refreshPromise
}

function scheduleSessionTimers() {
  clearSessionTimers()
  if (!token.value || !expiresAt.value) return

  const now = Date.now()
  if (expiresAt.value <= now) {
    void terminateSession({ redirect: true, revoke: true })
    return
  }

  if (sessionKind.value === SESSION_KIND_PERSISTENT) {
    if (!refreshToken.value) {
      logoutTimer = setTimeout(() => {
        void terminateSession({ redirect: true, revoke: false })
      }, expiresAt.value - now)
      return
    }
    const refreshDelay = Math.max(0, expiresAt.value - now - AUTO_REFRESH_LEAD_MS)
    autoRefreshTimer = setTimeout(() => {
      void refreshAccessToken()
    }, refreshDelay)
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
    void terminateSession({ redirect: true, revoke: true })
  }, expiresAt.value - now)
}

function initializeSession() {
  const stored = loadStoredSession()
  token.value = stored.token
  refreshToken.value = stored.refreshToken
  sessionKind.value = stored.kind

  if (!token.value) {
    clearSessionTimers()
    return
  }

  expiresAt.value = resolveExpiryMs(token.value)
  if (!expiresAt.value || expiresAt.value <= Date.now()) {
    void terminateSession({ redirect: false, revoke: true })
    return
  }

  startSessionClock()
  scheduleSessionTimers()
}

initializeSession()

export function useAuth() {
  const isAuthenticated = computed(() => !!token.value)
  const isPersistentSession = computed(() => sessionKind.value === SESSION_KIND_PERSISTENT)
  const canExtendSession = computed(() =>
    sessionKind.value === SESSION_KIND_EPHEMERAL && !!refreshToken.value,
  )

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
    applySession(data, rememberMe ? SESSION_KIND_PERSISTENT : SESSION_KIND_EPHEMERAL)
  }

  function logout(options) {
    void terminateSession(options)
  }

  async function extendSession() {
    if (!canExtendSession.value) return false
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
    sessionRemainingSeconds: readonly(sessionRemainingSeconds),
    extendingSession: readonly(extendingSession),
    isAuthenticated,
    isPersistentSession,
    canExtendSession,
    login,
    logout,
    refreshAccessToken,
    extendSession,
    getToken,
  }
}
