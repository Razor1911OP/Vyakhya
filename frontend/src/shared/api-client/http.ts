import { tokenStore } from '../auth/tokenStore'
import { ApiError } from './errors'
import {
  fromApiCase,
  fromApiEvent,
  fromApiMetrics,
  fromApiScore,
  fromApiStats,
  toApiScoreBody,
  type ApiCase,
  type ApiEvent,
  type ApiScoreResponse,
  type ApiStats,
} from './live-adapter'
import type { LoginResponse, StatsRange, VerdictRequest, VyakhyaApi } from './types'

const TIMEOUT_MS = 10_000

async function request<T>(base: string, path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (init.body) headers.set('Content-Type', 'application/json')
  const token = tokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let res: Response
  try {
    res = await fetch(`${base}${path}`, { ...init, headers, signal: controller.signal })
  } catch (err) {
    const aborted = err instanceof DOMException && err.name === 'AbortError'
    throw new ApiError(0, aborted ? 'The server took too long to respond.' : 'Could not reach the server.')
  } finally {
    clearTimeout(timer)
  }

  if (res.status === 401) tokenStore.set(null)
  if (!res.ok) {
    let detail: unknown
    try {
      detail = await res.json()
    } catch {
      detail = undefined
    }
    // The Node API answers { error, details?: string[] }.
    const d = detail as { error?: unknown; details?: unknown; detail?: unknown } | undefined
    const details = d?.details
    const parts = [d?.error, Array.isArray(details) ? details.join('; ') : d?.detail].filter((x): x is string => typeof x === 'string' && !!x)
    throw new ApiError(res.status, parts.length ? parts.join(': ') : `Request failed (${res.status}).`, detail)
  }
  return (await res.json()) as T
}

/** Live client for the Vyakhya Node API (Vyakhya-p2-backend/api). Shapes are mapped in live-adapter.ts. */
export function createHttpApi(base: string): VyakhyaApi {
  return {
    mode: 'live',
    login: async (username, password) => {
      const r = await request<{ token: string; role: string }>(base, '/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      })
      return { access_token: r.token, token_type: 'bearer' } satisfies LoginResponse
    },
    score: async (req) => {
      const r = await request<ApiScoreResponse>(base, '/score', { method: 'POST', body: JSON.stringify(toApiScoreBody(req)) })
      return fromApiScore(r, req)
    },
    events: async (query = {}) => {
      const list = (await request<ApiEvent[]>(base, '/events')).map(fromApiEvent)
      return list.filter((e) => !query.tier || e.tier === query.tier).slice(0, query.limit ?? 100)
    },
    cases: async () => (await request<ApiCase[]>(base, '/cases')).map(fromApiCase),
    verdict: async (req: VerdictRequest) =>
      fromApiCase(
        await request<ApiCase>(base, `/cases/${encodeURIComponent(req.case_id)}/decision`, {
          method: 'POST',
          body: JSON.stringify({ decision: req.action, note: req.note }),
        }),
      ),
    stats: async (range: StatsRange) => fromApiStats(await request<ApiStats>(base, `/stats?range=${range}`), range),
    metrics: async () => {
      const [files, events] = await Promise.all([
        request<Record<string, unknown>>(base, '/metrics'),
        request<ApiEvent[]>(base, '/events').catch(() => [] as ApiEvent[]),
      ])
      return fromApiMetrics(files, events)
    },
  }
}
