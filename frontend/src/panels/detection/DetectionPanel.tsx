import { useCallback, useMemo, useState } from 'react'
import { Pause, Play, RefreshCw } from 'lucide-react'
import { api } from '../../shared/api-client'
import type { Case, ClusterCandidate, ScoredEvent, Tier } from '../../shared/api-client/types'
import { FAMILY_LABEL, LANGUAGE_LABEL, formatCountdown, formatINR, formatTime } from '../../shared/lib/format'
import { useAsync } from '../../shared/useAsync'
import { useLiveStream } from '../../shared/useLiveStream'
import { Badge, Button, Card, EmptyState, ErrorState, LabelBadge, Loading, PageHeader, Segmented, Select, Stat, Table, Td, Th, TierBadge, Tr, cx } from '../../shared/ui-kit'
import { CaseDetail, STATUS_LABEL, useNow } from './CaseDetail'

const MAX_FEED = 200
type TierFilter = 'ALL' | Tier

export function DetectionPanel() {
  const eventsQ = useAsync(() => api.events({ limit: 50 }), [])
  const casesQ = useAsync(() => api.cases(), [])
  const statsQ = useAsync(() => api.stats('7d'), [])
  const [paused, setPaused] = useState(false)
  const [filter, setFilter] = useState<TierFilter>('ALL')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showClosed, setShowClosed] = useState(false)
  const now = useNow()

  const { reload: reloadCases, setData: setCases } = casesQ
  const { setData: setEvents } = eventsQ
  const onEvent = useCallback(
    (e: ScoredEvent) => {
      setEvents((list) => [e, ...(list ?? [])].slice(0, MAX_FEED))
      if (e.tier === 'HIGH' || e.tier === 'CRITICAL') void reloadCases()
    },
    [setEvents, reloadCases],
  )
  const stream = useLiveStream<ScoredEvent>(onEvent, { enabled: !paused })

  const events = (eventsQ.data ?? []).filter((e) => filter === 'ALL' || e.tier === filter)
  const allCases = useMemo(() => casesQ.data ?? [], [casesQ.data])
  const queue = useMemo(
    () => allCases.filter((c) => showClosed || c.status === 'pending' || c.status === 'awaiting_second_review').sort((a, b) => b.r - a.r),
    [allCases, showClosed],
  )
  const selected = queue.find((c) => c.case_id === selectedId) ?? queue[0] ?? null
  const openHolds = allCases.filter((c) => c.soft_hold && (c.status === 'pending' || c.status === 'awaiting_second_review')).length
  const recent = eventsQ.data ?? []
  const latencies = recent.map((e) => e.latency_ms).sort((a, b) => a - b)
  const p95 = latencies.length ? latencies[Math.floor(latencies.length * 0.95)] : 0

  const onUpdated = (next: Case) => setCases((list) => (list ?? []).map((c) => (c.case_id === next.case_id ? next : c)))

  return (
    <>
      <PageHeader
        title="Scam Detection"
        description="Live scoring feed and the analyst review queue. Holds are reversible and time-boxed to 30 minutes."
        badges={<LabelBadge label="SYNTHETIC" />}
        actions={
          <Button size="sm" icon={<RefreshCw className="size-3.5" />} onClick={() => void casesQ.reload()}>
            Refresh
          </Button>
        }
      />

      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Open holds" value={openHolds} hint="CRITICAL, before debit" />
        <Stat label="Cases in queue" value={allCases.filter((c) => c.status === 'pending' || c.status === 'awaiting_second_review').length} />
        <Stat label="Events in feed" value={recent.length} />
        <Stat label="p95 scoring latency" value={`${p95} ms`} target="Budget 300 ms" ok={p95 <= 300} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <Card
          title="Review queue"
          description="Ranked by risk score."
          actions={
            <label className="flex items-center gap-1.5 text-xs text-ink-300">
              <input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} className="accent-teal-500" /> Show closed
            </label>
          }
          bodyClassName="p-0"
        >
          {casesQ.loading && !casesQ.data ? (
            <Loading />
          ) : casesQ.error ? (
            <ErrorState error={casesQ.error} onRetry={() => void casesQ.reload()} />
          ) : queue.length === 0 ? (
            <EmptyState title="Queue is clear">New HIGH and CRITICAL payments appear here.</EmptyState>
          ) : (
            <ul className="scroll-thin max-h-[560px] divide-y divide-navy-800 overflow-y-auto">
              {queue.map((c) => {
                const remaining = c.expires_at ? Date.parse(c.expires_at) - now : null
                const open = c.status === 'pending' || c.status === 'awaiting_second_review'
                return (
                  <li key={c.case_id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(c.case_id)}
                      aria-current={selected?.case_id === c.case_id}
                      className={cx('w-full px-5 py-3 text-left transition-colors hover:bg-navy-850', selected?.case_id === c.case_id && 'bg-navy-800')}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <TierBadge tier={c.tier} />
                          <span className="tabular text-sm font-semibold">R {c.r}</span>
                          <span className="text-xs text-ink-300">{formatINR(c.amount)}</span>
                        </div>
                        {open && remaining !== null ? (
                          <span className={cx('tabular font-mono text-xs', remaining < 5 * 60_000 ? 'text-tier-high' : 'text-ink-400')}>{formatCountdown(remaining)}</span>
                        ) : (
                          <span className="text-2xs text-ink-400">{STATUS_LABEL[c.status]}</span>
                        )}
                      </div>
                      <p className="mt-1 truncate text-xs text-ink-300">{c.reason_codes[0]?.text}</p>
                      {c.status === 'awaiting_second_review' && <p className="mt-1 text-2xs text-tier-medium">Needs second reviewer</p>}
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </Card>

        <Card title="Case detail" description={selected ? selected.case_id : undefined}>
          {selected ? <CaseDetail key={selected.case_id} c={selected} onUpdated={onUpdated} /> : <EmptyState title="Select a case" />}
        </Card>
      </div>

      <Card
        className="mt-6"
        title="Live feed"
        description={
          <span className="flex items-center gap-1.5">
            <span className={cx('size-1.5 rounded-full', stream.status === 'open' ? 'bg-tier-low' : stream.status === 'reconnecting' ? 'bg-tier-medium' : 'bg-navy-500')} aria-hidden />
            {paused ? 'Paused' : stream.status === 'open' ? 'Connected' : stream.status === 'reconnecting' ? 'Reconnecting…' : 'Connecting…'}
            <span className="text-ink-500">· via {stream.transport === 'mock' ? 'mock stream' : stream.transport.toUpperCase()}</span>
          </span>
        }
        actions={
          <>
            <Segmented<TierFilter>
              size="sm"
              ariaLabel="Filter by tier"
              value={filter}
              onChange={setFilter}
              options={[
                { value: 'ALL', label: 'All' },
                { value: 'MEDIUM', label: 'Medium' },
                { value: 'HIGH', label: 'High' },
                { value: 'CRITICAL', label: 'Critical' },
              ]}
            />
            <Button size="sm" variant="ghost" icon={paused ? <Play className="size-3.5" /> : <Pause className="size-3.5" />} onClick={() => setPaused((p) => !p)}>
              {paused ? 'Resume' : 'Pause'}
            </Button>
          </>
        }
        bodyClassName="p-0"
      >
        {eventsQ.loading && !eventsQ.data ? (
          <Loading />
        ) : eventsQ.error ? (
          <ErrorState error={eventsQ.error} onRetry={() => void eventsQ.reload()} />
        ) : events.length === 0 ? (
          <EmptyState title="No events match this filter" />
        ) : (
          <Table className="max-h-[420px] overflow-y-auto">
            <thead className="sticky top-0 bg-navy-900">
              <tr>
                <Th>Time</Th>
                <Th>Tier</Th>
                <Th className="text-right">R</Th>
                <Th className="text-right">Amount</Th>
                <Th>Payee</Th>
                <Th>Top reason</Th>
                <Th>Lang</Th>
                <Th className="text-right">Latency</Th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <Tr key={e.event_id} className="hover:bg-navy-850">
                  <Td className="tabular whitespace-nowrap font-mono text-xs text-ink-300">{formatTime(e.ts)}</Td>
                  <Td>
                    <TierBadge tier={e.tier} />
                  </Td>
                  <Td className="tabular text-right font-medium">{e.r}</Td>
                  <Td className="tabular whitespace-nowrap text-right">{formatINR(e.amount)}</Td>
                  <Td className="whitespace-nowrap font-mono text-xs text-ink-300">{e.payee_vpa_masked}</Td>
                  <Td className="max-w-[360px] text-xs text-ink-200">
                    <span className="line-clamp-1">{e.reason_codes[0]?.text ?? 'No risk factors'}</span>
                  </Td>
                  <Td className="text-xs text-ink-400">{e.language ? LANGUAGE_LABEL[e.language] : '—'}</Td>
                  <Td className={cx('tabular text-right text-xs', e.latency_ms > 300 ? 'text-tier-high' : 'text-ink-300')}>{e.latency_ms} ms</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <NovelClusters clusters={statsQ.data?.cluster_candidates} loading={statsQ.loading} error={statsQ.error} />
    </>
  )
}

type Triage = 'new' | 'confirmed' | 'dismissed'
const TRIAGE_KEY = 'vyakhya.cluster_triage'

function NovelClusters({ clusters, loading, error }: { clusters?: ClusterCandidate[]; loading: boolean; error: unknown }) {
  const [triage, setTriage] = useState<Record<string, Triage>>(() => JSON.parse(localStorage.getItem(TRIAGE_KEY) ?? '{}'))
  const set = (id: string, v: Triage) => {
    const next = { ...triage, [id]: v }
    setTriage(next)
    localStorage.setItem(TRIAGE_KEY, JSON.stringify(next))
  }
  return (
    <Card
      className="mt-6"
      title="Novel cluster candidates"
      description="Groups of messages unlike any known pattern, found by offline HDBSCAN clustering. For analyst triage only; novelty never raises R."
      actions={<LabelBadge label="SYNTHETIC" />}
    >
      {loading && !clusters ? (
        <Loading />
      ) : error ? (
        <ErrorState error={error} />
      ) : !clusters?.length ? (
        <EmptyState title="No novel clusters" />
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          {clusters.map((c) => (
            <article key={c.cluster_id} className="flex flex-col rounded-md border border-navy-700 bg-navy-850 p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-medium">{c.cluster_id}</span>
                  <Badge tone="info">NOVEL</Badge>
                </div>
                <span className="text-xs text-ink-400">{c.size} messages</span>
              </div>
              <p className="mt-3 flex-1 text-xs leading-relaxed text-ink-200">“{c.sample_redacted}”</p>
              <div className="mt-3 flex flex-wrap gap-1">
                {c.top_terms.map((t) => (
                  <Badge key={t}>{t}</Badge>
                ))}
              </div>
              <p className="mt-3 text-2xs text-ink-400">
                Nearest known: {FAMILY_LABEL[c.nearest_known_family]} (distance {c.distance.toFixed(2)}) · {c.languages.map((l) => LANGUAGE_LABEL[l]).join(', ')}
              </p>
              <div className="mt-3 flex items-center gap-2 border-t border-navy-700 pt-3">
                <Select aria-label={`Triage ${c.cluster_id}`} value={triage[c.cluster_id] ?? 'new'} onChange={(e) => set(c.cluster_id, e.target.value as Triage)} className="h-8 text-xs">
                  <option value="new">Not triaged</option>
                  <option value="confirmed">Confirmed new pattern</option>
                  <option value="dismissed">Dismissed (benign)</option>
                </Select>
              </div>
            </article>
          ))}
        </div>
      )}
      <p className="mt-3 text-2xs text-ink-500">Triage choices are saved in this browser only until a triage endpoint exists.</p>
    </Card>
  )
}
