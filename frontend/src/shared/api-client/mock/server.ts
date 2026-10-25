import { tokenStore } from '../../auth/tokenStore'
import { b64urlEncode, decodeToken } from '../../auth/jwt'
import { maskVpa } from '../../lib/redaction'
import { createRng } from '../../lib/rng'
import { ApiError } from '../errors'
import type {
  Case,
  CaseTimelineEntry,
  ContextSignals,
  Language,
  MetricsBundle,
  Role,
  ScamFamily,
  ScoreRequest,
  ScoreResponse,
  ScoredEvent,
  Stats,
  StatsRange,
  VerdictRequest,
  VyakhyaApi,
} from '../types'
import { scoreRequest } from './engine'
import { SAMPLE_MESSAGES } from './samples'
import { buildStats } from './stats'

export const DEMO_ACCOUNTS: Array<{ username: string; role: Role; name: string }> = [
  { username: 'user', role: 'user', name: 'Demo customer' },
  { username: 'analyst', role: 'analyst', name: 'Analyst A' },
  { username: 'analyst2', role: 'analyst', name: 'Analyst B' },
  { username: 'admin', role: 'admin', name: 'Admin' },
]
export const DEMO_PASSWORD = 'demo'

const HOLD_TTL_MS = 30 * 60 * 1000
const MAX_EVENTS = 500
const MODEL_VERSIONS = {
  text: 'text-primary@mock-0',
  text_fallback: 'tfidf-lr@mock-0',
  txn: 'txn-xgb@mock-0',
  fusion: 'fusion@mock-0',
}

const rng = createRng(20261025)
const delay = (ms: number) => new Promise((r) => setTimeout(r, ms))
const id = (prefix: string) => `${prefix}_${Math.floor(rng.next() * 36 ** 6).toString(36).padStart(6, '0')}`

type Listener = (e: ScoredEvent) => void

interface SessionPoint {
  t: number
  r: number
  label: string
}

class MockBackend {
  events: ScoredEvent[] = []
  cases: Case[] = []
  sessions = new Map<string, { started: number; points: SessionPoint[] }>()
  listeners = new Set<Listener>()
  ticker: ReturnType<typeof setInterval> | null = null

  constructor() {
    const now = Date.now()
    for (let i = 60; i > 0; i--) {
      this.ingest(this.syntheticRequest(), now - i * 45_000 - rng.int(0, 30_000), 'synthetic_stream')
    }
    // Guarantee a few open holds so the review queue is never empty on first load.
    for (const ageMin of [3, 11, 22]) {
      this.ingest(this.syntheticRequest(true), now - ageMin * 60_000, 'synthetic_stream')
    }
  }

  syntheticRequest(forceScam = false): ScoreRequest {
    const scam = forceScam || rng.chance(0.14)
    const family: Exclude<ScamFamily, 'unknown'> = scam
      ? rng.pick(['kyc_refund', 'digital_arrest', 'lottery', 'upi_collect', 'job_task'] as const)
      : 'benign'
    const langs = Object.keys(SAMPLE_MESSAGES[family]) as Language[]
    const msg = rng.chance(scam ? 0.9 : 0.25) ? rng.pick(SAMPLE_MESSAGES[family][rng.pick(langs)]!) : undefined
    const signals: ContextSignals = scam
      ? {
          call_in_progress: forceScam || rng.chance(0.75),
          screen_share: forceScam || rng.chance(0.45),
          new_device: rng.chance(0.2),
          new_location: rng.chance(0.2),
          fresh_payee: rng.chance(0.9),
          odd_hour: rng.chance(0.25),
        }
      : {
          call_in_progress: rng.chance(0.06),
          screen_share: false,
          new_device: rng.chance(0.03),
          new_location: rng.chance(0.05),
          fresh_payee: rng.chance(0.2),
          odd_hour: rng.chance(0.05),
        }
    if (rng.chance(0.04)) signals.new_location = null
    return {
      session_id: id('ses'),
      payee_vpa: `${rng.pick(['ravi', 'shop', 'kirana', 'pay', 'refund', 'helpdesk', 'meena', 'amit'])}${rng.int(10, 999)}@${rng.pick(['okaxis', 'ybl', 'paytm', 'oksbi', 'ibl'])}`,
      amount: scam ? rng.int(5, 95) * 1000 - 1 : rng.int(4, 300) * 10,
      message: msg ? { redacted_text: msg, consent: true } : null,
      signals,
      signals_simulated: true,
    }
  }

