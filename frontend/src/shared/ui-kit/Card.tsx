import type { ReactNode } from 'react'
import { cx } from './cx'

interface Props {
  title?: ReactNode
  description?: ReactNode
  actions?: ReactNode
  children?: ReactNode
  className?: string
  bodyClassName?: string
  as?: 'section' | 'div'
}

export function Card({ title, description, actions, children, className, bodyClassName, as: Tag = 'section' }: Props) {
  return (
    <Tag className={cx('rounded-lg border border-navy-700 bg-navy-900', className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-4 border-b border-navy-700 px-5 py-3.5">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold text-ink-50">{title}</h2>}
            {description && <p className="mt-0.5 text-xs text-ink-400">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx('p-5', bodyClassName)}>{children}</div>
    </Tag>
  )
}
