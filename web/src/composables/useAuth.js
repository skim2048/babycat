import { ref, computed } from 'vue'

const token = ref(localStorage.getItem('token') || '')
const refreshToken = ref(localStorage.getItem('refresh_token') || '')

export function useAuth() {
  const isAuthenticated = computed(() => !!token.value)

  async function login(username, password, rememberMe = false) {
    const res = await fetch('/api/login', {
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
    token.value = data.token
    localStorage.setItem('token', data.token)
    if (data.refresh_token) {
      refreshToken.value = data.refresh_token
      localStorage.setItem('refresh_token', data.refresh_token)
    } else {
      refreshToken.value = ''
      localStorage.removeItem('refresh_token')
    }
  }

  function logout() {
    token.value = ''
    refreshToken.value = ''
    localStorage.removeItem('token')
    localStorage.removeItem('refresh_token')
  }

  async function refreshAccessToken() {
    // @chatgpt Refresh and rotate tokens together so an old refresh token cannot
    // @chatgpt be replayed indefinitely after it has been used once.
    if (!refreshToken.value) return false

    const res = await fetch('/api/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken.value }),
    })
    if (!res.ok) {
      logout()
      return false
    }

    const data = await res.json()
    token.value = data.token
    localStorage.setItem('token', data.token)
    refreshToken.value = data.refresh_token
    localStorage.setItem('refresh_token', data.refresh_token)
    return true
  }

  function getToken() {
    return token.value
  }

  function getRefreshToken() {
    return refreshToken.value
  }

  return {
    isAuthenticated,
    login,
    logout,
    refreshAccessToken,
    getToken,
    getRefreshToken,
  }
}
