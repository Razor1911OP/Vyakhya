import { useMemo, useRef, useState } from 'react'
import { Play, RotateCcw, Square } from 'lucide-react'
import { api, errorMessage } from '../../shared/api-client'
import type { ScoreRequest, ScoreResponse } from '../../shared/api-client/types'
import { maskVpa, redact } from '../../shared/lib/redaction'
import { Button, Card, Field, Input, LabelBadge, PageHeader, Switch, Textarea, cx } from '../../shared/ui-kit'
import { PhonePreview } from './PhonePreview'
import { COACHED_TRACE as MOCK_TRACE, EMPTY_FORM, LIVE_COACHED_TRACE, PRESETS, type PaymentForm } from './presets'

/** Mock API replays the deck trace; the live API runs the same story through the evaluated engine. */
const COACHED_TRACE = api.mode === 'live' ? LIVE_COACHED_TRACE : MOCK_TRACE
import { RedactionPreview } from './RedactionPreview'
import { RiskChart, cutoffsFrom, type RiskPoint } from './RiskChart'
import { ScoreDetails } from './ScoreDetails'
import { SignalControls } from './SignalControls'
import { validate } from './validation'

const STEP_MS = 3000
const newSession = () => crypto.randomUUID()

export function buildRequest(form: PaymentForm, sessionId: string): ScoreRequest {
  const message = form.consent && form.message.trim() ? { redacted_text: redact(form.message).redacted, consent: true as const } : null
  return {
    session_id: sessionId,
    payee_vpa: form.payee_vpa.trim(),
    amount: Number(form.amount),
    note: form.note.trim() ? redact(form.note).redacted : undefined,
    message,
    signals: form.signals,
    signals_simulated: true,
    trusted_payee: form.trusted_payee,
  }
}

