import { EyeOff } from 'lucide-react'
import { redactionSegments, type RedactionResult } from '../../shared/lib/redaction'
import { Badge } from '../../shared/ui-kit'
import type { ScoreRequest } from '../../shared/api-client/types'

interface Props {
  original: string
  result: RedactionResult
  consent: boolean
  payload: ScoreRequest | null
}

export function RedactionPreview({ original, result, consent, payload }: Props) {
  const masked = Object.entries(result.counts).filter(([, n]) => n > 0)
  const segments = redactionSegments(original, result.spans)

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5 text-xs text-ink-300">
        <EyeOff className="size-3.5 text-ink-400" aria-hidden />
        {masked.length === 0 ? (
          <span>No OTP, phone, card or account numbers found.</span>
        ) : (
          <>
            <span>Masked before sending:</span>
            {masked.map(([kind, n]) => (
              <Badge key={kind} tone="accent">
                {kind} × {n}
              </Badge>
            ))}
          </>
        )}
      </div>

      {original.trim() && (
        <div className="rounded-md border border-navy-700 bg-navy-950 p-3 text-xs leading-relaxed text-ink-200" aria-label="Message with masked values highlighted">
          {segments.map((s, i) =>
            s.kind ? (
              <mark key={i} className="rounded bg-teal-900 px-1 font-mono text-teal-300" title={`Masked ${s.kind}: original value is never sent`}>
                [{s.kind}]
              </mark>
            ) : (
              <span key={i}>{s.text}</span>
            ),
          )}
        </div>
      )}

      <div>
        <p className="mb-1.5 text-2xs font-medium uppercase tracking-wider text-ink-400">What we send</p>
        <pre className="scroll-thin max-h-56 overflow-auto rounded-md border border-navy-700 bg-navy-950 p-3 font-mono text-2xs leading-relaxed text-ink-300">
          {payload ? JSON.stringify(payload, null, 2) : 'Complete the payment details to preview the request.'}
        </pre>
        {!consent && original.trim() && <p className="mt-1.5 text-xs text-ink-400">The message is not sent because sharing is turned off.</p>}
        <p className="mt-1.5 text-2xs text-ink-500">The server repeats this redaction. Raw message text is never stored or logged.</p>
      </div>
    </div>
  )
}
