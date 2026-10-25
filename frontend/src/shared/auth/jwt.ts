import type { Role } from '../api-client/types'

export interface TokenClaims {
  sub: string
  role: Role
  exp: number
  iat?: number
  name?: string
}

const ROLES: Role[] = ['user', 'analyst', 'admin']

function b64urlDecode(segment: string): string {
  const b64 = segment.replace(/-/g, '+').replace(/_/g, '/')
  const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4)
  const bytes = Uint8Array.from(atob(padded), (c) => c.charCodeAt(0))
  return new TextDecoder().decode(bytes)
}

export function b64urlEncode(value: string): string {
  const bytes = new TextEncoder().encode(value)
  let bin = ''
  bytes.forEach((b) => (bin += String.fromCharCode(b)))
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** Reads claims for UI decisions only. The server verifies the signature on every request. */
export function decodeToken(token: string, nowSec = Date.now() / 1000): TokenClaims | null {
  const parts = token.split('.')
  if (parts.length !== 3) return null
  try {
    const claims = JSON.parse(b64urlDecode(parts[1])) as Partial<TokenClaims>
    if (typeof claims.sub !== 'string' || typeof claims.exp !== 'number') return null
    if (!claims.role || !ROLES.includes(claims.role)) return null
    if (claims.exp <= nowSec) return null
    return claims as TokenClaims
  } catch {
    return null
  }
}
