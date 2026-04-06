import { ref, computed } from 'vue'

const token = ref(localStorage.getItem('token') || '')
const mustChangePassword = ref(false)

export function useAuth() {
  const isAuthenticated = computed(() => !!token.value)

  async function login(username, password) {
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
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
    mustChangePassword.value = data.must_change_password
  }

  function logout() {
    token.value = ''
    mustChangePassword.value = false
    localStorage.removeItem('token')
  }

  function getToken() {
    return token.value
  }

  function clearMustChangePassword() {
    mustChangePassword.value = false
  }

  return {
    isAuthenticated,
    mustChangePassword,
    login,
    logout,
    getToken,
    clearMustChangePassword,
  }
}
