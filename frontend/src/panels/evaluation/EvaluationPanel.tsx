import type { ReactElement } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../../shared/api-client'
import type { MetricsBundle, MetricsMeta } from '../../shared/api-client/types'
import { FAMILY_LABEL } from '../../shared/lib/format'
import { useAsync } from '../../shared/useAsync'
import { Badge, Card, EmptyState, ErrorState, LabelBadge, Loading, PageHeader, Stat, Table, Td, Th, Tr, axisProps, tooltipProps, type Label } from '../../shared/ui-kit'
import { chart, tierColor } from '../../theme/tokens'

function Missing({ file }: { file: string }) {
  return <EmptyState title={`metrics/${file}.json not found`}>Run backend/jobs/eval.py to generate it.</EmptyState>
}

function Meta({ meta }: { meta?: MetricsMeta }) {
  if (!meta) return null
  return (
    <span className="flex gap-1">
      {meta.synthetic && <LabelBadge label="SYNTHETIC" />}
      {meta.placeholder && <LabelBadge label="PLACEHOLDER" />}
    </span>
  )
}

const SCOPE: Array<{ item: string; label: Label }> = [
  { item: 'Four panels, client-side redaction, RBAC route guards, live-stream client', label: 'BUILT' },
  { item: 'Call, screen-share, device, location signals and the money graph', label: 'SIMULATED' },
  { item: 'In-browser inference', label: 'ROADMAP' },
  { item: 'Cross-bank intelligence (private set intersection)', label: 'ROADMAP' },
  { item: 'Multi-factor sign-in', label: 'ROADMAP' },
]

