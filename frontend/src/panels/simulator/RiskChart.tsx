import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Tier } from '../../shared/api-client/types'
import { TIER_CUTOFFS } from '../../shared/lib/tiers'
import { axisProps, EmptyState, tooltipProps } from '../../shared/ui-kit'
import { chart, tierColor } from '../../theme/tokens'

export interface RiskPoint {
  label: string
  r: number
  tier: Tier
}

/** CRITICAL in the live engine = any hard-rule hit, which floors R at 90. */
const HARD_RULE_FLOOR = 90

export interface Cutoffs {
  MEDIUM: number
  HIGH: number
  CRITICAL: number
}

/** Mock API: fixed deck cutoffs. Live API: the engine's band cutoffs for the latest decision. */
export function cutoffsFrom(live?: { medium: number; high: number }): Cutoffs {
  return live ? { MEDIUM: Math.round(live.medium), HIGH: Math.round(live.high), CRITICAL: HARD_RULE_FLOOR } : { ...TIER_CUTOFFS }
}

export function RiskChart({ points, cutoffs = cutoffsFrom() }: { points: RiskPoint[]; cutoffs?: Cutoffs }) {
  if (points.length === 0) {
    return <EmptyState title="No checks yet">Each check in this session is plotted here against the tier thresholds.</EmptyState>
  }
  const bands: Array<{ tier: Tier; y1: number; y2: number }> = [
    { tier: 'LOW', y1: 0, y2: cutoffs.MEDIUM },
    { tier: 'MEDIUM', y1: cutoffs.MEDIUM, y2: cutoffs.HIGH },
    { tier: 'HIGH', y1: cutoffs.HIGH, y2: cutoffs.CRITICAL },
    { tier: 'CRITICAL', y1: cutoffs.CRITICAL, y2: 100 },
  ]
  return (
    <div className="h-64" role="img" aria-label={`Risk score over time: ${points.map((p) => `${p.label} R ${p.r}`).join(', ')}`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 84, bottom: 0, left: -16 }}>
          {bands.map((b) => (
            <ReferenceArea key={b.tier} y1={b.y1} y2={b.y2} fill={tierColor[b.tier].fg} fillOpacity={0.06} stroke="none" ifOverflow="hidden" />
          ))}
          <CartesianGrid stroke={chart.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" {...axisProps} />
          <YAxis domain={[0, 100]} ticks={[0, cutoffs.MEDIUM, cutoffs.HIGH, cutoffs.CRITICAL, 100]} {...axisProps} />
          {(['MEDIUM', 'HIGH', 'CRITICAL'] as const).map((t) => (
            <ReferenceLine
              key={t}
              y={cutoffs[t]}
              stroke={tierColor[t].fg}
              strokeDasharray="4 4"
              strokeOpacity={0.7}
              label={{ value: `${t} ${cutoffs[t]}`, position: 'right', fill: tierColor[t].fg, fontSize: 10 }}
            />
          ))}
          <Tooltip {...tooltipProps} formatter={(v) => [`R ${v}`, 'Risk']} />
          <Line
            type="monotone"
            dataKey="r"
            stroke={chart.primary}
            strokeWidth={2}
            isAnimationActive={false}
            dot={(p) => {
              const point = p.payload as RiskPoint
              return <circle key={`${p.index}`} cx={p.cx} cy={p.cy} r={4.5} fill={tierColor[point.tier].fg} stroke={chart.tooltipBg} strokeWidth={2} />
            }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
