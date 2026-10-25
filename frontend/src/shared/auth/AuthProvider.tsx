import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '../api-client'
import type { Role } from '../api-client/types'
import { decodeToken, type TokenClaims } from './jwt'
import { tokenStore } from './tokenStore'

interface AuthState {
  user: TokenClaims | null
  login(username: string, password: string): Promise<TokenClaims>
  logout(): void
  hasRole(...roles: Role[]): boolean
}

const AuthContext = createContext<AuthState | null>(null)

function readUser(): TokenClaims | null {
  const token = tokenStore.get()
  return token ? decodeToken(token) : null
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<TokenClaims | null>(readUser)

  useEffect(() => tokenStore.subscribe(() => setUser(readUser())), [])

  useEffect(() => {
    if (!user) return
    const ms = user.exp * 1000 - Date.now()
    const timer = setTimeout(() => tokenStore.set(null), Math.max(0, ms))
    return () => clearTimeout(timer)
  }, [user])

  const login = useCallback(async (username: string, password: string) => {
    const { access_token } = await api.login(username, password)
    const claims = decodeToken(access_token)
    if (!claims) throw new Error('The server returned an invalid session token.')
    tokenStore.set(access_token)
    return claims
  }, [])

  const logout = useCallback(() => tokenStore.set(null), [])

  const value = useMemo<AuthState>(
    () => ({ user, login, logout, hasRole: (...roles) => !!user && roles.includes(user.role) }),
    [user, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
