import type { ReactNode } from 'react'
import { CircleCheck, CircleAlert } from 'lucide-react'
import { cx } from './cx'

interface Props {
  label: string
  value: ReactNode
  /** e.g. "Target > 95%". */
  target?: string
  /** true = meets target, false = misses target, undefined = no target. */
  ok?: boolean
  hint?: ReactNode
}

export function Stat({ label, value, target, ok, hint }: Props) {
  return (
    <div className="rounded-lg border border-navy-700 bg-navy-900 px-4 py-3.5">
      <p className="text-xs text-ink-400">{label}</p>
      <p className="tabular mt-1 text-2xl font-semibold text-ink-50">{value}</p>
      {(target || hint) && (
        <div className="mt-1.5 flex items-center gap-1.5 text-xs">
          {ok !== undefined &&
            (ok ? <CircleCheck className="size-3.5 text-tier-low" aria-label="Meets target" /> : <CircleAlert className="size-3.5 text-tier-high" aria-label="Misses target" />)}
          {target && <span className={cx(ok === false ? 'text-tier-high' : 'text-ink-400')}>{target}</span>}
          {hint && <span className="text-ink-400">{hint}</span>}
        </div>
      )}
    </div>
  )
}
