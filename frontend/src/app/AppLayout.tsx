import { ChartColumn, FlaskConical, LogOut, Radar, Smartphone } from 'lucide-react'
import type { ComponentType } from 'react'
import { NavLink, Outlet } from 'react-router'
import { API_BASE_URL, API_MODE } from '../shared/api-client'
import { useAuth } from '../shared/auth/AuthProvider'
import { canAccess, PANEL_PATH, ROLE_LABEL, type PanelKey } from '../shared/auth/permissions'
import { Badge, cx } from '../shared/ui-kit'
import { Logo } from './Logo'

const NAV: Array<{ panel: PanelKey; label: string; description: string; icon: ComponentType<{ className?: string }> }> = [
  { panel: 'simulator', label: 'Payment Simulator', description: 'Try a payment', icon: Smartphone },
  { panel: 'detection', label: 'Scam Detection', description: 'Live feed and review', icon: Radar },
  { panel: 'analysis', label: 'Analysis', description: 'Trends and fairness', icon: ChartColumn },
  { panel: 'evaluation', label: 'Model Evaluation', description: 'Offline metrics', icon: FlaskConical },
]

export function AppLayout() {
  const { user, logout } = useAuth()
  const items = NAV.filter((n) => canAccess(user?.role, n.panel))

  return (
    <div className="flex min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-navy-800 focus:px-3 focus:py-2">
        Skip to content
      </a>
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-navy-700 bg-navy-900 md:flex">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <Logo />
          <div>
            <p className="text-sm font-semibold leading-tight">Vyakhya</p>
            <p className="text-2xs text-ink-400">Scam pattern recognition</p>
          </div>
        </div>
        <nav aria-label="Panels" className="flex-1 space-y-0.5 px-3">
          {items.map(({ panel, label, description, icon: Icon }) => (
            <NavLink
              key={panel}
              to={PANEL_PATH[panel]}
              className={({ isActive }) =>
                cx(
                  'group flex items-start gap-3 rounded-md px-3 py-2 transition-colors',
                  isActive ? 'bg-navy-800 text-ink-50' : 'text-ink-300 hover:bg-navy-850 hover:text-ink-50',
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className={cx('mt-0.5 size-4 shrink-0', isActive ? 'text-teal-400' : 'text-ink-400 group-hover:text-ink-200')} />
                  <span>
                    <span className="block text-sm font-medium">{label}</span>
                    <span className="block text-2xs text-ink-400">{description}</span>
                  </span>
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-navy-700 px-5 py-4 text-2xs text-ink-400">
          {API_MODE === 'mock' ? (
            <>
              <p className="font-medium text-ink-200">Demo mode</p>
              <p className="mt-0.5">In-browser mock API with synthetic data. Set VITE_API_BASE_URL to connect a backend.</p>
            </>
          ) : (
            <>
              <p className="font-medium text-ink-200">Connected</p>
              <p className="mt-0.5 break-all">{API_BASE_URL}</p>
            </>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-4 border-b border-navy-700 bg-navy-950/95 px-4 backdrop-blur md:px-8">
          <div className="flex items-center gap-2 md:hidden">
            <Logo size={24} />
            <span className="text-sm font-semibold">Vyakhya</span>
          </div>
          <nav aria-label="Panels" className="scroll-thin flex gap-1 overflow-x-auto md:hidden">
            {items.map(({ panel, label }) => (
              <NavLink key={panel} to={PANEL_PATH[panel]} className={({ isActive }) => cx('whitespace-nowrap rounded px-2 py-1 text-xs', isActive ? 'bg-navy-800 text-ink-50' : 'text-ink-300')}>
                {label}
              </NavLink>
            ))}
          </nav>
          <p className="hidden text-xs text-ink-400 md:block">Every decision carries a plain-language reason.</p>
          {user && (
            <div className="flex items-center gap-3">
              <div className="text-right">
                <p className="text-xs font-medium text-ink-50">{user.name ?? user.sub}</p>
                <p className="text-2xs text-ink-400">{user.sub}</p>
              </div>
              <Badge tone="accent">{ROLE_LABEL[user.role]}</Badge>
              <button type="button" onClick={logout} className="rounded-md p-2 text-ink-400 hover:bg-navy-800 hover:text-ink-50" aria-label="Sign out" title="Sign out">
                <LogOut className="size-4" />
              </button>
            </div>
          )}
        </header>
        <main id="main" className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 md:px-8 md:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
