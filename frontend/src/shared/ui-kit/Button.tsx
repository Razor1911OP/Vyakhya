import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { LoaderCircle } from 'lucide-react'
import { cx } from './cx'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md'

const VARIANT: Record<Variant, string> = {
  primary: 'bg-teal-500 text-navy-950 hover:bg-teal-400 disabled:bg-navy-600 disabled:text-ink-400',
  secondary: 'border border-navy-600 bg-navy-800 text-ink-50 hover:border-navy-500 hover:bg-navy-700 disabled:text-ink-500',
  ghost: 'text-ink-200 hover:bg-navy-800 hover:text-ink-50 disabled:text-ink-500',
  danger: 'border border-tier-critical/60 bg-tier-criticalSoft text-tier-critical hover:bg-tier-critical hover:text-white disabled:opacity-50',
}

const SIZE: Record<Size, string> = {
  sm: 'h-8 px-3 text-xs gap-1.5',
  md: 'h-10 px-4 text-sm gap-2',
}

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
  icon?: ReactNode
}

export function Button({ variant = 'secondary', size = 'md', loading, icon, className, children, disabled, ...rest }: Props) {
  return (
    <button
      type="button"
      className={cx(
        'inline-flex shrink-0 items-center justify-center rounded-md font-medium transition-colors disabled:cursor-not-allowed',
        VARIANT[variant],
        SIZE[size],
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  )
}
