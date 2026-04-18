import { useAuth } from './useAuth.js'

/**
 * fetch wrapper that automatically attaches the auth token.
 * On a 401 response it clears the token and redirects to /login.
 *
 * @claude
 */
export function authFetch(url, options = {}) {
  const { getToken, logout } = useAuth()
  const token = getToken()

  const headers = { ...options.headers }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  return fetch(url, { ...options, headers }).then((res) => {
    if (res.status === 401) {
      logout()
      window.location.href = '/login'
    }
    return res
  })
}
