import type { ScoreResponse } from '../../shared/api-client/types'
import { SIGNAL_LABEL } from '../../shared/lib/format'
import { TIER_BEHAVIOUR } from '../../shared/lib/tiers'
import { Badge, ReasonList, TierBadge } from '../../shared/ui-kit'

const BUDGET_MS = 300

export function ScoreDetails({ result }: { result: ScoreResponse }) {
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <div>
          <p className="text-xs text-ink-400">Risk score</p>
          <p className="tabular text-3xl font-semibold">
            {result.r}
            <span className="text-base font-normal text-ink-400"> / 100</span>
          </p>
        </div>
        <div className="space-y-1">
          <TierBadge tier={result.tier} />
          <p className="text-xs text-ink-300">{TIER_BEHAVIOUR[result.tier]}</p>
        </div>
        <dl className="ml-auto grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
          <dt className="text-ink-400">Soft hold</dt>
          <dd className={result.soft_hold ? 'font-medium text-tier-critical' : 'text-ink-200'}>{result.soft_hold ? 'Yes, before debit' : 'No'}</dd>
          <dt className="text-ink-400">Latency</dt>
          <dd className={result.latency_ms > BUDGET_MS ? 'text-tier-high' : 'text-ink-200'}>
            {result.latency_ms} ms <span className="text-ink-500">/ {BUDGET_MS} ms budget</span>
          </dd>
          <dt className="text-ink-400">Text model</dt>
          <dd className="text-ink-200">{result.text_model_used === 'hf' ? 'Primary (HF)' : result.text_model_used === 'tfidf_lr' ? 'Fallback (TF-IDF + LR)' : 'Not used'}</dd>
        </dl>
      </div>

      {result.review_band_widened && (
        <p className="rounded-md border border-tier-medium/40 bg-tier-mediumSoft px-3 py-2 text-xs text-ink-50">
          Review band widened because these signals were unavailable: {result.missing_signals.map((s) => SIGNAL_LABEL[s]).join(', ')}.
        </p>
      )}

      <div>
        <p className="mb-2 text-2xs font-medium uppercase tracking-wider text-ink-400">Reason codes</p>
        <ReasonList reasons={result.reason_codes} />
      </div>

      {result.components && (
        <div>
          <p className="mb-2 text-2xs font-medium uppercase tracking-wider text-ink-400">Model contributions</p>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-4">
            {([
              ['Text model', result.components.text_prob],
              ['Transaction model', result.components.txn_prob],
              ['Rule layer', result.components.rule_prob],
            ] as const).map(([label, p]) => (
              <div key={label}>
                <dt className="text-ink-400">{label}</dt>
                <dd className="tabular text-ink-200">{p == null ? 'not used' : `P(scam) ${p.toFixed(2)}`}</dd>
              </div>
            ))}
            <div>
              <dt className="text-ink-400">Hard-rule floor</dt>
              <dd className={result.components.hard_rule_floor ? 'font-medium text-tier-critical' : 'text-ink-200'}>
                {result.components.hard_rule_floor ? `R ≥ ${result.components.hard_rule_floor}` : 'none'}
              </dd>
            </div>
          </dl>
          <p className="mt-1.5 text-2xs text-ink-500">
            Signals used: {result.components.signal_mode === 'both' ? 'message + payment' : result.components.signal_mode === 'text' ? 'message only' : 'payment only'}. Transaction model trained on PaySim (public synthetic mobile-money data, not UPI).
          </p>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-1.5 border-t border-navy-700 pt-3 text-2xs text-ink-400">
        <span>Event {result.event_id}</span>
        <span aria-hidden>·</span>
        {Object.entries(result.model_versions).map(([k, v]) => (
          <Badge key={k} title={k}>
            {v}
          </Badge>
        ))}
      </div>
    </div>
  )
}