export function SimulatorPanel() {
  const [form, setForm] = useState<PaymentForm>(PRESETS[0].form)
  const [sessionId, setSessionId] = useState(newSession)
  const [result, setResult] = useState<ScoreResponse | null>(null)
  const [points, setPoints] = useState<RiskPoint[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [touched, setTouched] = useState(false)
  const [traceStep, setTraceStep] = useState<number | null>(null)
  const stopRef = useRef(false)
  const startedAt = useRef<number | null>(null)

  const errors = validate(form)
  const valid = Object.keys(errors).length === 0
  const redaction = useMemo(() => redact(form.message), [form.message])
  const payload = valid ? buildRequest(form, sessionId) : null
  const tracing = traceStep !== null

  const update = (patch: Partial<PaymentForm>) => setForm((f) => ({ ...f, ...patch }))

  const reset = (next: PaymentForm) => {
    stopRef.current = true
    setForm(next)
    setSessionId(newSession())
    setResult(null)
    setPoints([])
    setError(null)
    setTouched(false)
    startedAt.current = null
  }

  const check = async (f: PaymentForm, sid: string, label?: string) => {
    setBusy(true)
    setError(null)
    try {
      const res = await api.score(buildRequest(f, sid))
      startedAt.current ??= Date.now()
      const t = label ?? `T+${Math.round((Date.now() - startedAt.current) / 1000)}s`
      setResult(res)
      setPoints((p) => [...p, { label: t, r: res.r, tier: res.tier }])
      return res
    } catch (err) {
      setError(errorMessage(err))
      return null
    } finally {
      setBusy(false)
    }
  }

  const onCheck = () => {
    setTouched(true)
    if (valid) void check(form, sessionId)
  }

  const playTrace = async () => {
    const sid = newSession()
    reset(COACHED_TRACE[0].form)
    setSessionId(sid)
    stopRef.current = false
    for (let i = 0; i < COACHED_TRACE.length; i++) {
      if (stopRef.current) break
      const step = COACHED_TRACE[i]
      setTraceStep(i)
      setForm(step.form)
      const res = await check(step.form, sid, `T+${step.t}s`)
      if (!res || i === COACHED_TRACE.length - 1) break
      await new Promise((r) => setTimeout(r, STEP_MS))
    }
    setTraceStep(null)
  }

  return (
    <>
      <PageHeader
        title="Payment Simulator"
        description="Check a payment before the debit. Each decision is explained in plain language."
        badges={
          <>
            <LabelBadge label="SYNTHETIC" />
            <LabelBadge label="SIMULATED" />
          </>
        }
      />
      <p className="-mt-3 mb-6 text-xs text-ink-400">Synthetic scenario. Call, screen-share, device, location, payee and hour signals are simulated with the controls below.</p>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
        <div className="space-y-6">
          <Card title="Scenarios" description="Load a preset, or enter your own payment.">
            <div className="grid gap-2 sm:grid-cols-3">
              {PRESETS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  disabled={tracing}
                  onClick={() => reset(p.form)}
                  className="rounded-md border border-navy-700 bg-navy-850 p-3 text-left transition-colors hover:border-navy-500 disabled:opacity-50"
                >
                  <span className="block text-sm font-medium">{p.title}</span>
                  <span className="mt-1 block text-xs text-ink-400">{p.summary}</span>
                </button>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-navy-700 pt-4">
              {tracing ? (
                <Button size="sm" icon={<Square className="size-3.5" />} onClick={() => (stopRef.current = true)}>
                  Stop trace
                </Button>
              ) : (
                <Button size="sm" variant="primary" icon={<Play className="size-3.5" />} onClick={() => void playTrace()}>
                  Play coached-victim trace
                </Button>
              )}
              <span className="text-xs text-ink-400">Five checks from T+0s to T+120s, shown in {(COACHED_TRACE.length - 1) * (STEP_MS / 1000)} seconds.</span>
            </div>
            {tracing && (
              <ol className="mt-3 space-y-1.5" aria-live="polite">
                {COACHED_TRACE.map((s, i) => (
                  <li key={s.t} className={cx('flex gap-3 text-xs', i === traceStep ? 'text-ink-50' : i < traceStep! ? 'text-ink-400' : 'text-ink-500')}>
                    <span className="tabular w-12 shrink-0 font-mono">T+{s.t}s</span>
                    <span>{s.narrative}</span>
                  </li>
                ))}
              </ol>
            )}
          </Card>

          <Card title="Payment">
            <fieldset disabled={tracing} className="grid gap-4 sm:grid-cols-2">
              <Field label="Payee UPI ID" error={touched ? errors.payee_vpa : undefined}>
                {(p) => <Input {...p} value={form.payee_vpa} placeholder="name@bank" onChange={(e) => update({ payee_vpa: e.target.value })} />}
              </Field>
              <Field label="Amount (₹)" error={touched ? errors.amount : undefined}>
                {(p) => <Input {...p} inputMode="numeric" value={form.amount} placeholder="0" onChange={(e) => update({ amount: e.target.value.replace(/[^\d.]/g, '') })} />}
              </Field>
              <Field label="Note" className="sm:col-span-2" hint="Optional. Redacted like the message.">
                {(p) => <Input {...p} value={form.note} maxLength={80} onChange={(e) => update({ note: e.target.value })} />}
              </Field>
              <div className="sm:col-span-2">
                <Switch checked={form.trusted_payee} onChange={(v) => update({ trusted_payee: v })} label="Saved payee" description="The customer has paid this payee before. Repeat warnings are suppressed." />
              </div>
            </fieldset>
          </Card>

          <Card title="Forwarded message" description="Paste the SMS or chat the customer received. Numbers are masked before anything is sent.">
            <fieldset disabled={tracing} className="space-y-4">
              <Field label="Message" error={errors.message} trailing={<span className="text-2xs text-ink-500">{form.message.length}/2000</span>}>
                {(p) => <Textarea {...p} rows={4} value={form.message} placeholder="e.g. Your KYC has expired. Share OTP 482913 to keep your account active." onChange={(e) => update({ message: e.target.value })} />}
              </Field>
              <Switch checked={form.consent} onChange={(v) => update({ consent: v })} label="Share this message for checking" description="Only the masked text is sent. It is not stored." />
              <RedactionPreview original={form.message} result={redaction} consent={form.consent} payload={payload} />
            </fieldset>
          </Card>

          <Card title="Context signals" actions={<LabelBadge label="SIMULATED" />} description="The prototype cannot read these from a real phone, so set them here.">
            <SignalControls value={form.signals} disabled={tracing} onChange={(signals) => update({ signals })} />
          </Card>

          <div className="flex items-center gap-3">
            <Button variant="primary" onClick={onCheck} loading={busy && !tracing} disabled={tracing}>
              Check payment
            </Button>
            <Button variant="ghost" icon={<RotateCcw className="size-4" />} onClick={() => reset(EMPTY_FORM)} disabled={tracing}>
              Clear
            </Button>
            {error && (
              <p role="alert" className="text-xs text-tier-critical">
                {error}
              </p>
            )}
          </div>
        </div>

        <div className="space-y-6 xl:sticky xl:top-20 xl:self-start">
          <Card title="Customer view" description="What the payer sees for this decision." bodyClassName="bg-navy-850/40">
            <PhonePreview result={result} amount={Number(form.amount) || 0} payee={form.payee_vpa ? maskVpa(form.payee_vpa) : ''} autoplay={tracing} />
          </Card>
          <Card
            title="Risk over this session"
            description={
              result?.cutoffs
                ? `Engine cutoffs for this decision: MEDIUM ${Math.round(result.cutoffs.medium)}, HIGH ${Math.round(result.cutoffs.high)}; CRITICAL = hard-rule hit (R ≥ 90). Tuned on synthetic data, re-calibrate at pilot.`
                : 'Tier thresholds at 40, 70 and 85.'
            }
          >
            <RiskChart points={points} cutoffs={cutoffsFrom(result?.cutoffs)} />
          </Card>
          <Card title="Decision" description="Response from POST /score.">
            {result ? <ScoreDetails result={result} /> : <p className="text-xs text-ink-400">No decision yet.</p>}
          </Card>
        </div>
      </div>
    </>
  )
}
