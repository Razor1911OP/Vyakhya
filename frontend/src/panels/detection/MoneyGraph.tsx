import type { Case } from '../../shared/api-client/types'
import { formatINR } from '../../shared/lib/format'

const COL_X = { victim: 40, payee: 170, mule: 300, merchant: 300 }

export function MoneyGraph({ graph }: { graph: Case['money_graph'] }) {
  const mules = graph.nodes.filter((n) => n.kind === 'mule' || n.kind === 'merchant')
  const height = Math.max(110, mules.length * 40 + 30)
  const pos = new Map<string, { x: number; y: number }>()
  graph.nodes.forEach((n) => {
    if (n.kind === 'victim' || n.kind === 'payee') pos.set(n.id, { x: COL_X[n.kind], y: height / 2 })
  })
  mules.forEach((n, i) => pos.set(n.id, { x: COL_X.mule, y: (height / (mules.length + 1)) * (i + 1) }))

  return (
    <svg viewBox={`0 0 360 ${height}`} className="w-full" role="img" aria-label="Money flow from payer through payee to downstream accounts">
      {graph.edges.map((e) => {
        const a = pos.get(e.from)
        const b = pos.get(e.to)
        if (!a || !b) return null
        return (
          <g key={`${e.from}-${e.to}`}>
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="stroke-navy-500" strokeWidth={1.5} />
            <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 5} textAnchor="middle" className="fill-ink-400 text-[9px]">
              {formatINR(e.amount)}
            </text>
          </g>
        )
      })}
      {graph.nodes.map((n) => {
        const p = pos.get(n.id)!
        const cls = n.kind === 'victim' ? 'fill-teal-900 stroke-teal-400' : n.kind === 'payee' ? 'fill-tier-highSoft stroke-tier-high' : 'fill-tier-criticalSoft stroke-tier-critical'
        return (
          <g key={n.id}>
            <circle cx={p.x} cy={p.y} r={9} className={cls} strokeWidth={1.5} />
            <text x={p.x} y={p.y + 22} textAnchor="middle" className="fill-ink-200 text-[9px]">
              {n.label}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
