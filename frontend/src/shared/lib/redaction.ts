export type RedactionKind = 'OTP' | 'PHONE' | 'CARD' | 'ACCOUNT'

export interface RedactionSpan {
  start: number
  end: number
  kind: RedactionKind
}

export interface RedactionResult {
  redacted: string
  spans: RedactionSpan[]
  counts: Record<RedactionKind, number>
}

const DEVANAGARI_DIGITS = '०१२३४५६७८९'
const OTP_CONTEXT = /(otp|o\.t\.p|one[\s-]?time|passcode|pass code|code|pin|verification|ओटीपी|कोड|पिन)\W{0,12}$/i
const MONEY_CONTEXT = /(rs\.?|inr|₹|रु\.?|rupees?)\s*$/i

/** Map Devanagari digits to ASCII; one UTF-16 unit each, so offsets are preserved. */
export function normaliseDigits(text: string): string {
  return text.replace(/[०-९]/g, (d) => String(DEVANAGARI_DIGITS.indexOf(d)))
}

function luhn(digits: string): boolean {
  let sum = 0
  let double = false
  for (let i = digits.length - 1; i >= 0; i--) {
    let n = Number(digits[i])
    if (double) {
      n *= 2
      if (n > 9) n -= 9
    }
    sum += n
    double = !double
  }
  return sum % 10 === 0
}

function classify(digits: string, raw: string, before: string): RedactionKind | null {
  const len = digits.length
  const hasCountryCode = /^\+?\s*91/.test(raw.trim()) && len === 12
  if (len >= 4 && len <= 8 && OTP_CONTEXT.test(before)) return 'OTP'
  if (len === 6 && !MONEY_CONTEXT.test(before)) return 'OTP'
  if (hasCountryCode || (len === 10 && /^[6-9]/.test(digits))) return 'PHONE'
  if (len >= 13 && len <= 19 && (luhn(digits) || len === 16)) return 'CARD'
  if (len >= 9 && len <= 18) return 'ACCOUNT'
  return null
}

/**
 * Masks OTP, phone, card and account numbers. Tolerates digits split by spaces,
 * dots or dashes (a common evasion trick) and Devanagari numerals.
 */
export function redact(input: string): RedactionResult {
  const text = normaliseDigits(input)
  const pattern = /\+?\d(?:[\s.-]{0,2}\d){3,22}/g
  const spans: RedactionSpan[] = []
  let match: RegExpExecArray | null
  while ((match = pattern.exec(text)) !== null) {
    const raw = match[0]
    const digits = raw.replace(/\D/g, '')
    const before = text.slice(Math.max(0, match.index - 24), match.index)
    const kind = classify(digits, raw, before)
    if (kind) spans.push({ start: match.index, end: match.index + raw.length, kind })
  }

  let redacted = ''
  let cursor = 0
  const counts: Record<RedactionKind, number> = { OTP: 0, PHONE: 0, CARD: 0, ACCOUNT: 0 }
  for (const span of spans) {
    redacted += input.slice(cursor, span.start) + `[${span.kind}]`
    cursor = span.end
    counts[span.kind] += 1
  }
  redacted += input.slice(cursor)
  return { redacted, spans, counts }
}

/** Splits the original text into plain and masked segments for the preview. */
export function redactionSegments(input: string, spans: RedactionSpan[]) {
  const out: Array<{ text: string; kind?: RedactionKind }> = []
  let cursor = 0
  for (const s of spans) {
    if (s.start > cursor) out.push({ text: input.slice(cursor, s.start) })
    out.push({ text: input.slice(s.start, s.end), kind: s.kind })
    cursor = s.end
  }
  if (cursor < input.length) out.push({ text: input.slice(cursor) })
  return out
}

export function maskVpa(vpa: string): string {
  const [local, handle] = vpa.split('@')
  if (!handle) return '••••'
  const visible = local.slice(0, 2)
  return `${visible}${'•'.repeat(Math.max(2, Math.min(6, local.length - 2)))}@${handle}`
}
