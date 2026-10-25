import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../../shared/api-client'
import type { StatsRange } from '../../shared/api-client/types'
import { FAMILY_LABEL, LANGUAGE_LABEL, formatInt, formatPct } from '../../shared/lib/format'
import { useAsync } from '../../shared/useAsync'
import { Card, ErrorState, LabelBadge, Loading, PageHeader, Segmented, Stat, Table, Td, Th, TierBadge, Tr, axisProps, tooltipProps, cx } from '../../shared/ui-kit'
import { chart, tierColor } from '../../theme/tokens'

export function AnalysisPanel() {
  const [range, setRange] = useState<StatsRange>('7d')
  const q = useAsync(() => api.stats(range), [range])
  const s = q.data

  return (
    <>
      <PageHeader
        title="Analysis"
        description="How the system behaves over time: who sees friction, how often, and whether it is fair across cohorts."
        badges={s?.synthetic !== false && <LabelBadge label="SYNTHETIC" />}
        actions={<Segmented<StatsRange> ariaLabel="Date range" value={range} onChange={setRange} options={[{ value: '7d', label: 'Last 7 days' }, { value: '30d', label: 'Last 30 days' }]} />}
      />
      {q.loading && !s ? (
        <Loading />
      ) : q.error ? (
        <ErrorState error={q.error} onRetry={() => void q.reload()} />
      ) : s ? (
        <div className={cx('space-y-6', q.loading && 'opacity-60')}>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            <Stat label="Payments scored" value={formatInt(s.totals.payments)} />
            <Stat label="Payments with zero friction" value={formatPct(s.totals.zero_friction_pct)} target={`Target > ${s.targets.zero_friction_pct}%`} ok={s.totals.zero_friction_pct > s.targets.zero_friction_pct} />
            <Stat label="Alerts per user per week" value={s.totals.alerts_per_user_week.toFixed(2)} target={`Target ≤ ${s.targets.alerts_per_user_week}`} ok={s.totals.alerts_per_user_week <= s.targets.alerts_per_user_week} />
            <Stat label="Soft holds placed" value={formatInt(s.totals.holds)} />
            <Stat label="Users over alert budget" value={formatInt(s.totals.users_over_budget)} hint={`of ${formatInt(s.totals.users)}`} />
          </div>

          <Card title="Interventions over time" description="MEDIUM, HIGH and CRITICAL decisions per day. LOW payments pass silently and are left out.">
            <div className="h-72">
              <ResponsiveContainer>
                <BarChart data={s.trend} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
                  <CartesianGrid stroke={chart.grid} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="date" {...axisProps} tickFormatter={(d: string) => d.slice(5)} />
                  <YAxis {...axisProps} />
                  <Tooltip {...tooltipProps} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  {(['MEDIUM', 'HIGH', 'CRITICAL'] as const).map((t) => (
                    <Bar key={t} dataKey={t} stackId="a" fill={tierColor[t].fg} isAnimationActive={false} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Tier distribution">
              <Table>
                <thead>
                  <tr>
                    <Th>Tier</Th>
                    <Th className="text-right">Payments</Th>
                    <Th className="text-right">Share</Th>
                    <Th className="w-1/3" />
                  </tr>
                </thead>
                <tbody>
                  {s.tier_distribution.map((t) => {
                    const pct = (t.count / s.totals.payments) * 100
                    return (
                      <Tr key={t.tier}>
                        <Td><TierBadge tier={t.tier} /></Td>
                        <Td className="tabular text-right">{formatInt(t.count)}</Td>
                        <Td className="tabular text-right">{pct < 1 ? pct.toFixed(2) : pct.toFixed(1)}%</Td>
                        <Td>
                          <div className="h-1.5 rounded bg-navy-800">
                            <div className="h-1.5 rounded" style={{ width: `${Math.max(1, pct)}%`, background: tierColor[t.tier].fg }} />
                          </div>
                        </Td>
                      </Tr>
                    )
                  })}
                </tbody>
              </Table>
            </Card>

            <Card title="Scam family breakdown" description="Flagged payments (MEDIUM and above) and soft holds by suspected family.">
              <div className="h-64">
                <ResponsiveContainer>
                  <BarChart data={s.family_breakdown.map((f) => ({ ...f, name: FAMILY_LABEL[f.family] }))} layout="vertical" margin={{ left: 24, right: 8 }}>
                    <CartesianGrid stroke={chart.grid} strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" {...axisProps} />
                    <YAxis type="category" dataKey="name" width={100} {...axisProps} />
                    <Tooltip {...tooltipProps} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="flagged" name="Flagged" fill={chart.primary} isAnimationActive={false} />
                    <Bar dataKey="held" name="Held" fill={tierColor.CRITICAL.fg} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>

            <Card title="Language breakdown">
              <Table>
                <thead>
                  <tr>
                    <Th>Language</Th>
                    <Th className="text-right">Payments</Th>
                    <Th className="text-right">Alerts</Th>
                    <Th className="text-right">Alert rate</Th>
                  </tr>
                </thead>
                <tbody>
                  {s.language_breakdown.map((l) => (
                    <Tr key={l.language}>
                      <Td>{LANGUAGE_LABEL[l.language]}</Td>
                      <Td className="tabular text-right">{formatInt(l.payments)}</Td>
                      <Td className="tabular text-right">{formatInt(l.alerts)}</Td>
                      <Td className="tabular text-right">{formatPct((l.alerts / l.payments) * 100, 2)}</Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            </Card>

            <Card title="Text model usage" description="Primary Hugging Face model vs the TF-IDF + logistic regression fallback.">
              <div className="h-48">
                <ResponsiveContainer>
                  <BarChart data={s.model_usage.map((m) => ({ ...m, name: m.model === 'hf' ? 'Primary (HF)' : 'Fallback (TF-IDF + LR)' }))} layout="vertical" margin={{ left: 40, right: 8 }}>
                    <XAxis type="number" {...axisProps} />
                    <YAxis type="category" dataKey="name" width={140} {...axisProps} />
                    <Tooltip {...tooltipProps} />
                    <Bar dataKey="calls" name="Calls" isAnimationActive={false}>
                      {s.model_usage.map((m) => (
                        <Cell key={m.model} fill={m.model === 'hf' ? chart.primary : chart.secondary} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-2 text-xs text-ink-400">
                {s.model_usage.map((m) => `${m.model === 'hf' ? 'Primary' : 'Fallback'}: ${formatPct((m.calls / s.model_usage.reduce((a, b) => a + b.calls, 0)) * 100)} of calls, p95 ${m.p95_ms} ms`).join(' · ')}
              </p>
            </Card>
          </div>

          <Card title="Fairness by cohort" description="Rows are flagged when the alert rate is more than 1.5× the lowest cohort in the same dimension.">
            <Table>
              <thead>
                <tr>
                  <Th>Dimension</Th>
                  <Th>Cohort</Th>
                  <Th className="text-right">Payments</Th>
                  <Th className="text-right">Alert rate</Th>
                  <Th className="text-right">Precision</Th>
                  <Th className="text-right">Recall</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {s.fairness.map((f) => {
                  const minRate = Math.min(...s.fairness.filter((x) => x.dimension === f.dimension).map((x) => x.alert_rate_pct))
                  const flagged = f.alert_rate_pct > minRate * 1.5
                  return (
                    <Tr key={f.dimension + f.cohort}>
                      <Td className="text-ink-400">{f.dimension === 'language' ? 'Language' : 'Age band'}</Td>
                      <Td>{f.cohort}</Td>
                      <Td className="tabular text-right">{formatInt(f.payments)}</Td>
                      <Td className={cx('tabular text-right', flagged && 'text-tier-high')}>{formatPct(f.alert_rate_pct)}</Td>
                      <Td className="tabular text-right">{f.precision.toFixed(2)}</Td>
                      <Td className="tabular text-right">{f.recall.toFixed(2)}</Td>
                      <Td className="text-xs text-tier-high">{flagged ? 'Review' : ''}</Td>
                    </Tr>
                  )
                })}
              </tbody>
            </Table>
          </Card>
          <p className="text-2xs text-ink-500">All figures are from synthetic data and are not production performance. Generated {new Date(s.generated_at).toLocaleString('en-IN')}.</p>
        </div>
      ) : null}
    </>
  )
}
