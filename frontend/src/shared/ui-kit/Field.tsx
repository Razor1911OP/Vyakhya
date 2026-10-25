import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { cx } from './cx'

const CONTROL =
  'w-full rounded-md border border-navy-600 bg-navy-950 px-3 text-sm text-ink-50 placeholder:text-ink-500 transition-colors hover:border-navy-500 focus:border-teal-500 focus:outline-none focus-visible:outline-none focus:ring-1 focus:ring-teal-500 disabled:opacity-60 aria-[invalid=true]:border-tier-critical'

interface FieldProps {
  label: ReactNode
  hint?: ReactNode
  error?: string
  children: (props: { id: string; 'aria-describedby'?: string; 'aria-invalid'?: boolean }) => ReactNode
  className?: string
  trailing?: ReactNode
}

export function Field({ label, hint, error, children, className, trailing }: FieldProps) {
  const id = useId()
  const describedBy = error ? `${id}-err` : hint ? `${id}-hint` : undefined
  return (
    <div className={cx('space-y-1.5', className)}>
      <div className="flex items-center justify-between gap-2">
        <label htmlFor={id} className="text-xs font-medium text-ink-200">
          {label}
        </label>
        {trailing}
      </div>
      {children({ id, 'aria-describedby': describedBy, 'aria-invalid': error ? true : undefined })}
      {error ? (
        <p id={`${id}-err`} className="text-xs text-tier-critical">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-xs text-ink-400">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx(CONTROL, 'h-10', className)} {...rest} />
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cx(CONTROL, 'scroll-thin min-h-24 resize-y py-2 leading-relaxed', className)} {...rest} />
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cx(CONTROL, 'h-9 pr-8', className)} {...rest}>
      {children}
    </select>
  )
}
