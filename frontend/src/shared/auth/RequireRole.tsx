import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { useAuth } from './AuthProvider'
import { canAccess, type PanelKey } from './permissions'
import { NoAccess } from '../ui-kit/States'

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const location = useLocation()
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <>{children}</>
}

export function RequirePanel({ panel, children }: { panel: PanelKey; children: ReactNode }) {
  const { user } = useAuth()
  if (!canAccess(user?.role, panel)) return <NoAccess />
  return <>{children}</>
}
