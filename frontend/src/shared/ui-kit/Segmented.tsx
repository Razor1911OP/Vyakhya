import { cx } from './cx'

interface Option<T extends string> {
  value: T
  label: string
}

interface Props<T extends string> {
  value: T
  options: Option<T>[]
  onChange(value: T): void
  ariaLabel: string
  size?: 'sm' | 'md'
}

export function Segmented<T extends string>({ value, options, onChange, ariaLabel, size = 'md' }: Props<T>) {
  return (
    <div role="radiogroup" aria-label={ariaLabel} className="inline-flex rounded-md border border-navy-600 bg-navy-950 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cx(
            'rounded px-2.5 font-medium transition-colors',
            size === 'sm' ? 'h-6 text-2xs' : 'h-7 text-xs',
            value === o.value ? 'bg-navy-700 text-ink-50' : 'text-ink-400 hover:text-ink-200',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
