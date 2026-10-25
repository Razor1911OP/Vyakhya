import type { ReactNode } from 'react'

export function PageHeader({ title, description, actions, badges }: { title: string; description?: ReactNode; actions?: ReactNode; badges?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl text-ink-50">{title}</h1>
          {badges}
        </div>
        {description && <p className="mt-1 max-w-3xl text-sm text-ink-300">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}
