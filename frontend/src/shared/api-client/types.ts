export type Tier = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export const TIERS: Tier[] = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']

export type Role = 'user' | 'analyst' | 'admin'

export type ScamFamily =
  | 'kyc_refund'
  | 'digital_arrest'
  | 'lottery'
  | 'upi_collect'
  | 'job_task'
  | 'benign'
  | 'unknown'

export type Language = 'en' | 'hi' | 'hinglish'

export type TextModelUsed = 'hf' | 'tfidf_lr' | 'none'

/** `null` means the signal could not be read. Missing signals widen the review band. */
export type SignalValue = boolean | null

export interface ContextSignals {
  call_in_progress: SignalValue
  screen_share: SignalValue
  new_device: SignalValue
  new_location: SignalValue
  fresh_payee: SignalValue
  odd_hour: SignalValue
}

export type SignalKey = keyof ContextSignals

export interface ScoreRequest {
  session_id: string
  payee_vpa: string
  amount: number
  note?: string
  /** Already redacted on the client. Omitted when the user has not consented. */
  message?: { redacted_text: string; consent: true } | null
  signals: ContextSignals
  signals_simulated: true
  trusted_payee?: boolean
}

export interface ReasonCode {
  code: string
  /** Plain-language explanation shown to users and analysts. */
  text: string
}

export interface ScoreResponse {
  event_id: string
  r: number
  tier: Tier
  reason_codes: ReasonCode[]
  soft_hold: boolean
  latency_ms: number
  model_versions: Record<string, string>
  text_model_used: TextModelUsed
  missing_signals: SignalKey[]
  review_band_widened: boolean
  family_guess?: ScamFamily
  language?: Language
  /** Live API only: band cutoffs the engine used for this decision (they differ by signal mode). */
  cutoffs?: { medium: number; high: number }
  /** Live API only: per-signal probabilities from the frozen engine. */
  components?: {
    text_prob: number | null
    txn_prob: number | null
    rule_prob: number | null
    hard_rule_floor: number | null
    signal_mode: string | null
  }
  hold_expires_at?: string | null
}

export interface ScoredEvent {
  event_id: string
  ts: string
  r: number
  tier: Tier
  reason_codes: ReasonCode[]
  latency_ms: number
  payee_vpa_masked: string
  amount: number
  soft_hold: boolean
  family_guess?: ScamFamily
  language?: Language
  text_model_used: TextModelUsed
  source: 'simulator' | 'synthetic_stream' | 'live'
}

export type CaseStatus =
  | 'pending'
  | 'awaiting_second_review'
  | 'released'
  | 'blocked'
  | 'escalated'

export interface CaseReview {
  analyst: string
  action: 'release' | 'block'
  note: string
  report: boolean
  ts: string
}

export interface MoneyGraphNode {
  id: string
  label: string
  kind: 'victim' | 'payee' | 'mule' | 'merchant'
}

export interface MoneyGraphEdge {
  from: string
  to: string
  amount: number
}

export interface CaseTimelineEntry {
  t_offset_s: number
  label: string
  r?: number
}

export interface Case {
  case_id: string
  event_id: string
  created_at: string
  /** Only set for soft holds (CRITICAL). */
  expires_at: string | null
  r: number
  tier: Tier
  status: CaseStatus
  soft_hold: boolean
  reason_codes: ReasonCode[]
  payee_vpa_masked: string
  amount: number
  family_guess?: ScamFamily
  timeline: CaseTimelineEntry[]
  money_graph: { nodes: MoneyGraphNode[]; edges: MoneyGraphEdge[]; simulated: boolean }
  reviews: CaseReview[]
}

export interface VerdictRequest {
  case_id: string
  action: 'release' | 'block'
  note: string
  report?: boolean
}

export interface LoginResponse {
  access_token: string
  token_type: 'bearer'
}

export interface ClusterCandidate {
  cluster_id: string
  size: number
  first_seen: string
  last_seen: string
  languages: Language[]
  sample_redacted: string
  top_terms: string[]
  nearest_known_family: ScamFamily
  distance: number
}

export type StatsRange = '7d' | '30d'

export interface Stats {
  range: StatsRange
  generated_at: string
  synthetic: boolean
  totals: {
    payments: number
    zero_friction_pct: number
    alerts_per_user_week: number
    holds: number
    users: number
    users_over_budget: number
  }
  targets: { zero_friction_pct: number; alerts_per_user_week: number }
  trend: Array<{ date: string } & Record<Tier, number>>
  tier_distribution: Array<{ tier: Tier; count: number }>
  family_breakdown: Array<{ family: ScamFamily; flagged: number; held: number }>
  language_breakdown: Array<{ language: Language; payments: number; alerts: number }>
  fairness: Array<{
    dimension: 'language' | 'age_band'
    cohort: string
    payments: number
    alert_rate_pct: number
    precision: number
    recall: number
  }>
  model_usage: Array<{ model: Exclude<TextModelUsed, 'none'>; calls: number; p95_ms: number }>
  cluster_candidates: ClusterCandidate[]
}

export interface MetricsMeta {
  synthetic: boolean
  placeholder?: boolean
  source: string
  generated_at: string
  dataset?: string
  note?: string
}

export interface PrCurveMetrics {
  _meta: MetricsMeta
  prevalence: string
  reweighted: boolean
  points: Array<{ recall: number; precision: number }>
  cutoffs: Array<{ tier: Exclude<Tier, 'LOW'>; r: number; recall: number; precision: number }>
}

export interface LofoMetrics {
  _meta: MetricsMeta
  target: number
  max_fpr: number
  families: Array<{ family: ScamFamily; baseline_text_only: number; fused: number }>
}

export interface CriticalPrecisionMetrics {
  _meta: MetricsMeta
  precision: number
  target: number
  support: number
}

export interface LatencyMetrics {
  _meta: MetricsMeta
  budget_ms: number
  p50_ms: number
  p95_ms: number
  p99_ms: number
  histogram: Array<{ start_ms: number; end_ms: number; count: number }>
}

export interface RegistryMetrics {
  _meta: MetricsMeta
  models: Array<{
    name: string
    version: string
    role: string
    created: string
    in_use: boolean
    notes?: string
  }>
}

export interface ComparisonMetrics {
  _meta: MetricsMeta
  rows: Array<{ metric: string; baseline: number; fused: number; higher_is_better: boolean }>
}

/** `GET /metrics` returns each `metrics/*.json` file keyed by its file stem. */
export interface MetricsBundle {
  pr_curve?: PrCurveMetrics
  lofo?: LofoMetrics
  critical_precision?: CriticalPrecisionMetrics
  latency?: LatencyMetrics
  registry?: RegistryMetrics
  comparison?: ComparisonMetrics
  [file: string]: unknown
}

export interface EventsQuery {
  limit?: number
  tier?: Tier
}

export interface VyakhyaApi {
  readonly mode: 'mock' | 'live'
  login(username: string, password: string): Promise<LoginResponse>
  score(req: ScoreRequest): Promise<ScoreResponse>
  events(query?: EventsQuery): Promise<ScoredEvent[]>
  cases(): Promise<Case[]>
  verdict(req: VerdictRequest): Promise<Case>
  stats(range: StatsRange): Promise<Stats>
  metrics(): Promise<MetricsBundle>
}
