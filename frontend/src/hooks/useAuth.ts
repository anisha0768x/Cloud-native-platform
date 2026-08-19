import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { fetchCurrentUser, login as loginApi, logout as logoutApi } from '../api/auth'
import { useAuthStore } from '../store/authStore'

export function useAuth() {
  const navigate = useNavigate()
  const { accessToken, refreshToken, user, setSession, clearSession } = useAuthStore()

  const loginMutation = useMutation({
    mutationFn: async ({ email, password }: { email: string; password: string }) => {
      const tokens = await loginApi(email, password)
      // Stash the token BEFORE fetching /me, since the http client's
      // request interceptor reads it from the store, not from this
      // function's local scope.
      setSession(tokens.access_token, tokens.refresh_token, null as never)
      const currentUser = await fetchCurrentUser()
      setSession(tokens.access_token, tokens.refresh_token, currentUser)
      return currentUser
    },
    onSuccess: () => navigate('/'),
  })

  const logoutMutation = useMutation({
    mutationFn: async () => {
      if (refreshToken) {
        await logoutApi(refreshToken).catch(() => undefined) // best-effort — clear local session regardless
      }
    },
    onSettled: () => {
      clearSession()
      navigate('/login')
    },
  })

  return {
    isAuthenticated: Boolean(accessToken && user),
    user,
    login: loginMutation.mutate,
    isLoggingIn: loginMutation.isPending,
    loginError: loginMutation.error,
    logout: logoutMutation.mutate,
  }
}
