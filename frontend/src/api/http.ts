import axios, { type AxiosError } from 'axios'
import { useAuthStore } from '../store/authStore'
import type { ApiErrorResponse, TokenResponse } from '../types/api'

// All requests go through the API Gateway (Module 3) — the frontend
// never talks to a backend service directly, matching the platform's
// own architecture (external traffic always enters through the gateway).
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export const http = axios.create({ baseURL: API_BASE_URL })

http.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let refreshPromise: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const { refreshToken, user, setSession, clearSession } = useAuthStore.getState()
  if (!refreshToken || !user) return null

  try {
    const resp = await axios.post<TokenResponse>(`${API_BASE_URL}/api/v1/auth/refresh`, {
      refresh_token: refreshToken,
    })
    setSession(resp.data.access_token, resp.data.refresh_token, user)
    return resp.data.access_token
  } catch {
    clearSession()
    return null
  }
}

// WHY a shared in-flight promise: if multiple dashboard queries 401 at
// the same moment (a realistic case — several polling requests firing
// close together right as the access token expires), each retrying with
// its own independent refresh call would race and could invalidate each
// other's new refresh token (Auth Service rotates on every use, see
// Module 2). Coalescing to one in-flight refresh avoids that.
http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiErrorResponse>) => {
    const original = error.config
    if (error.response?.status === 401 && original && !(original as { _retried?: boolean })._retried) {
      ;(original as { _retried?: boolean })._retried = true

      if (!refreshPromise) {
        refreshPromise = refreshAccessToken().finally(() => {
          refreshPromise = null
        })
      }
      const newToken = await refreshPromise
      if (newToken) {
        original.headers = original.headers ?? {}
        original.headers.Authorization = `Bearer ${newToken}`
        return http(original)
      }
    }
    return Promise.reject(error)
  },
)

export function getApiErrorMessage(error: unknown): string {
  if (axios.isAxiosError<ApiErrorResponse>(error) && error.response?.data?.error) {
    return error.response.data.error.message
  }
  return 'Something went wrong. Please try again.'
}
