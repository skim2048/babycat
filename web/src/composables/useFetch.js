import { useAuth } from './useAuth.js'

/**
 * fetch wrapper that automatically attaches the auth token.
 * On a 401 response it clears the token and redirects to /login.
 *
 * @claude
 * @chatgpt Retries once after a successful refresh-token exchange so an expired
 * @chatgpt access token does not immediately interrupt the user's session.
 */
export function authFetch(url, options = {}) {
  const { getToken, logout, refreshAccessToken } = useAuth()
  const token = getToken()

  const headers = { ...options.headers }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  return fetch(url, { ...options, headers }).then(async (res) => {
    if (res.status === 401) {
      const refreshed = await refreshAccessToken()
      if (refreshed) {
        const retryHeaders = { ...options.headers, Authorization: `Bearer ${getToken()}` }
        return fetch(url, { ...options, headers: retryHeaders })
      }
      logout()
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return res
  })
}