  ingest(req: ScoreRequest, ts: number, source: ScoredEvent['source']): ScoreResponse {
    const started = performance.now()
    const result = scoreRequest(req)
    const textModel = req.message ? (rng.chance(0.93) ? 'hf' : 'tfidf_lr') : 'none'
    const latency = Math.round(performance.now() - started + 35 + rng.next() * 110)
    const event: ScoredEvent = {
      event_id: id('evt'),
      ts: new Date(ts).toISOString(),
      r: result.r,
      tier: result.tier,
      reason_codes: result.reason_codes,
      latency_ms: latency,
      payee_vpa_masked: maskVpa(req.payee_vpa),
      amount: req.amount,
      soft_hold: result.soft_hold,
      family_guess: result.family_guess,
      language: result.language,
      text_model_used: textModel,
      source,
    }
    this.events.unshift(event)
    this.events.length = Math.min(this.events.length, MAX_EVENTS)

    const session = this.sessions.get(req.session_id) ?? { started: ts, points: [] }
    session.points.push({
      t: Math.round((ts - session.started) / 1000),
      r: result.r,
      label: result.reason_codes[0]?.code ?? 'SCORED',
    })
    this.sessions.set(req.session_id, session)

    if (result.tier === 'HIGH' || result.tier === 'CRITICAL') {
      this.cases = this.cases.filter((c) => !(c.status === 'pending' && c.case_id === `case_${req.session_id}`))
      this.cases.push(this.makeCase(event, req, session.points))
    }
    this.listeners.forEach((l) => l(event))

    return {
      event_id: event.event_id,
      r: result.r,
      tier: result.tier,
      reason_codes: result.reason_codes,
      soft_hold: result.soft_hold,
      latency_ms: latency,
      model_versions: MODEL_VERSIONS,
      text_model_used: textModel,
      missing_signals: result.missing_signals,
      review_band_widened: result.review_band_widened,
      family_guess: result.family_guess,
      language: result.language,
    }
  }

  makeCase(event: ScoredEvent, req: ScoreRequest, points: SessionPoint[]): Case {
    const timeline: CaseTimelineEntry[] =
      points.length > 1
        ? points.map((p) => ({ t_offset_s: p.t, label: TIMELINE_LABEL[p.label] ?? p.label, r: p.r }))
        : this.syntheticTimeline(req, event.r)
    const muleCount = event.tier === 'CRITICAL' ? rng.int(1, 3) : rng.int(0, 1)
    const nodes: Case['money_graph']['nodes'] = [
      { id: 'payer', label: 'Payer', kind: 'victim' },
      { id: 'payee', label: event.payee_vpa_masked, kind: 'payee' },
    ]
    const edges: Case['money_graph']['edges'] = [{ from: 'payer', to: 'payee', amount: req.amount }]
    for (let i = 0; i < muleCount; i++) {
      nodes.push({ id: `m${i}`, label: `acct ••${rng.int(1000, 9999)}`, kind: 'mule' })
      edges.push({ from: 'payee', to: `m${i}`, amount: Math.round(req.amount / (muleCount + 0.3)) })
    }
    const created = new Date(event.ts).getTime()
    return {
      case_id: `case_${req.session_id}`,
      event_id: event.event_id,
      created_at: event.ts,
      expires_at: event.soft_hold ? new Date(created + HOLD_TTL_MS).toISOString() : null,
      r: event.r,
      tier: event.tier,
      status: 'pending',
      soft_hold: event.soft_hold,
      reason_codes: event.reason_codes,
      payee_vpa_masked: event.payee_vpa_masked,
      amount: req.amount,
      family_guess: event.family_guess,
      timeline,
      money_graph: { nodes, edges, simulated: true },
      reviews: [],
    }
  }

  syntheticTimeline(req: ScoreRequest, finalR: number): CaseTimelineEntry[] {
    const out: CaseTimelineEntry[] = []
    let t = 0
    if (req.signals.call_in_progress) out.push({ t_offset_s: t, label: 'Incoming call started' })
    if (req.message) out.push({ t_offset_s: (t += rng.int(15, 40)), label: 'Message forwarded for check' })
    if (req.signals.screen_share) out.push({ t_offset_s: (t += rng.int(15, 40)), label: 'Screen sharing started' })
    if (req.signals.fresh_payee) out.push({ t_offset_s: (t += rng.int(10, 30)), label: 'New payee added' })
    out.push({ t_offset_s: (t += rng.int(10, 30)), label: 'Payment initiated', r: finalR })
    return out
  }

  expireHolds() {
    const now = Date.now()
    for (const c of this.cases) {
      if (c.expires_at && (c.status === 'pending' || c.status === 'awaiting_second_review') && Date.parse(c.expires_at) <= now) {
        c.status = 'escalated'
        c.reviews.push({ analyst: 'system', action: 'block', note: 'Hold reached its 30-minute limit without a decision; escalated to a senior analyst.', report: false, ts: new Date(now).toISOString() })
      }
    }
  }

  subscribe(listener: Listener) {
    this.listeners.add(listener)
    if (!this.ticker) {
      this.ticker = setInterval(() => this.ingest(this.syntheticRequest(), Date.now(), 'synthetic_stream'), 3500)
    }
    return () => {
      this.listeners.delete(listener)
      if (this.listeners.size === 0 && this.ticker) {
        clearInterval(this.ticker)
        this.ticker = null
      }
    }
  }
}

