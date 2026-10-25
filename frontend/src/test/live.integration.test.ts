/**
 * Live contract test: runs the REAL http client + adapter against a running Node API.
 * Skipped unless LIVE_API is set, e.g.  LIVE_API=http://localhost:3000 npx vitest run src/test/live.integration.test.ts
 * Creates a few demo events/cases in the API's database.
 */
import { beforeAll, describe, expect, it } from 'vitest'
import { createHttpApi } from '../shared/api-client/http'
import { tokenStore } from '../shared/auth/tokenStore'
import { decodeToken } from '../shared/auth/jwt'
import { buildRequest } from '../panels/simulator/SimulatorPanel'
import { LIVE_COACHED_TRACE as COACHED_TRACE, PRESETS } from '../panels/simulator/presets'

const BASE = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env.LIVE_API
const d = BASE ? describe : describe.skip

d('live API contract', () => {
  const api = createHttpApi(BASE ?? '')
  const log: string[] = []
  beforeAll(async () => {
    const { access_token } = await api.login('analyst', 'analyst123')
    expect(decodeToken(access_token)?.role).toBe('analyst')
    tokenStore.set(access_token)
  })

  it('scores presets and the coached trace with the fields the panels read', async () => {
    for (const p of PRESETS) {
      const r = await api.score(buildRequest(p.form, `fe-${p.id}-${Date.now()}`))
      log.push(`${p.id}: R=${r.r} ${r.tier} hold=${r.soft_hold} ${r.latency_ms}ms cutoffs=${JSON.stringify(r.cutoffs)} reasons=${r.reason_codes.map((c) => c.code).join(',')}`)
      expect(typeof r.r).toBe('number')
      expect(r.reason_codes.every((c) => c.text.length > 3)).toBe(true)
      expect(r.cutoffs?.medium).toBeTypeOf('number')
    }
    const sid = `fe-trace-${Date.now()}`
    let last
    for (const s of COACHED_TRACE) {
      last = await api.score(buildRequest(s.form, sid))
      const r = last
      log.push(`trace T+${s.t}s: R=${r.r} ${r.tier} hold=${r.soft_hold} components=${JSON.stringify(r.components)} reasons=${r.reason_codes.map((c) => c.code).join(',')}`)
    }
    expect(last?.tier).toBe('CRITICAL')
    expect(last?.soft_hold).toBe(true)
  })

  it('reads events, cases, stats and metrics in panel shapes, and decides a case with a note', async () => {
    const events = await api.events({ limit: 5 })
    log.push(`events[0]: ${JSON.stringify(events[0])}`)
    expect(events[0].event_id).toBeTruthy()
    expect(events[0].payee_vpa_masked).toContain('@')

    const cases = await api.cases()
    const open = cases.find((c) => c.status === 'pending')
    log.push(`cases: ${cases.length}, first open: ${open?.case_id} ${open?.tier} R=${open?.r} expires=${open?.expires_at}`)
    if (open) {
      const done = await api.verdict({ case_id: open.case_id, action: 'block', note: 'Contract test: caller impersonating bank', report: true })
      log.push(`verdict -> ${done.status} by ${done.reviews[0]?.analyst} note="${done.reviews[0]?.note}"`)
      expect(done.status).toBe('blocked')
      expect(done.reviews[0]?.note).toContain('Contract test')
    }

    const stats = await api.stats('7d')
    log.push(`stats: ${JSON.stringify({ totals: stats.totals, tiers: stats.tier_distribution, days: stats.trend.length })}`)
    expect(stats.totals.payments).toBeGreaterThan(0)

    const m = await api.metrics()
    log.push(`metrics keys: ${Object.keys(m).join(',')}`)
    log.push(`lofo: ${JSON.stringify(m.lofo?.families)}`)
    log.push(`critical_precision: ${JSON.stringify({ p: m.critical_precision?.precision, n: m.critical_precision?.support })}  latency p95: ${m.latency?.p95_ms}`)
    expect(m.lofo?.families.length).toBe(5)
    expect(m.registry?.models.length).toBeGreaterThan(3)
    console.log('\n' + log.join('\n'))
  })
})
