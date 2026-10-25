/**
 * Adapter between this UI's types and the Vyakhya Node API (Vyakhya-p2-backend/api/server.js).
 *
 * The API speaks its own shapes (R, reasons + why, hold, hold_expires_at, ...). This file maps them to the
 * types the panels already use, so the panels stay unchanged. Every mapping that has to invent or
 * approximate a value is commented, so nothing here silently pretends to be measured.
 */
import { maskVpa } from '../lib/redaction'
import type {
  Case,
  CaseStatus,
  ComparisonMetrics,
  ContextSignals,
  CriticalPrecisionMetrics,
  LatencyMetrics,
  LofoMetrics,
  MetricsBundle,
  MetricsMeta,
  ReasonCode,
  RegistryMetrics,
  ScamFamily,
  ScoreRequest,
  ScoreResponse,
  ScoredEvent,
  SignalKey,
  Stats,
  StatsRange,
  Tier,
} from './types'
import { TIERS } from './types'

// ------------------------------------------------------------------ API shapes (subset we read)
export interface ApiScoreResponse {
  R: number | null
  tier: Tier
  reasons: string[]
  why: string[]
  hold: boolean
  event_id?: string
  latency_ms?: number
  cutoffs?: { medium: number; high: number } | null
  components?: {
    text_prob: number | null
    txn_prob: number | null
    rule_prob: number | null
    hard_rule_floor: number | null
    signal_mode: string | null
  } | null
  case_id: string | null
  hold_expires_at: string | null
  disclaimer: string | null
  ask_user: string | null
  context_flags: string[]
  model_version: string | null
  rules_version: string | null
}

export interface ApiEvent {
  id: string
  created_at: string
  R: number | null
  tier: Tier
  reasons: string[]
  why?: string[]
  hold: boolean
  scoring_ok: boolean
  amount: number
  payee_masked?: string | null
  latency_ms?: number | null
  model_version?: string | null
}

export interface ApiCase {
  _id: string
  event_id: string
  created_at: string
  R: number | null
  tier: Tier
  reasons: string[]
  why: string[]
  hold: boolean
  payment?: { payee_vpa?: string; amount?: number }
  status: 'held' | 'escalated' | 'released' | 'blocked'
  held_at?: string
  hold_expires_at?: string
  escalated_at?: string
  escalated_via?: string
  closed_at?: string
  closed_via?: string
  seconds_held?: number
  decided_by?: string
  decision_note?: string
}

export interface ApiStats {
  total: number
  tiers: Partial<Record<Tier, number>>
  by_day?: Array<{ date: string } & Record<Tier, number>>
  holds?: number
  users?: number
  users_over_budget?: number
  alerts_per_user_week?: number
  p95_latency_ms?: number | null
  zero_friction_pct: number | null
}

// ------------------------------------------------------------------------- shared helpers
/** reasons[i] is the code, why[i] the plain-language sentence the API wrote for it. */
export function toReasons(codes: string[] = [], why: string[] = []): ReasonCode[] {
  return codes.map((code, i) => ({ code, text: why[i] ?? code.replace(/_/g, ' ').toLowerCase() }))
}

/** Context signals are SIMULATED and are not part of R in the frozen engine; label them as such. */
const CONTEXT_TEXT: Record<string, string> = {
  SCREEN_SHARE: 'Screen sharing is on (simulated signal, shown for context, not part of the score).',
  CALL_ACTIVE: 'A call is in progress (simulated signal, shown for context, not part of the score).',
  NEW_DEVICE: 'New device (simulated signal, shown for context, not part of the score).',
  NEW_GEO: 'New location (simulated signal, shown for context, not part of the score).',
}

// --------------------------------------------------------------------------------- /score
/**
 * Values the simulator cannot know, filled with documented demo assumptions:
 *  - user_avg_amount: a typical customer pays about Rs 1,500 per transaction.
 *  - payee history: "Saved payee" = 50 earlier payments; "first payment" = 0; otherwise unknown
 *    (the engine treats unknown as a new payee, never as safe).
 *  - hour: 23:00 when "unusual hour" is on, else 14:00 (fixed so demo results are repeatable).
 */
export const DEMO_USER_AVG_AMOUNT = 1500

