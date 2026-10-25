import { TIER_CUTOFFS, tierFor } from '../../lib/tiers'
import { FAMILY_LABEL } from '../../lib/format'
import type {
  ContextSignals,
  Language,
  ReasonCode,
  ScamFamily,
  ScoreRequest,
  SignalKey,
  Tier,
} from '../types'

/**
 * Deterministic stand-in for the backend detection pipeline, so the frontend can be
 * demoed without the API. It is a points model, NOT the trained fusion model.
 */

export const TYPICAL_AMOUNT = 1200

type ScoredFamily = Exclude<ScamFamily, 'benign' | 'unknown'>

const FAMILY_CUES: Record<ScoredFamily, RegExp[]> = {
  kyc_refund: [/\bkyc\b/i, /expire/i, /\brefund/i, /blocked|band ho/i, /\bpan\b|aadhaar/i, /केवाईसी/, /खाता बंद/, /रिफंड/],
  digital_arrest: [/\bcbi\b|police|customs|cyber cell/i, /arrest|giraftar/i, /narcotic|drugs|parcel/i, /video call/i, /warrant|court/i, /गिरफ्तार/, /पुलिस/, /पार्सल/],
  lottery: [/lottery/i, /\bwon\b|jeet/i, /prize|lucky draw|\bkbc\b/i, /processing fee|claim/i, /इनाम|लॉटरी/],
  upi_collect: [/collect request/i, /approve/i, /upi pin|pin daalo|enter (your )?pin/i, /receive (the )?money|paise receive/i],
  job_task: [/part[- ]time|ghar baithe/i, /\btask/i, /daily|kamai/i, /commission|rating videos|like videos/i, /prepaid|recharge task/i],
}

const URGENCY = /immediately|urgent|today|now\b|turant|abhi|तुरंत|within 24/i

const FAMILY_HINT: Record<ScoredFamily, string> = {
  kyc_refund: 'asks you to update KYC or claim a refund',
  digital_arrest: 'claims to be police, CBI or customs and threatens arrest',
  lottery: 'says you have won a prize and must pay a fee',
  upi_collect: 'asks you to approve a request or enter your PIN to receive money',
  job_task: 'offers paid online tasks that need an upfront payment',
}

export interface TextAnalysis {
  family: ScamFamily
  language: Language
  strength: 0 | 1 | 2
}

export function detectLanguage(text: string): Language {
  if (/[\u0900-\u097F]/.test(text)) return 'hi'
  if (/\b(hai|karo|aapka|aapne|nahi|kijiye|paise|turant|abhi|raho|bhejo|ho gaya|jayega|bhai)\b/i.test(text)) return 'hinglish'
  return 'en'
}

export function analyseText(text: string | undefined): TextAnalysis | null {
  if (!text || !text.trim()) return null
  const language = detectLanguage(text)
  let best: ScoredFamily | null = null
  let bestHits = 0
  for (const [family, cues] of Object.entries(FAMILY_CUES) as [ScoredFamily, RegExp[]][]) {
    const hits = cues.filter((c) => c.test(text)).length
    if (hits > bestHits) {
      best = family
      bestHits = hits
    }
  }
  if (!best) return { family: 'benign', language, strength: 0 }
  const total = bestHits + (URGENCY.test(text) ? 1 : 0)
  return { family: best, language, strength: total >= 2 ? 2 : 1 }
}

interface Contribution {
  points: number
  reason: ReasonCode
}

