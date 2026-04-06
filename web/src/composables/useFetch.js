import { useAuth } from './useAuth.js'

/**
 * 인증 토큰을 자동으로 첨부하는 fetch 래퍼.
 * 401 응답 시 자동으로 토큰을 삭제하고 로그인 페이지로 리다이렉트한다.
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