export function toApiScoreBody(req: ScoreRequest) {
  const s: ContextSignals = req.signals
  const text = [req.message?.redacted_text, req.note].filter((x): x is string => !!x && !!x.trim()).join('\n')
  const prior = req.trusted_payee ? 50 : s.fresh_payee ? 0 : undefined
  return {
    session_id: req.session_id,
    redacted_text: text,
    context: {
      new_device: s.new_device === true,
      new_geo: s.new_location === true,
      screen_share: s.screen_share === true,
      call_active: s.call_in_progress === true,
    },
    payment: {
      payee_vpa: req.payee_vpa,
      amount: req.amount,
      payee_age_days: req.trusted_payee ? 365 : s.fresh_payee ? 0 : 30,
      user_avg_amount: DEMO_USER_AVG_AMOUNT,
      ...(prior !== undefined ? { payee_prior_txns: prior } : {}),
      hour: s.odd_hour ? 23 : 14,
    },
  }
}

export function fromApiScore(res: ApiScoreResponse, req: ScoreRequest): ScoreResponse {
  const reasons = toReasons(res.reasons, res.why)
  if (res.disclaimer) reasons.push({ code: 'PIN_DISCLAIMER', text: res.disclaimer })
  if (res.ask_user) reasons.push({ code: 'ASK_USER', text: res.ask_user })
  for (const c of res.context_flags ?? []) reasons.push({ code: c, text: CONTEXT_TEXT[c] ?? c })
  const missing = (Object.keys(req.signals) as SignalKey[]).filter((k) => req.signals[k] === null)
  return {
    event_id: res.event_id ?? res.case_id ?? crypto.randomUUID(),
    r: res.R ?? 0, // null only when the scoring service is down; the reason SCORING_UNAVAILABLE says so
    tier: res.tier,
    reason_codes: reasons,
    soft_hold: res.tier === 'CRITICAL' && res.hold,
    latency_ms: res.latency_ms ?? 0,
    model_versions: {
      ...(res.model_version ? { engine: res.model_version } : {}),
      ...(res.rules_version ? { rules: `rules ${res.rules_version}` } : {}),
    },
    text_model_used: res.components?.text_prob != null ? 'tfidf_lr' : 'none',
    missing_signals: missing,
    review_band_widened: false, // the frozen engine does not widen bands for missing signals
    cutoffs: res.cutoffs ?? undefined,
    components: res.components ?? undefined,
    hold_expires_at: res.hold_expires_at,
  }
}

// --------------------------------------------------------------------------------- events
export function fromApiEvent(e: ApiEvent): ScoredEvent {
  return {
    event_id: e.id,
    ts: e.created_at,
    r: e.R ?? 0,
    tier: e.tier,
    reason_codes: toReasons(e.reasons, e.why),
    latency_ms: e.latency_ms ?? 0,
    payee_vpa_masked: e.payee_masked ?? '••••',
    amount: e.amount,
    soft_hold: e.tier === 'CRITICAL' && e.hold,
    text_model_used: 'tfidf_lr',
    source: 'live',
  }
}

// ---------------------------------------------------------------------------------- cases
const STATUS: Record<ApiCase['status'], CaseStatus> = {
  held: 'pending',
  escalated: 'pending', // CRITICAL after call-back/expiry: still held, waiting for an analyst
  released: 'released',
  blocked: 'blocked',
}

export function fromApiCase(c: ApiCase): Case {
  const amount = c.payment?.amount ?? 0
  const payee = c.payment?.payee_vpa ? maskVpa(c.payment.payee_vpa) : '••••'
  const t0 = Date.parse(c.held_at ?? c.created_at)
  const off = (iso?: string) => (iso ? Math.max(0, Math.round((Date.parse(iso) - t0) / 1000)) : 0)
  const timeline: Case['timeline'] = [{ t_offset_s: 0, label: 'Payment scored and held before debit', r: c.R ?? undefined }]
  if (c.escalated_at) timeline.push({ t_offset_s: off(c.escalated_at), label: `Escalated to analyst (${c.escalated_via ?? 'expiry'})` })
  if (c.closed_at) timeline.push({ t_offset_s: off(c.closed_at), label: `${c.status === 'released' ? 'Released' : 'Blocked'} via ${c.closed_via ?? 'analyst'}` })
  return {
    case_id: c._id,
    event_id: c.event_id,
    created_at: c.created_at,
    expires_at: c.status === 'held' ? c.hold_expires_at ?? null : null,
    r: c.R ?? 0,
    tier: c.tier,
    status: STATUS[c.status],
    soft_hold: c.tier === 'CRITICAL' && c.hold,
    reason_codes: toReasons(c.reasons, c.why),
    payee_vpa_masked: payee,
    amount,
    family_guess: 'unknown' as ScamFamily,
    timeline,
    // Derived from the payment only (payer -> payee). Downstream mule hops are ROADMAP.
    money_graph: {
      nodes: [
        { id: 'payer', label: 'Payer', kind: 'victim' },
        { id: 'payee', label: payee, kind: 'payee' },
      ],
      edges: [{ from: 'payer', to: 'payee', amount }],
      simulated: true,
    },
    reviews: c.decided_by
      ? [{ analyst: c.decided_by, action: c.status === 'released' ? 'release' : 'block', note: c.decision_note ?? '', report: c.status === 'blocked', ts: c.closed_at ?? c.created_at }]
      : [],
  }
}

