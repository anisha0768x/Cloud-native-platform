import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { UserResponse } from '../types/api'

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  user: UserResponse | null
  setSession: (accessToken: string, refreshToken: string, user: UserResponse) => void
  clearSession: () => void
  hasPermission: (permission: string) => boolean
}

// WHY zustand + persist rather than React Context: dashboards poll every
// 15s (matching Dashboard Service's cache TTL) via React Query, and every
// one of those requests needs the current access token — a plain Context
// re-renders every subscriber on every token refresh, while zustand's
// store can be read imperatively (see api/http.ts's request interceptor)
// without subscribing the whole component tree to auth state changes.
export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      setSession: (accessToken, refreshToken, user) => set({ accessToken, refreshToken, user }),
      clearSession: () => set({ accessToken: null, refreshToken: null, user: null }),
      hasPermission: (permission: string) => {
        const { user } = get()
        if (!user) return false
        return user.permissions.includes(permission) || user.permissions.includes('admin:*')
      },
    }),
    { name: 'platform-auth' },
  ),
)
