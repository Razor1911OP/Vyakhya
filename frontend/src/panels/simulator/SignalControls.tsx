import type { ContextSignals, SignalKey } from '../../shared/api-client/types'
import { SIGNAL_LABEL } from '../../shared/lib/format'
import { Segmented } from '../../shared/ui-kit'

type Choice = 'no' | 'yes' | 'unknown'
const toChoice = (v: boolean | null): Choice => (v === null ? 'unknown' : v ? 'yes' : 'no')
const fromChoice = (c: Choice): boolean | null => (c === 'unknown' ? null : c === 'yes')

const OPTIONS = [
  { value: 'no' as const, label: 'No' },
  { value: 'yes' as const, label: 'Yes' },
  { value: 'unknown' as const, label: 'Unknown' },
]

export function SignalControls({ value, onChange, disabled }: { value: ContextSignals; onChange(next: ContextSignals): void; disabled?: boolean }) {
  return (
    <fieldset disabled={disabled} className="space-y-2.5 disabled:opacity-60">
      <legend className="sr-only">Simulated context signals</legend>
      {(Object.keys(SIGNAL_LABEL) as SignalKey[]).map((key) => (
        <div key={key} className="flex items-center justify-between gap-3">
          <span className="text-sm text-ink-50">{SIGNAL_LABEL[key]}</span>
          <Segmented size="sm" ariaLabel={SIGNAL_LABEL[key]} value={toChoice(value[key])} options={OPTIONS} onChange={(c) => onChange({ ...value, [key]: fromChoice(c) })} />
        </div>
      ))}
      <p className="pt-1 text-xs text-ink-400">"Unknown" means the signal could not be read. That widens the review band; it never lowers the risk.</p>
    </fieldset>
  )
}
