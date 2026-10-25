import type { ReasonCode } from '../api-client/types'
import { cx } from './cx'

export function ReasonList({ reasons, limit, compact, className }: { reasons: ReasonCode[]; limit?: number; compact?: boolean; className?: string }) {
  const shown = limit ? reasons.slice(0, limit) : reasons
  if (shown.length === 0) return <p className="text-xs text-ink-400">No risk factors were found.</p>
  return (
    <ol className={cx(compact ? 'space-y-1' : 'space-y-2.5', className)}>
      {shown.map((r) => (
        <li key={r.code} className="flex gap-2.5">
          <span className="mt-[7px] size-1.5 shrink-0 rounded-full bg-teal-400" aria-hidden />
          <span className="min-w-0">
            <span className={cx('block text-ink-50', compact ? 'text-xs' : 'text-sm')}>{r.text}</span>
            {!compact && <code className="mt-0.5 block font-mono text-2xs text-ink-500">{r.code}</code>}
          </span>
        </li>
      ))}
    </ol>
  )
}
