import { computed, readonly, ref } from 'vue'
import { API_ENDPOINTS, persistBabycatHost } from '../endpoints.js'

// @claude 60 s before expiry: long enough for the operator to read the warning
// @claude and press "extend" before the ephemeral session is cut.
const WARNING_LEAD_MS = 60_000
// @claude 60 s before expiry: the silent refresh of a kept-login session lands
// @claude well before the access token stops being accepted.
const AUTO_REFRESH_LEAD_MS = 60_000
const SESSION_KIND_KEY = 'session_kind'
const SESSION_KIND_PERSISTENT = 'persistent'
const SESSION_KIND_EPHEMERAL = 'ephemeral'
// @claude Why the session ended, carried across the full-page redirect to the
// @claude login page (a session replaced by a newer login is notified).
// @claude sessionStorage: per-tab, so the notice shows only in the kicked tab.
const LOGOUT_NOTICE_KEY = 'logout_notice'
// @claude SDD §6.2: the first login must change the initial password.
// @claude The flag rides the login response and is persisted with the session
// @claude so a reload keeps forcing the change until it actually happens.
const MUST_CHANGE_KEY = 'must_change_password'

const token = ref('')
const refreshToken = ref('')
const expiresAt = ref(0)
const sessionKind = ref(SESSION_KIND_PERSISTENT)
const mustChangePassword = ref(false)
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
    storage.removeItem(MUST_CHANGE_KEY)
  }
}

function writeStoredSession(kind, sessionToken, sessionRefreshToken) {
  clearStoredSession()
  if (!hasWindow()) return
  const storage = kind === SESSION_KIND_PERSISTENT ? window.localStorage : window.sessionStorage
  storage.setItem('token', sessionToken)
  storage.setItem('refresh_token', sessionRefreshToken)
  storage.setItem(SESSION_KIND_KEY, kind)
  // @claude Re-persisted on every session write (a refresh rotation rewrites
  // @claude the whole set) so the forced-change state survives until cleared.
  if (mustChangePassword.value) storage.setItem(MUST_CHANGE_KEY, '1')
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
      mustChange: storage.getItem(MUST_CHANGE_KEY) === '1',
    }
  }
  return { kind: SESSION_KIND_PERSISTENT, token: '', refreshToken: '', mustChange: false }
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

function finishSession({ redirect = true, reason = '' } = {}) {
  token.value = ''
  refreshToken.value = ''
  expiresAt.value = 0
  sessionKind.value = SESSION_KIND_PERSISTENT
  mustChangePassword.value = false
  extendingSession.value = false
  hideWarning()
  clearSessionTimers()
  clearStoredSession()
  if (reason && hasWindow()) {
    window.sessionStorage.setItem(LOGOUT_NOTICE_KEY, reason)
  }
  if (redirect) {
    redirectToLogin()
  }
}

function consumeLogoutNotice() {
  if (!hasWindow()) return ''
  const notice = window.sessionStorage.getItem(LOGOUT_NOTICE_KEY) || ''
  window.sessionStorage.removeItem(LOGOUT_NOTICE_KEY)
  return notice
}

async function revokeSessionTokens(sessionRefreshToken, sessionAccessToken) {
  // @claude Ephemeral sessions carry no refresh token, so the access token
  // @claude identifies the user for the server-side epoch bump.
  if (!sessionRefreshToken && !sessionAccessToken) return
  const headers = { 'Content-Type': 'application/json' }
  if (sessionAccessToken) {
    headers.Authorization = `Bearer ${sessionAccessToken}`
  }
  try {
    await fetch(API_ENDPOINTS.logout, {
      method: 'POST',
      headers,
      body: JSON.stringify({ refresh_token: sessionRefreshToken || null }),
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
  const { redirect = true, revoke = true, reason = '' } = options
  const sessionRefreshToken = refreshToken.value
  const sessionAccessToken = token.value
  finishSession({ redirect, reason })
  if (revoke) {
    await revokeSessionTokens(sessionRefreshToken, sessionAccessToken)
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
  mustChangePassword.value = !!stored.mustChange

  if (!token.value) {
    clearSessionTimers()
    return
  }

  expiresAt.value = resolveExpiryMs(token.value)
  if (!expiresAt.value || expiresAt.value <= Date.now()) {
    // @claude An expired access token does not end a kept-login session:
    // @claude the refresh token carries it across revisits. Only a session
    // @claude with no refresh token ends here. A network failure leaves the
    // @claude session intact — the next request's 401 path retries the refresh.
    if (refreshToken.value) {
      // @claude Intentionally ignored: a failed initial refresh is retried by the next request's 401 path.
      refreshAccessToken().catch(() => {})
    } else {
      void terminateSession({ redirect: false, revoke: true })
    }
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
    let res
    try {
      res = await fetch(API_ENDPOINTS.login, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, remember_me: rememberMe }),
      })
    } catch {
      // @claude Network-level failure: the backend host was never reached. Do not
      // @claude persist it so the operator can correct the host and retry.
      throw new Error('host unreachable')
    }
    // @claude The host responded (even on 401/429), so it is reachable — remember it.
    persistBabycatHost()
    if (res.status === 429) {
      // @claude The lockout length travels in the Retry-After header (seconds).
      // @claude It is readable cross-origin only when the router exposes it via
      // @claude CORS; the detail string is the fallback.
      const body = await res.json().catch(() => ({}))
      const header = Number(res.headers.get('Retry-After'))
      const fromDetail = Number((String(body.detail || '').match(/(\d+)\s*s\b/) || [])[1])
      const error = new Error('too many attempts')
      error.retryAfterSeconds = Number.isFinite(header) && header > 0
        ? header
        : (Number.isFinite(fromDetail) ? fromDetail : null)
      throw error
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || 'login failed')
    }
    const data = await res.json()
    // @claude Set before applySession so writeStoredSession persists the flag.
    mustChangePassword.value = !!data.must_change_password
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
    mustChangePassword: readonly(mustChangePassword),
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
    consumeLogoutNotice,
  }
}
