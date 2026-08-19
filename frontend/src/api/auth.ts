import { http } from './http'
import type { TokenResponse, UserResponse } from '../types/api'

export async function login(email: string, password: string): Promise<TokenResponse> {
  const resp = await http.post<TokenResponse>('/api/v1/auth/login', { email, password })
  return resp.data
}

export async function fetchCurrentUser(): Promise<UserResponse> {
  const resp = await http.get<UserResponse>('/api/v1/auth/me')
  return resp.data
}

export async function logout(refreshToken: string): Promise<void> {
  await http.post('/api/v1/auth/logout', { refresh_token: refreshToken })
}
