import type { Language, ScamFamily, SignalKey } from '../api-client/types'

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const int = new Intl.NumberFormat('en-IN')

export const formatINR = (n: number) => inr.format(n)
export const formatInt = (n: number) => int.format(n)
export const formatPct = (n: number, digits = 1) => `${n.toFixed(digits)}%`
export const formatRatio = (n: number, digits = 2) => n.toFixed(digits)

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

export function formatCountdown(ms: number): string {
  if (ms <= 0) return '00:00'
  const total = Math.floor(ms / 1000)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export const FAMILY_LABEL: Record<ScamFamily, string> = {
  kyc_refund: 'KYC / refund',
  digital_arrest: 'Digital arrest',
  lottery: 'Lottery / prize',
  upi_collect: 'UPI collect',
  job_task: 'Job / task',
  benign: 'Benign',
  unknown: 'Unclassified',
}

export const LANGUAGE_LABEL: Record<Language, string> = {
  en: 'English',
  hi: 'Hindi',
  hinglish: 'Hinglish',
}

export const SIGNAL_LABEL: Record<SignalKey, string> = {
  call_in_progress: 'Call in progress',
  screen_share: 'Screen sharing on',
  new_device: 'New device',
  new_location: 'New location',
  fresh_payee: 'First payment to this payee',
  odd_hour: 'Unusual hour',
}
