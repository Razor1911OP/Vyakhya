import { chart, palette } from '../../theme/tokens'

export const tooltipProps = {
  contentStyle: {
    background: chart.tooltipBg,
    border: `1px solid ${chart.tooltipBorder}`,
    borderRadius: 6,
    fontSize: 12,
    color: palette.ink[50],
  },
  labelStyle: { color: palette.ink[300], marginBottom: 4 },
  itemStyle: { padding: 0 },
  cursor: { fill: 'rgba(58, 79, 120, 0.25)' },
} as const

export const axisProps = {
  stroke: chart.axis,
  tick: { fill: chart.axis, fontSize: 11 },
  tickLine: false,
  axisLine: { stroke: chart.grid },
} as const
