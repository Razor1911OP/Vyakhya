import { describe, expect, it } from 'vitest'
import { scoreRequest } from '../shared/api-client/mock/engine'
import { decodeToken } from '../shared/auth/jwt'
import { canAccess } from '../shared/auth/permissions'
import { issueMockToken } from '../shared/api-client/mock/server'
import { redact } from '../shared/lib/redaction'
import { tierFor } from '../shared/lib/tiers'
import { buildRequest } from '../panels/simulator/SimulatorPanel'
import { COACHED_TRACE, NO_SIGNALS } from '../panels/simulator/presets'

describe('redaction', () => {
  it('masks OTP, phone, card and account numbers', () => {
    const r = redact('OTP 482913. Call +91 98765 43210. Card 4111 1111 1111 1111. A/c 123456789012')
    expect(r.counts).toEqual({ OTP: 1, PHONE: 1, CARD: 1, ACCOUNT: 1 })
    expect(r.redacted).not.toMatch(/\d{4}/)
  })
  it('handles spacing tricks and Devanagari digits', () => {
    expect(redact('code 4-8-2-9-1-3').counts.OTP).toBe(1)
    expect(redact('ओटीपी ४८२९१३').redacted).toContain('[OTP]')
  })
  it('leaves amounts alone', () => {
    expect(redact('Pay Rs 500000 now').counts.OTP).toBe(0)
  })
})

describe('tier policy', () => {
  it('maps cutoffs', () => {
    expect([39, 40, 69, 70, 84, 85].map((r) => tierFor(r))).toEqual(['LOW', 'MEDIUM', 'MEDIUM', 'HIGH', 'HIGH', 'CRITICAL'])
  })
  it('missing signals widen the band, never lower R', () => {
    const base = { session_id: 's', payee_vpa: 'a@b', amount: 100, signals: NO_SIGNALS, signals_simulated: true as const }
    const known = scoreRequest(base)
    const missing = scoreRequest({ ...base, signals: { ...NO_SIGNALS, call_in_progress: null } })
    expect(missing.r).toBeGreaterThanOrEqual(known.r)
    expect(missing.missing_signals).toEqual(['call_in_progress'])
  })
})

describe('coached-victim trace', () => {
  it('follows the deck trace 18 → 40 → 66 → 82 → 90 and ends in a hold', () => {
    const results = COACHED_TRACE.map((s) => scoreRequest(buildRequest(s.form, 'trace')))
    expect(results.map((r) => r.r)).toEqual([18, 40, 66, 82, 90])
    expect(results.at(-1)!.soft_hold).toBe(true)
    expect(results.every((r) => r.reason_codes.every((c) => c.text.length > 10))).toBe(true)
  })
})

describe('auth', () => {
  it('decodes tokens and enforces RBAC', () => {
    const claims = decodeToken(issueMockToken('analyst', 'analyst', 'A'))
    expect(claims?.role).toBe('analyst')
    expect(decodeToken('garbage')).toBeNull()
    expect(canAccess('user', 'detection')).toBe(false)
    expect(canAccess('user', 'simulator')).toBe(true)
    expect(canAccess('analyst', 'evaluation')).toBe(true)
  })
})
