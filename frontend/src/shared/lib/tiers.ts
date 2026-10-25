import type { Tier } from '../api-client/types'

/** Tier cutoffs (R in [0, 100]). Tuned on synthetic data; re-calibrated at pilot. */
export const TIER_CUTOFFS = { MEDIUM: 40, HIGH: 70, CRITICAL: 85 } as const

export const TIER_RANGE: Record<Tier, string> = {
  LOW: '0–39',
  MEDIUM: '40–69',
  HIGH: '70–84',
  CRITICAL: '85–100',
}

export const TIER_BEHAVIOUR: Record<Tier, string> = {
  LOW: 'Silent allow, logged only',
  MEDIUM: 'One inline nudge, one-tap proceed',
  HIGH: 'Named-reason friction with a 30-second wait',
  CRITICAL: 'Reversible soft-hold before debit, analyst review',
}

/** `widenBy` lowers every cutoff: a missing signal widens the review band, never lowers R. */
export function tierFor(r: number, widenBy = 0): Tier {
  if (r >= TIER_CUTOFFS.CRITICAL - widenBy) return 'CRITICAL'
  if (r >= TIER_CUTOFFS.HIGH - widenBy) return 'HIGH'
  if (r >= TIER_CUTOFFS.MEDIUM - widenBy) return 'MEDIUM'
  return 'LOW'
}
