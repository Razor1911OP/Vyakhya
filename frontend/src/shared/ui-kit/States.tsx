import type { ReactNode } from 'react'
import { LoaderCircle, ShieldOff, TriangleAlert } from 'lucide-react'
import { Link } from 'react-router'
import { errorMessage } from '../api-client/errors'
import { Button } from './Button'

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-10 text-sm text-ink-400">
      <LoaderCircle className="size-4 animate-spin" aria-hidden />
      {label}
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-4 py-10 text-center">
      <p className="text-sm font-medium text-ink-200">{title}</p>
      {children && <div className="mt-1 max-w-sm text-xs text-ink-400">{children}</div>}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center justify-center gap-3 px-4 py-10 text-center">
      <TriangleAlert className="size-5 text-tier-high" aria-hidden />
      <p className="text-sm text-ink-200">{errorMessage(error)}</p>
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}

export function NoAccess() {
  return (
    <div className="mx-auto mt-16 max-w-md rounded-lg border border-navy-700 bg-navy-900 p-8 text-center">
      <ShieldOff className="mx-auto size-6 text-ink-400" aria-hidden />
      <h1 className="mt-3 text-base">You don't have access to this panel</h1>
      <p className="mt-1 text-sm text-ink-400">This area is limited to analyst and admin roles. Ask an administrator if you need access.</p>
      <Link to="/" className="mt-4 inline-block text-sm text-teal-300 hover:underline">
        Go to your home panel
      </Link>
    </div>
  )
}
