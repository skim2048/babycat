import { useAuth } from './useAuth.js'

/**
 * fetch wrapper that automatically attaches the auth token.
 * On a 401 response it ends the current session and redirects to /login.
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

  return fetch(url, { ...options, headers }).then(async (res) => {
    if (res.status === 401) {
      const latestToken = getToken()
      if (latestToken && latestToken !== token) {
        const retryHeaders = { ...options.headers, Authorization: `Bearer ${latestToken}` }
        return fetch(url, { ...options, headers: retryHeaders })
      }
      logout({ redirect: true })
    }
    return res
  })
}
