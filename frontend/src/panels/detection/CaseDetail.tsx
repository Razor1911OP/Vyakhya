import { useEffect, useState } from 'react'
import { Ban, Check, Clock } from 'lucide-react'
import { api, errorMessage } from '../../shared/api-client'
import type { Case } from '../../shared/api-client/types'
import { useAuth } from '../../shared/auth/AuthProvider'
import { FAMILY_LABEL, formatCountdown, formatDateTime, formatINR } from '../../shared/lib/format'
import { Badge, Button, Field, LabelBadge, Modal, ReasonList, Textarea, TierBadge } from '../../shared/ui-kit'
import { MoneyGraph } from './MoneyGraph'

export const STATUS_LABEL: Record<Case['status'], string> = {
  pending: 'Awaiting review',
  awaiting_second_review: 'Needs second reviewer',
  released: 'Released',
  blocked: 'Blocked',
  escalated: 'Escalated on expiry',
}

export function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(t)
  }, [intervalMs])
  return now
}

export function CaseDetail({ c, onUpdated }: { c: Case; onUpdated(next: Case): void }) {
  const { user } = useAuth()
  const now = useNow()
  const [action, setAction] = useState<'release' | 'block' | null>(null)
  const [note, setNote] = useState('')
  const [report, setReport] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const open = c.status === 'pending' || c.status === 'awaiting_second_review'
  const remaining = c.expires_at ? Date.parse(c.expires_at) - now : null
  const firstReviewer = c.reviews.find((r) => r.action === 'release')?.analyst
  const sameReviewer = c.status === 'awaiting_second_review' && firstReviewer === user?.sub
  // Dual review exists in the mock API only; the live API closes a case on one decision (ROADMAP).
  const needsDual = c.tier === 'CRITICAL' && api.mode === 'mock'

  const submit = async () => {
    if (!action) return
    setBusy(true)
    setError(null)
    try {
      const next = await api.verdict({ case_id: c.case_id, action, note, report: action === 'block' ? report : false })
      onUpdated(next)
      setAction(null)
      setNote('')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <TierBadge tier={c.tier} />
            <span className="tabular text-lg font-semibold">R {c.r}</span>
            {c.soft_hold && <Badge tone="critical">Soft hold</Badge>}
          </div>
          <p className="mt-1 text-xs text-ink-400">
            {formatINR(c.amount)} to {c.payee_vpa_masked} · {FAMILY_LABEL[c.family_guess ?? 'unknown']} · opened {formatDateTime(c.created_at)}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs font-medium text-ink-200">{STATUS_LABEL[c.status]}</p>
          {open && remaining !== null && (
            <p className={`tabular mt-0.5 flex items-center justify-end gap-1 text-xs ${remaining < 5 * 60_000 ? 'text-tier-high' : 'text-ink-400'}`}>
              <Clock className="size-3.5" /> {c.tier === 'CRITICAL' ? 'Escalates to analyst' : 'Auto-releases'} in {formatCountdown(remaining)}
            </p>
          )}
        </div>
      </div>

      <section>
        <h3 className="mb-2 text-2xs font-medium uppercase tracking-wider text-ink-400">Why it was flagged</h3>
        <ReasonList reasons={c.reason_codes} />
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <section>
          <h3 className="mb-2 text-2xs font-medium uppercase tracking-wider text-ink-400">Signal timeline</h3>
          <ol className="space-y-2 border-l border-navy-600 pl-4">
            {c.timeline.map((t, i) => (
              <li key={i} className="relative text-xs">
                <span className="absolute -left-[21px] top-1 size-2 rounded-full bg-navy-500" aria-hidden />
                <span className="tabular mr-2 font-mono text-ink-400">T+{t.t_offset_s}s</span>
                <span className="text-ink-50">{t.label}</span>
                {t.r !== undefined && <span className="tabular ml-2 text-ink-400">R {t.r}</span>}
              </li>
            ))}
          </ol>
        </section>
        <section>
          <div className="mb-2 flex items-center gap-2">
            <h3 className="text-2xs font-medium uppercase tracking-wider text-ink-400">Money graph</h3>
            {c.money_graph.simulated && <LabelBadge label="SIMULATED" />}
          </div>
          <MoneyGraph graph={c.money_graph} />
        </section>
      </div>

      {c.reviews.length > 0 && (
        <section>
          <h3 className="mb-2 text-2xs font-medium uppercase tracking-wider text-ink-400">Audit trail</h3>
          <ul className="space-y-1.5 text-xs">
            {c.reviews.map((r, i) => (
              <li key={i} className="rounded-md border border-navy-700 bg-navy-850 px-3 py-2">
                <span className="font-medium text-ink-50">{r.analyst}</span> <span className="text-ink-400">{r.action === 'release' ? 'released' : r.report ? 'blocked and reported' : 'blocked'} · {formatDateTime(r.ts)}</span>
                <p className="mt-0.5 text-ink-300">{r.note}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {open && (
        <div className="space-y-2 border-t border-navy-700 pt-4">
          {c.status === 'awaiting_second_review' && (
            <p className="text-xs text-tier-medium">
              {firstReviewer} approved release. A different analyst must confirm before the money moves.
              {sameReviewer && ' Sign in as another analyst to confirm.'}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button variant="danger" icon={<Ban className="size-4" />} onClick={() => setAction('block')}>
              Block and report
            </Button>
            <Button icon={<Check className="size-4" />} onClick={() => setAction('release')} disabled={sameReviewer}>
              {c.status === 'awaiting_second_review' ? 'Confirm release' : 'Release'}
            </Button>
          </div>
        </div>
      )}

      <Modal
        open={action !== null}
        onClose={() => setAction(null)}
        title={action === 'block' ? 'Block this payment' : needsDual && c.status === 'pending' ? 'Release (first review of two)' : 'Release this payment'}
        footer={
          <>
            <Button variant="ghost" onClick={() => setAction(null)}>
              Cancel
            </Button>
            <Button variant={action === 'block' ? 'danger' : 'primary'} loading={busy} disabled={note.trim().length < 8} onClick={() => void submit()}>
              {action === 'block' ? 'Block payment' : 'Release payment'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {action === 'release' && needsDual && c.status === 'pending' && (
            <p className="text-xs text-ink-300">CRITICAL holds need two analysts. Your approval is recorded, and the payment stays on hold until a second analyst confirms.</p>
          )}
          <Field label="Reason for decision" hint="Recorded in the audit log. At least 8 characters.">
            {(p) => <Textarea {...p} rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Customer confirmed on safe call-back that the caller was not from the bank." />}
          </Field>
          {action === 'block' && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={report} onChange={(e) => setReport(e.target.checked)} className="size-4 accent-teal-500" />
              Report the payee account as a suspected mule
            </label>
          )}
          {error && (
            <p role="alert" className="text-xs text-tier-critical">
              {error}
            </p>
          )}
        </div>
      </Modal>
    </div>
  )
}