const SIGNAL_POINTS: Record<SignalKey, Contribution> = {
  call_in_progress: { points: 15, reason: { code: 'CALL_ACTIVE', text: 'You are on a phone call while making this payment. Scammers often guide victims over a call.' } },
  screen_share: { points: 14, reason: { code: 'SCREEN_SHARE', text: 'Your screen is being shared, so someone else may be able to see your banking details.' } },
  fresh_payee: { points: 10, reason: { code: 'FRESH_PAYEE', text: 'This is your first payment to this payee.' } },
  new_device: { points: 8, reason: { code: 'NEW_DEVICE', text: 'This payment is being made from a device you have not used before.' } },
  new_location: { points: 6, reason: { code: 'NEW_LOCATION', text: 'This payment is being made from a location that is unusual for you.' } },
  odd_hour: { points: 4, reason: { code: 'ODD_HOUR', text: 'This payment is at an hour when you rarely make payments.' } },
}

function amountPoints(ratio: number): number {
  if (ratio < 2) return 0
  if (ratio < 5) return 3
  if (ratio < 20) return 6
  if (ratio < 50) return 10
  return 14
}

export interface EngineResult {
  r: number
  tier: Tier
  reason_codes: ReasonCode[]
  soft_hold: boolean
  missing_signals: SignalKey[]
  review_band_widened: boolean
  family_guess: ScamFamily
  language?: Language
}

export function scoreRequest(req: ScoreRequest, typicalAmount = TYPICAL_AMOUNT): EngineResult {
  const s: ContextSignals = req.signals
  const parts: Contribution[] = [{ points: 3, reason: { code: 'BASELINE', text: '' } }]

  const text = analyseText(req.message?.redacted_text)
  if (text && text.strength > 0 && text.family !== 'benign' && text.family !== 'unknown') {
    parts.push({
      points: text.strength === 2 ? 22 : 10,
      reason: {
        code: `TEXT_${text.family.toUpperCase()}`,
        text: `The forwarded message reads like a known ${FAMILY_LABEL[text.family]} scam: it ${FAMILY_HINT[text.family]}.`,
      },
    })
  }

  const missing: SignalKey[] = []
  for (const key of Object.keys(SIGNAL_POINTS) as SignalKey[]) {
    if (s[key] === null) missing.push(key)
    else if (s[key]) parts.push(SIGNAL_POINTS[key])
  }

  if (s.call_in_progress && s.screen_share) {
    parts.push({ points: 12, reason: { code: 'GUIDED_SESSION', text: 'A call and screen sharing are both active, which is how callers usually direct a victim through a payment.' } })
  }

  const ratio = req.amount / typicalAmount
  const ap = amountPoints(ratio)
  if (ap > 0) {
    parts.push({ points: ap, reason: { code: 'AMOUNT_UNUSUAL', text: `This amount is about ${Math.round(ratio)}× your usual payment.` } })
  }
  if (s.call_in_progress && s.fresh_payee && ratio >= 20) {
    parts.push({ points: 4, reason: { code: 'COACHED_TRANSFER', text: 'A large first payment to a new payee is being made during an active call.' } })
  }

  const r = Math.max(0, Math.min(100, parts.reduce((sum, p) => sum + p.points, 0)))
  const widenBy = Math.min(10, missing.length * 5)
  let tier = tierFor(r, widenBy)

  const reasons = parts
    .filter((p) => p.reason.code !== 'BASELINE')
    .sort((a, b) => b.points - a.points)
    .map((p) => p.reason)

  if (missing.length > 0) {
    reasons.push({
      code: 'MISSING_SIGNALS',
      text: `Some signals could not be read (${missing.length}). We review such payments more carefully; a missing signal never lowers the risk.`,
    })
  }
  if (req.trusted_payee && tier === 'MEDIUM') {
    tier = 'LOW'
    reasons.push({ code: 'TRUSTED_PAYEE', text: 'You have paid this payee before, so we did not warn you again.' })
  }

  return {
    r,
    tier,
    reason_codes: reasons,
    soft_hold: tier === 'CRITICAL',
    missing_signals: missing,
    review_band_widened: widenBy > 0 && tierFor(r, widenBy) !== tierFor(r, 0),
    family_guess: text?.family ?? 'unknown',
    language: text?.language,
  }
}

export { TIER_CUTOFFS }
