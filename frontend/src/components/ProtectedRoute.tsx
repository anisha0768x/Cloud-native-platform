import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const accessToken = useAuthStore((s) => s.accessToken)
  const user = useAuthStore((s) => s.user)
  const isAuthenticated = Boolean(accessToken && user)
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}
