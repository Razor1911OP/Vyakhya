import { useEffect, useId, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { cx } from './cx'

interface Props {
  open: boolean
  onClose(): void
  title: ReactNode
  children: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'md'
}

export function Modal({ open, onClose, title, children, footer, size = 'md' }: Props) {
  const titleId = useId()
  const panel = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    panel.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      previous?.focus()
    }
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-navy-950/80" onClick={onClose} aria-hidden />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={cx('relative w-full rounded-lg border border-navy-600 bg-navy-900 shadow-2xl outline-none', size === 'sm' ? 'max-w-sm' : 'max-w-lg')}
      >
        <header className="flex items-center justify-between border-b border-navy-700 px-5 py-3.5">
          <h2 id={titleId} className="text-sm font-semibold">
            {title}
          </h2>
          <button type="button" onClick={onClose} className="rounded p-1 text-ink-400 hover:bg-navy-800 hover:text-ink-50" aria-label="Close">
            <X className="size-4" />
          </button>
        </header>
        <div className="scroll-thin max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-navy-700 px-5 py-3">{footer}</footer>}
      </div>
    </div>
  )
}