// ---------------------------------------------------------------------------------- stats
export function fromApiStats(s: ApiStats, range: StatsRange): Stats {
  const total = s.total ?? 0
  return {
    range,
    generated_at: new Date().toISOString(),
    synthetic: true,
    totals: {
      payments: total,
      zero_friction_pct: s.zero_friction_pct ?? 0,
      alerts_per_user_week: s.alerts_per_user_week ?? 0,
      holds: s.holds ?? 0,
      users: s.users ?? 0,
      users_over_budget: s.users_over_budget ?? 0,
    },
    targets: { zero_friction_pct: 95, alerts_per_user_week: 1 },
    trend: (s.by_day ?? []).map((d) => ({ date: d.date, LOW: d.LOW ?? 0, MEDIUM: d.MEDIUM ?? 0, HIGH: d.HIGH ?? 0, CRITICAL: d.CRITICAL ?? 0 })),
    tier_distribution: TIERS.map((tier) => ({ tier, count: s.tiers?.[tier] ?? 0 })),
    // Not known at scoring time (family and language are evaluated offline, see Model Evaluation).
    family_breakdown: [],
    language_breakdown: [],
    fairness: [],
    model_usage: total ? [{ model: 'tfidf_lr', calls: total, p95_ms: s.p95_latency_ms ?? 0 }] : [],
    cluster_candidates: [], // HDBSCAN clustering is ROADMAP
  }
}

// -------------------------------------------------------------------------------- metrics
type Json = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any
const SYNTH_FOLDS = ['kyc_refund', 'digital_arrest', 'lottery', 'upi_collect', 'job_task'] as const
const SHIPPED = 'with_rule_score'

