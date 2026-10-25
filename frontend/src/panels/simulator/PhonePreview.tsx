import { useEffect, useState, type ReactNode } from 'react'
import { CircleCheck, Hand, PauseCircle, PhoneCall, ShieldAlert, TriangleAlert } from 'lucide-react'
import type { ScoreResponse } from '../../shared/api-client/types'
import { formatINR } from '../../shared/lib/format'
import { Button, Modal, ReasonList } from '../../shared/ui-kit'

const WAIT_SECONDS = 30

type Outcome = 'pending' | 'sent' | 'stopped' | 'held'

interface Props {
  result: ScoreResponse | null
  amount: number
  payee: string
  /** Set during an automated trace so the screen does not wait for taps. */
  autoplay?: boolean
}

export function PhonePreview(props: Props) {
  // Remount per decision so countdowns and choices reset.
  return <PhoneScreen key={props.result?.event_id ?? 'empty'} {...props} />
}

function PhoneScreen({ result, amount, payee, autoplay }: Props) {
  const [outcome, setOutcome] = useState<Outcome>(result?.tier === 'LOW' ? 'sent' : 'pending')
  const [secondsLeft, setSecondsLeft] = useState(WAIT_SECONDS)
  const [whyOpen, setWhyOpen] = useState(false)

  useEffect(() => {
    if (result?.tier !== 'HIGH' || outcome !== 'pending') return
    const t = setInterval(() => setSecondsLeft((s) => Math.max(0, s - 1)), 1000)
    return () => clearInterval(t)
  }, [result?.tier, outcome])

  return (
    <div className="mx-auto w-full max-w-[300px] rounded-[28px] border border-navy-600 bg-navy-950 p-2.5 shadow-xl">
      <div className="flex min-h-[420px] flex-col overflow-hidden rounded-[20px] border border-navy-700 bg-navy-900">
        <div className="flex items-center justify-between px-4 pb-2 pt-3 text-2xs text-ink-400">
          <span>Your bank · UPI</span>
          {result?.tier && <span>R {result.r}</span>}
        </div>
        <div className="border-b border-navy-700 px-4 pb-4">
          <p className="text-2xs text-ink-400">Paying</p>
          <p className="tabular text-2xl font-semibold">{amount > 0 ? formatINR(amount) : '₹—'}</p>
          <p className="truncate text-xs text-ink-300">to {payee || 'payee'}</p>
        </div>

        <div className="flex flex-1 flex-col p-4">
          {!result && <p className="m-auto text-center text-xs text-ink-400">Fill in the payment and select Check payment to see what the customer would see.</p>}

          {result && outcome === 'sent' && (
            <Centered icon={<CircleCheck className="size-8 text-tier-low" />} title="Payment sent" body={result.tier === 'LOW' ? 'No warning shown. The check ran silently and was logged.' : 'The customer chose to continue.'} />
          )}
          {result && outcome === 'stopped' && <Centered icon={<Hand className="size-8 text-ink-300" />} title="Payment stopped" body="No money has moved." />}
          {result && outcome === 'held' && (
            <Centered icon={<PauseCircle className="size-8 text-tier-critical" />} title="On hold for review" body="An analyst will review this. The hold is reversible and expires in 30 minutes." />
          )}

          {result?.tier === 'MEDIUM' && outcome === 'pending' && (
            <div className="space-y-4">
              <div className="rounded-lg border border-tier-medium/40 bg-tier-mediumSoft p-3">
                <p className="flex items-center gap-1.5 text-sm font-medium text-tier-medium">
                  <TriangleAlert className="size-4" /> Take a moment
                </p>
                <p className="mt-1.5 text-xs text-ink-50">{result.reason_codes[0]?.text ?? 'Please check this payment.'}</p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Button size="sm" onClick={() => setOutcome('stopped')}>Cancel</Button>
                <Button size="sm" variant="primary" onClick={() => setOutcome('sent')}>Proceed</Button>
              </div>
            </div>
          )}

          {result?.tier === 'HIGH' && outcome === 'pending' && (
            <div className="space-y-4">
              <div className="rounded-lg border border-tier-high/40 bg-tier-highSoft p-3">
                <p className="flex items-center gap-1.5 text-sm font-medium text-tier-high">
                  <PhoneCall className="size-4" /> Are you on a call with someone guiding this payment?
                </p>
                <p className="mt-1.5 text-xs text-ink-50">{result.reason_codes[0]?.text}</p>
                <p className="mt-2 text-xs text-ink-300">Banks never ask you to move money to "secure" your account.</p>
              </div>
              <div className="grid gap-2">
                <Button size="sm" variant="primary" onClick={() => setOutcome('stopped')}>Stop payment</Button>
                <Button size="sm" disabled={secondsLeft > 0 || autoplay} onClick={() => setOutcome('sent')} aria-live="polite">
                  {secondsLeft > 0 ? `I'm alone, continue (${secondsLeft}s)` : "I'm alone, continue"}
                </Button>
              </div>
              <p className="text-center text-2xs text-ink-400">The 30-second wait cannot be skipped.</p>
            </div>
          )}

          {result?.tier === 'CRITICAL' && outcome === 'pending' && (
            <div className="space-y-4">
              <div className="rounded-lg border border-tier-critical/50 bg-tier-criticalSoft p-3">
                <p className="flex items-center gap-1.5 text-sm font-medium text-tier-critical">
                  <ShieldAlert className="size-4" /> We've paused this transfer for your safety
                </p>
                <p className="mt-1.5 text-xs text-ink-50">Your money has not left your account. We will call you back from our official number.</p>
                <p className="mt-2 text-xs font-medium text-ink-50">We will never ask for your OTP or PIN.</p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Button size="sm" onClick={() => setWhyOpen(true)}>Why?</Button>
                <Button size="sm" variant="primary" onClick={() => setOutcome('held')}>Okay</Button>
              </div>
            </div>
          )}
        </div>
      </div>

      {result && (
        <Modal open={whyOpen} onClose={() => setWhyOpen(false)} title="Why we paused this payment" footer={<Button variant="primary" onClick={() => setWhyOpen(false)}>Close</Button>}>
          <ReasonList reasons={result.reason_codes} />
        </Modal>
      )}
    </div>
  )
}

function Centered({ icon, title, body }: { icon: ReactNode; title: string; body: string }) {
  return (
    <div className="m-auto flex flex-col items-center gap-2 text-center">
      {icon}
      <p className="text-sm font-medium">{title}</p>
      <p className="text-xs text-ink-400">{body}</p>
    </div>
  )
}