export function EvaluationPanel() {
  const q = useAsync(() => api.metrics(), [])
  const m: MetricsBundle = q.data ?? {}
  const anyPlaceholder = Object.values(m).some((v) => (v as { _meta?: MetricsMeta })?._meta?.placeholder)

  if (q.loading && !q.data) return <Loading />
  if (q.error) return <ErrorState error={q.error} onRetry={() => void q.reload()} />

  const lofo = m.lofo
  const meanBase = lofo ? lofo.families.reduce((s, f) => s + f.baseline_text_only, 0) / lofo.families.length : 0
  const meanFused = lofo ? lofo.families.reduce((s, f) => s + f.fused, 0) / lofo.families.length : 0
  const cp = m.critical_precision
  const lat = m.latency

  return (
    <>
      <PageHeader
        title="Model Evaluation"
        description="Offline results read from metrics/*.json. Cutoffs are tuned on synthetic data and will be re-calibrated at pilot."
        badges={<LabelBadge label="SYNTHETIC" />}
      />
      {anyPlaceholder && (
        <p role="note" className="mb-6 rounded-md border border-tier-high/40 bg-tier-highSoft px-4 py-3 text-sm text-ink-50">
          Some files contain placeholder numbers for UI development, not measured results. They will be replaced by the output of <code className="font-mono text-xs">eval.py</code>.
        </p>
      )}

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Stat label="Mean unseen-family recall (fused)" value={lofo ? meanFused.toFixed(2) : '—'} target={lofo ? `Target ≥ ${lofo.target.toFixed(2)} · text-only ${meanBase.toFixed(2)}` : undefined} ok={lofo ? meanFused >= lofo.target : undefined} />
        <Stat label="Precision at CRITICAL" value={cp ? cp.precision.toFixed(2) : '—'} target={cp ? `Target ≥ ${cp.target.toFixed(2)} · n = ${cp.support}` : undefined} ok={cp ? cp.precision >= cp.target : undefined} />
        <Stat label="p95 latency, /score" value={lat ? `${lat.p95_ms} ms` : '—'} target={lat ? `Budget < ${lat.budget_ms} ms` : undefined} ok={lat ? lat.p95_ms < lat.budget_ms : undefined} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Leave-one-family-out recall" description={lofo ? `Train on four families, test on the held-out fifth. Recall at FPR ≤ ${lofo.max_fpr * 100}%.` : undefined} actions={<Meta meta={lofo?._meta} />}>
          {lofo ? (
            <>
              <ChartBox>
                <BarChart data={lofo.families.map((f) => ({ ...f, name: FAMILY_LABEL[f.family] }))} margin={{ top: 8, right: 8, left: -16 }}>
                  <CartesianGrid stroke={chart.grid} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" {...axisProps} interval={0} tick={{ ...axisProps.tick, fontSize: 10 }} />
                  <YAxis domain={[0, 1]} {...axisProps} />
                  <Tooltip {...tooltipProps} formatter={(v) => Number(v).toFixed(2)} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <ReferenceLine y={lofo.target} stroke={tierColor.LOW.fg} strokeDasharray="4 4" label={{ value: `Target ${lofo.target}`, position: 'insideTopRight', fill: tierColor.LOW.fg, fontSize: 10 }} />
                  <Bar dataKey="baseline_text_only" name="Text-only baseline" fill={chart.muted} isAnimationActive={false} />
                  <Bar dataKey="fused" name="Fused" fill={chart.primary} isAnimationActive={false} />
                </BarChart>
              </ChartBox>
              {lofo._meta.note && <p className="mt-2 text-2xs text-ink-400">{lofo._meta.note}</p>}
            </>
          ) : (
            <Missing file="lofo" />
          )}
        </Card>

        <Card title="Precision–recall curve" description={m.pr_curve ? `Reweighted to a realistic prevalence of ${m.pr_curve.prevalence} (illustrative).` : undefined} actions={<Meta meta={m.pr_curve?._meta} />}>
          {m.pr_curve ? (
            <ChartBox>
              <LineChart data={m.pr_curve.points} margin={{ top: 8, right: 84, left: -16 }}>
                <CartesianGrid stroke={chart.grid} strokeDasharray="3 3" />
                <XAxis type="number" dataKey="recall" domain={[0, 1]} {...axisProps} label={{ value: 'Recall', position: 'insideBottom', offset: -2, fill: chart.axis, fontSize: 11 }} />
                <YAxis type="number" domain={[0, 1]} {...axisProps} />
                <Tooltip {...tooltipProps} formatter={(v) => Number(v).toFixed(2)} labelFormatter={(v) => `Recall ${Number(v).toFixed(2)}`} />
                <Line type="monotone" dataKey="precision" name="Precision" stroke={chart.primary} strokeWidth={2} dot={false} isAnimationActive={false} />
                {m.pr_curve.cutoffs.map((c) => (
                  <ReferenceDot key={c.tier} x={c.recall} y={c.precision} r={5} fill={tierColor[c.tier].fg} stroke={chart.tooltipBg} label={{ value: `${c.tier} (R ${c.r})`, position: 'right', fill: tierColor[c.tier].fg, fontSize: 10 }} />
                ))}
              </LineChart>
            </ChartBox>
          ) : (
            <Missing file="pr_curve" />
          )}
        </Card>

        <Card title="Latency distribution" description={lat ? `p50 ${lat.p50_ms} ms · p95 ${lat.p95_ms} ms · p99 ${lat.p99_ms} ms. Bars past the ${lat.budget_ms} ms budget are highlighted.` : undefined} actions={<Meta meta={lat?._meta} />}>
          {lat ? (
            <ChartBox>
              <BarChart data={lat.histogram.map((h) => ({ ...h, name: `${h.start_ms}` }))} margin={{ top: 8, right: 8, left: -16 }}>
                <CartesianGrid stroke={chart.grid} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" {...axisProps} label={{ value: 'ms', position: 'insideBottomRight', fill: chart.axis, fontSize: 11 }} />
                <YAxis {...axisProps} />
                <Tooltip {...tooltipProps} labelFormatter={(v) => `${v}–${Number(v) + 25} ms`} />
                <Bar dataKey="count" name="Requests" isAnimationActive={false}>
                  {lat.histogram.map((h) => (
                    <Cell key={h.start_ms} fill={h.start_ms >= lat.budget_ms ? tierColor.HIGH.fg : chart.primary} />
                  ))}
                </Bar>
              </BarChart>
            </ChartBox>
          ) : (
            <Missing file="latency" />
          )}
        </Card>

        <Card title="Baseline vs fused" description="Text-only baseline against the full fusion model." actions={<Meta meta={m.comparison?._meta} />} bodyClassName="p-0">
          {m.comparison ? (
            <Table>
              <thead>
                <tr>
                  <Th className="pl-5">Metric</Th>
                  <Th className="text-right">Text-only</Th>
                  <Th className="text-right">Fused</Th>
                  <Th className="pr-5 text-right">Change</Th>
                </tr>
              </thead>
              <tbody>
                {m.comparison.rows.map((r) => {
                  const better = r.higher_is_better ? r.fused > r.baseline : r.fused < r.baseline
                  return (
                    <Tr key={r.metric}>
                      <Td className="pl-5">{r.metric}</Td>
                      <Td className="tabular text-right text-ink-300">{r.baseline}</Td>
                      <Td className="tabular text-right font-medium">{r.fused}</Td>
                      <Td className={`tabular pr-5 text-right text-xs ${better ? 'text-tier-low' : 'text-tier-high'}`}>{better ? 'Better' : 'Worse'}</Td>
                    </Tr>
                  )
                })}
              </tbody>
            </Table>
          ) : (
            <Missing file="comparison" />
          )}
        </Card>

        <Card title="Model registry" description="Versions loaded by the backend from model_registry/." actions={<Meta meta={m.registry?._meta} />} bodyClassName="p-0">
          {m.registry ? (
            <Table>
              <thead>
                <tr>
                  <Th className="pl-5">Model</Th>
                  <Th>Role</Th>
                  <Th>Version</Th>
                  <Th className="pr-5">Status</Th>
                </tr>
              </thead>
              <tbody>
                {m.registry.models.map((r) => (
                  <Tr key={r.name}>
                    <Td className="pl-5 font-mono text-xs">{r.name}</Td>
                    <Td className="text-xs text-ink-300">
                      {r.role}
                      {r.notes && <span className="block text-2xs text-ink-500">{r.notes}</span>}
                    </Td>
                    <Td className="font-mono text-xs">{r.version}</Td>
                    <Td className="pr-5">{r.in_use ? <Badge tone="accent">In use</Badge> : <Badge>Inactive</Badge>}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <Missing file="registry" />
          )}
        </Card>

        <Card title="Scope and labels" description="What is built, simulated, or planned.">
          <ul className="space-y-2.5">
            {SCOPE.map((s) => (
              <li key={s.item} className="flex items-start justify-between gap-4 text-sm">
                <span className="text-ink-200">{s.item}</span>
                <LabelBadge label={s.label} />
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  )
}

function ChartBox({ children }: { children: ReactElement }) {
  return (
    <div className="h-64">
      <ResponsiveContainer>{children}</ResponsiveContainer>
    </div>
  )
}
