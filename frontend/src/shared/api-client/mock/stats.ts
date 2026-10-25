import { createRng } from '../../lib/rng'
import type { Stats, StatsRange, Tier } from '../types'

/** Seeded synthetic aggregates for the Analysis panel in demo mode. */
export function buildStats(range: StatsRange): Stats {
  const days = range === '7d' ? 7 : 30
  const rng = createRng(days * 7919)
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  const trend = Array.from({ length: days }, (_, i) => {
    const d = new Date(today.getTime() - (days - 1 - i) * 86_400_000)
    const base = 9000 + rng.int(-900, 1200)
    return {
      date: d.toISOString().slice(0, 10),
      LOW: base,
      MEDIUM: Math.round(base * (0.022 + rng.next() * 0.008)),
      HIGH: Math.round(base * (0.006 + rng.next() * 0.003)),
      CRITICAL: Math.round(base * (0.0012 + rng.next() * 0.0008)),
    }
  })

  const sum = (t: Tier) => trend.reduce((s, d) => s + d[t], 0)
  const tiers: Tier[] = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
  const tier_distribution = tiers.map((tier) => ({ tier, count: sum(tier) }))
  const payments = tier_distribution.reduce((s, t) => s + t.count, 0)
  const alerts = payments - sum('LOW')
  const users = Math.round(payments / (days * 0.9))
  const weeks = days / 7

  return {
    range,
    generated_at: new Date().toISOString(),
    synthetic: true,
    totals: {
      payments,
      zero_friction_pct: (sum('LOW') / payments) * 100,
      alerts_per_user_week: alerts / users / weeks,
      holds: sum('CRITICAL'),
      users,
      users_over_budget: Math.round(users * 0.004),
    },
    targets: { zero_friction_pct: 95, alerts_per_user_week: 1 },
    trend,
    tier_distribution,
    family_breakdown: [
      { family: 'kyc_refund', flagged: Math.round(alerts * 0.31), held: Math.round(sum('CRITICAL') * 0.34) },
      { family: 'digital_arrest', flagged: Math.round(alerts * 0.18), held: Math.round(sum('CRITICAL') * 0.29) },
      { family: 'upi_collect', flagged: Math.round(alerts * 0.21), held: Math.round(sum('CRITICAL') * 0.14) },
      { family: 'lottery', flagged: Math.round(alerts * 0.12), held: Math.round(sum('CRITICAL') * 0.1) },
      { family: 'job_task', flagged: Math.round(alerts * 0.11), held: Math.round(sum('CRITICAL') * 0.09) },
      { family: 'unknown', flagged: Math.round(alerts * 0.07), held: Math.round(sum('CRITICAL') * 0.04) },
    ],
    language_breakdown: [
      { language: 'en', payments: Math.round(payments * 0.46), alerts: Math.round(alerts * 0.41) },
      { language: 'hinglish', payments: Math.round(payments * 0.34), alerts: Math.round(alerts * 0.37) },
      { language: 'hi', payments: Math.round(payments * 0.2), alerts: Math.round(alerts * 0.22) },
    ],
    fairness: [
      { dimension: 'language', cohort: 'English', payments: Math.round(payments * 0.46), alert_rate_pct: 3.1, precision: 0.82, recall: 0.79 },
      { dimension: 'language', cohort: 'Hinglish', payments: Math.round(payments * 0.34), alert_rate_pct: 3.6, precision: 0.78, recall: 0.74 },
      { dimension: 'language', cohort: 'Hindi', payments: Math.round(payments * 0.2), alert_rate_pct: 3.8, precision: 0.75, recall: 0.7 },
      { dimension: 'age_band', cohort: '18–29', payments: Math.round(payments * 0.31), alert_rate_pct: 2.7, precision: 0.8, recall: 0.76 },
      { dimension: 'age_band', cohort: '30–49', payments: Math.round(payments * 0.42), alert_rate_pct: 3.2, precision: 0.81, recall: 0.77 },
      { dimension: 'age_band', cohort: '50–64', payments: Math.round(payments * 0.18), alert_rate_pct: 4.1, precision: 0.79, recall: 0.78 },
      { dimension: 'age_band', cohort: '65+', payments: Math.round(payments * 0.09), alert_rate_pct: 5.6, precision: 0.77, recall: 0.81 },
    ],
    model_usage: [
      { model: 'hf', calls: Math.round(alerts * 3.1), p95_ms: 118 },
      { model: 'tfidf_lr', calls: Math.round(alerts * 0.24), p95_ms: 9 },
    ],
    cluster_candidates: [
      {
        cluster_id: 'C-117',
        size: 42,
        first_seen: new Date(Date.now() - 2 * 86_400_000).toISOString(),
        last_seen: new Date(Date.now() - 40 * 60_000).toISOString(),
        languages: ['hinglish', 'en'],
        sample_redacted: 'Electricity connection will be cut tonight. Pay pending bill to officer at [PHONE] turant.',
        top_terms: ['electricity', 'bill', 'tonight', 'officer', 'cut'],
        nearest_known_family: 'kyc_refund',
        distance: 0.61,
      },
      {
        cluster_id: 'C-121',
        size: 17,
        first_seen: new Date(Date.now() - 86_400_000).toISOString(),
        last_seen: new Date(Date.now() - 3 * 3_600_000).toISOString(),
        languages: ['en'],
        sample_redacted: 'Your FASTag is deactivated. Recharge via this link within 2 hours to avoid penalty.',
        top_terms: ['fastag', 'deactivated', 'recharge', 'penalty'],
        nearest_known_family: 'upi_collect',
        distance: 0.57,
      },
      {
        cluster_id: 'C-124',
        size: 9,
        first_seen: new Date(Date.now() - 9 * 3_600_000).toISOString(),
        last_seen: new Date(Date.now() - 50 * 60_000).toISOString(),
        languages: ['hi'],
        sample_redacted: 'आपके बेटे को हिरासत में लिया गया है। छुड़ाने के लिए तुरंत पैसे भेजें।',
        top_terms: ['हिरासत', 'बेटे', 'तुरंत'],
        nearest_known_family: 'digital_arrest',
        distance: 0.48,
      },
    ],
  }
}
