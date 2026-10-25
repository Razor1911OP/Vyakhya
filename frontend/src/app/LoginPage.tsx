import { useState, type FormEvent } from 'react'
import { Lock } from 'lucide-react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { API_MODE, errorMessage } from '../shared/api-client'
import { DEMO_ACCOUNTS, DEMO_PASSWORD } from '../shared/api-client/mock/server'
import { useAuth } from '../shared/auth/AuthProvider'
import { homePathFor, ROLE_LABEL } from '../shared/auth/permissions'
import { canAccess, type PanelKey } from '../shared/auth/permissions'
import { Button, Field, Input } from '../shared/ui-kit'
import { Logo } from './Logo'

export function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to={homePathFor(user.role)} replace />

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) {
      setError('Enter your username and password.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const claims = await login(username, password)
      const from = (location.state as { from?: string } | null)?.from
      const panel = from?.replace('/', '') as PanelKey | undefined
      navigate(panel && canAccess(claims.role, panel) ? from! : homePathFor(claims.role), { replace: true })
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-3">
          <Logo size={36} />
          <div>
            <p className="text-lg font-semibold leading-tight">Vyakhya</p>
            <p className="text-xs text-ink-400">Explainable scam pattern recognition</p>
          </div>
        </div>

        <form onSubmit={onSubmit} noValidate className="rounded-lg border border-navy-700 bg-navy-900 p-6">
          <h1 className="text-base">Sign in</h1>
          <p className="mt-1 text-xs text-ink-400">Use the account issued by your organisation.</p>
          <div className="mt-5 space-y-4">
            <Field label="Username">
              {(p) => <Input {...p} autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />}
            </Field>
            <Field label="Password">
              {(p) => <Input {...p} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />}
            </Field>
            {error && (
              <p role="alert" className="rounded-md border border-tier-critical/40 bg-tier-criticalSoft px-3 py-2 text-xs text-tier-critical">
                {error}
              </p>
            )}
            <Button type="submit" variant="primary" className="w-full" loading={busy} icon={<Lock className="size-4" />}>
              Sign in
            </Button>
          </div>
        </form>

        {API_MODE === 'live' && (
          <div className="mt-4 rounded-lg border border-navy-700 bg-navy-900/60 p-4 text-xs text-ink-300">
            <p className="font-medium text-ink-200">Demo accounts (local API)</p>
            <ul className="mt-2 space-y-1">
              {[
                ['analyst', 'analyst123', 'Analyst'],
                ['user', 'user123', 'Customer'],
              ].map(([u, p, label]) => (
                <li key={u} className="flex items-center justify-between">
                  <button type="button" className="font-mono text-teal-300 hover:underline" onClick={() => { setUsername(u); setPassword(p) }}>
                    {u}
                  </button>
                  <span className="text-ink-400">{label}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {API_MODE === 'mock' && (
          <div className="mt-4 rounded-lg border border-navy-700 bg-navy-900/60 p-4 text-xs text-ink-300">
            <p className="font-medium text-ink-200">Demo accounts</p>
            <p className="mt-0.5 text-ink-400">
              Mock API, synthetic data. Password for all: <code className="font-mono text-ink-200">{DEMO_PASSWORD}</code>
            </p>
            <ul className="mt-2 space-y-1">
              {DEMO_ACCOUNTS.map((a) => (
                <li key={a.username} className="flex items-center justify-between">
                  <button
                    type="button"
                    className="font-mono text-teal-300 hover:underline"
                    onClick={() => {
                      setUsername(a.username)
                      setPassword(DEMO_PASSWORD)
                    }}
                  >
                    {a.username}
                  </button>
                  <span className="text-ink-400">{ROLE_LABEL[a.role]}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <p className="mt-6 text-center text-2xs text-ink-500">Multi-factor sign-in is on the roadmap.</p>
      </div>
    </div>
  )
}