const TIMELINE_LABEL: Record<string, string> = {
  CALL_ACTIVE: 'Call in progress',
  TEXT_KYC_REFUND: 'KYC / refund message forwarded',
  TEXT_DIGITAL_ARREST: 'Digital-arrest message forwarded',
  TEXT_LOTTERY: 'Lottery message forwarded',
  TEXT_UPI_COLLECT: 'Collect-request message forwarded',
  TEXT_JOB_TASK: 'Job-task message forwarded',
  SCREEN_SHARE: 'Screen sharing started',
  GUIDED_SESSION: 'Screen sharing started during call',
  FRESH_PAYEE: 'New payee added',
  AMOUNT_UNUSUAL: 'Amount raised',
  COACHED_TRANSFER: 'Large transfer to new payee',
  SCORED: 'Payment scored',
}

let backend: MockBackend | null = null
export function getMockBackend(): MockBackend {
  backend ??= new MockBackend()
  return backend
}

function currentUser(): { sub: string; role: Role } {
  const token = tokenStore.get()
  const claims = token ? decodeToken(token) : null
  if (!claims) {
    tokenStore.set(null)
    throw new ApiError(401, 'Your session has ended. Please sign in again.')
  }
  return claims
}

function requireRole(...roles: Role[]) {
  const user = currentUser()
  if (!roles.includes(user.role)) throw new ApiError(403, 'Your role does not have access to this action.')
  return user
}

export function issueMockToken(username: string, role: Role, name: string): string {
  const now = Math.floor(Date.now() / 1000)
  const header = b64urlEncode(JSON.stringify({ alg: 'none', typ: 'JWT' }))
  const payload = b64urlEncode(JSON.stringify({ sub: username, role, name, iat: now, exp: now + 8 * 3600 }))
  return `${header}.${payload}.mock`
}

const METRIC_FILES = ['pr_curve', 'lofo', 'critical_precision', 'latency', 'registry', 'comparison']

export function createMockApi(): VyakhyaApi {
  return {
    mode: 'mock',
    async login(username, password) {
      await delay(250)
      const account = DEMO_ACCOUNTS.find((a) => a.username === username.trim().toLowerCase())
      if (!account || password !== DEMO_PASSWORD) throw new ApiError(401, 'Incorrect username or password.')
      return { access_token: issueMockToken(account.username, account.role, account.name), token_type: 'bearer' }
    },
    async score(req) {
      currentUser()
      if (req.amount <= 0 || !Number.isFinite(req.amount)) throw new ApiError(422, 'Amount must be a positive number.')
      if ((req.message?.redacted_text.length ?? 0) > 2000) throw new ApiError(413, 'Message is too long.')
      await delay(60 + rng.int(0, 80))
      return getMockBackend().ingest(req, Date.now(), 'simulator')
    },
    async events(query = {}) {
      requireRole('analyst', 'admin')
      await delay(120)
      const list = getMockBackend().events.filter((e) => !query.tier || e.tier === query.tier)
      return list.slice(0, query.limit ?? 100)
    },
    async cases() {
      requireRole('analyst', 'admin')
      await delay(120)
      const b = getMockBackend()
      b.expireHolds()
      return structuredClone(b.cases).sort((a, c) => c.r - a.r)
    },
    async verdict(req: VerdictRequest) {
      const user = requireRole('analyst', 'admin')
      await delay(200)
      const b = getMockBackend()
      b.expireHolds()
      const c = b.cases.find((x) => x.case_id === req.case_id)
      if (!c) throw new ApiError(404, 'Case not found.')
      if (c.status !== 'pending' && c.status !== 'awaiting_second_review') throw new ApiError(409, 'This case is already closed.')
      if (req.note.trim().length < 8) throw new ApiError(422, 'Add a short note (at least 8 characters) explaining the decision.')
      const review = { analyst: user.sub, action: req.action, note: req.note.trim(), report: !!req.report, ts: new Date().toISOString() }
      if (req.action === 'block') {
        c.status = 'blocked'
      } else if (c.tier === 'CRITICAL') {
        if (c.status === 'pending') c.status = 'awaiting_second_review'
        else if (c.reviews.some((r) => r.analyst === user.sub)) {
          throw new ApiError(409, 'A different analyst must confirm the release of a CRITICAL hold.')
        } else c.status = 'released'
      } else {
        c.status = 'released'
      }
      c.reviews.push(review)
      return structuredClone(c)
    },
    async stats(range: StatsRange): Promise<Stats> {
      requireRole('analyst', 'admin')
      await delay(180)
      return buildStats(range)
    },
    async metrics(): Promise<MetricsBundle> {
      requireRole('analyst', 'admin')
      const entries = await Promise.all(
        METRIC_FILES.map(async (name) => {
          try {
            const res = await fetch(`${import.meta.env.BASE_URL}mock-metrics/${name}.json`)
            return res.ok ? ([name, await res.json()] as const) : null
          } catch {
            return null
          }
        }),
      )
      return Object.fromEntries(entries.filter((e) => e !== null))
    },
  }
}
