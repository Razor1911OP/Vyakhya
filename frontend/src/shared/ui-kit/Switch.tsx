import { cx } from './cx'

interface Props {
  checked: boolean
  onChange(checked: boolean): void
  label: string
  description?: string
  disabled?: boolean
}

export function Switch({ checked, onChange, label, description, disabled }: Props) {
  return (
    <label className={cx('flex cursor-pointer items-start justify-between gap-4', disabled && 'cursor-not-allowed opacity-60')}>
      <span className="min-w-0">
        <span className="block text-sm text-ink-50">{label}</span>
        {description && <span className="mt-0.5 block text-xs text-ink-400">{description}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cx(
          'relative mt-0.5 inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors',
          checked ? 'border-teal-500 bg-teal-500' : 'border-navy-500 bg-navy-700',
        )}
      >
        <span className={cx('inline-block size-3.5 rounded-full bg-white transition-transform', checked ? 'translate-x-[18px]' : 'translate-x-0.5')} />
      </button>
    </label>
  )
}