/** Builds the panel's metric cards from metrics/risk_eval.json plus live latencies from /events. */
export function fromApiMetrics(files: Json, events: ApiEvent[]): MetricsBundle {
  const ev = files.risk_eval as Json | undefined
  const out: MetricsBundle = {}
  if (ev) {
    const meta = (note?: string): MetricsMeta => ({
      synthetic: true,
      source: 'metrics/risk_eval.json',
      generated_at: ev.fusion_shipped?.trained_at ?? '',
      dataset: 'Vyakhya synthetic + UCI SMS Spam + PaySim (public synthetic mobile-money data, not UPI)',
      note,
    })
    const textOnly = ev.ablation?.['text only']
    const shipped = ev.ablation?.['all + rule_score (shipped)']
    const weak = ev.weak_spots
    const lofoRows: Json[] = (ev.lofo?.[SHIPPED] ?? []).filter((r: Json) => (SYNTH_FOLDS as readonly string[]).includes(r.fold))
    const lofo: LofoMetrics = {
      _meta: meta(
        weak
          ? `Weakest family: ${weak.weakest_family_lofo} (${Number(weak.weakest_family_detail?.shipped_recall_at_1pct_fpr ?? 0).toFixed(2)}). ` +
              'Unseen-family numbers measure transfer between our own synthetic templates, not real-world scams.'
          : undefined,
      ),
      target: 0.8,
      max_fpr: 0.01,
      families: lofoRows.map((r) => ({
        family: r.fold as ScamFamily,
        baseline_text_only: Number(textOnly?.per_fold_recall_at_1pct_fpr?.[r.fold] ?? 0),
        fused: Number(r.recall_at_1pct_fpr ?? 0),
      })),
    }
    out.lofo = lofo

    const hw = ev.handwritten
    const rows: ComparisonMetrics['rows'] = []
    if (textOnly && shipped) {
      rows.push({ metric: 'Mean unseen-family recall @1% FPR (synthetic)', baseline: round(textOnly.mean_unseen_family_recall_at_1pct_fpr), fused: round(shipped.mean_unseen_family_recall_at_1pct_fpr), higher_is_better: true })
      rows.push({ metric: 'Pooled AUC (synthetic)', baseline: round(textOnly.synthetic_pooled_auc), fused: round(shipped.synthetic_pooled_auc), higher_is_better: true })
    }
    if (hw?.auc) rows.push({ metric: `AUC, hand-written set (n=${hw.n})`, baseline: round(hw.auc['text only']), fused: round(hw.auc[SHIPPED]), higher_is_better: true })
    out.comparison = { _meta: meta('Hand-written set was written by the same author as the rules; not an independent test.'), rows }

    // CRITICAL = any hard-rule hit. Precision on synthetic data: hard-rule hits on benign vs on scams.
    const scamN = lofoRows.reduce((a, r) => a + Number(r.n_scam ?? 0), 0)
    const scamHits = Math.round(Number(ev.rule_flag_rates?.scam_synthetic?.hard_floor_90 ?? 0) * scamN)
    const benignHits = Object.values(ev.hard_negatives ?? {}).reduce((a: number, g) => a + Number((g as Json).hard_floor_hits ?? 0), 0)
    if (scamHits + benignHits > 0) {
      const cp: CriticalPrecisionMetrics = {
        _meta: meta('CRITICAL = hard-rule hit (PIN/collect to receive money, or amount mismatch). Measured on synthetic data only.'),
        precision: round(scamHits / (scamHits + benignHits)),
        target: 0.9,
        support: scamHits + benignHits,
      }
      out.critical_precision = cp
    }

    const fs = ev.fusion_shipped ?? {}
    const registry: RegistryMetrics = {
      _meta: { ...meta('Loaded from model_registry/risk/' + (fs.model_version ?? '') + '/. Frozen.'), synthetic: true },
      models: [
        { name: 'tfidf_lr_text', version: fs.model_version ?? '?', role: 'Text model (TF-IDF char 2-5 + LR, isotonic)', created: fs.trained_at ?? '', in_use: true },
        { name: 'paysim_xgb_behaviour', version: fs.model_version ?? '?', role: 'Transaction model', created: fs.trained_at ?? '', in_use: true, notes: 'Trained on PaySim: public synthetic mobile-money data, not UPI' },
        { name: 'sender_history_lr', version: fs.model_version ?? '?', role: 'Sender-history model (synthetic)', created: fs.trained_at ?? '', in_use: true },
        { name: `rules ${ev.rules_version ?? ''}`, version: (ev.frozen_hashes?.['risk/rules.py'] ?? '').slice(0, 12), role: 'Rule layer + hard-rule floor 90', created: fs.trained_at ?? '', in_use: true },
        { name: 'fusion with_rule_score', version: fs.model_version ?? '?', role: 'max(floor, blend(text, txn, rules))', created: fs.trained_at ?? '', in_use: fs.shipped_system === SHIPPED, notes: 'Cutoffs tuned on synthetic data, re-calibrate at pilot' },
        { name: 'fusion spec_baseline', version: fs.model_version ?? '?', role: 'max(floor, blend(text, txn))', created: fs.trained_at ?? '', in_use: fs.shipped_system === 'spec_baseline', notes: 'Reported baseline' },
        { name: 'multilingual MiniLM', version: '-', role: 'Optional text-model comparison', created: '', in_use: false, notes: 'Not evaluated' },
      ],
    }
    out.registry = registry
  }

  const lat = events.map((e) => e.latency_ms).filter((x): x is number => typeof x === 'number').sort((a, b) => a - b)
  if (lat.length) {
    const q = (p: number) => lat[Math.min(lat.length - 1, Math.floor(lat.length * p))]
    const bins = new Map<number, number>()
    for (const v of lat) bins.set(Math.floor(v / 25) * 25, (bins.get(Math.floor(v / 25) * 25) ?? 0) + 1)
    const latency: LatencyMetrics = {
      _meta: { synthetic: true, source: `GET /events (last ${lat.length} scored payments)`, generated_at: new Date().toISOString(), note: 'Live demo traffic; server-side time before storage.' },
      budget_ms: 300,
      p50_ms: q(0.5),
      p95_ms: q(0.95),
      p99_ms: q(0.99),
      histogram: [...bins.entries()].sort((a, b) => a[0] - b[0]).map(([start, count]) => ({ start_ms: start, end_ms: start + 25, count })),
    }
    out.latency = latency
  }
  return out
}

function round(x: unknown): number {
  return Math.round(Number(x ?? 0) * 1000) / 1000
}
