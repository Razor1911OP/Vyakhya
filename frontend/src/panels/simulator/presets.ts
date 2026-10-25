import type { ContextSignals } from '../../shared/api-client/types'
import { COACHED_VICTIM_MESSAGE } from '../../shared/api-client/mock/samples'

export interface PaymentForm {
  payee_vpa: string
  amount: string
  note: string
  message: string
  consent: boolean
  trusted_payee: boolean
  signals: ContextSignals
}

export const NO_SIGNALS: ContextSignals = {
  call_in_progress: false,
  screen_share: false,
  new_device: false,
  new_location: false,
  fresh_payee: false,
  odd_hour: false,
}

export const EMPTY_FORM: PaymentForm = {
  payee_vpa: '',
  amount: '',
  note: '',
  message: '',
  consent: false,
  trusted_payee: false,
  signals: NO_SIGNALS,
}

export interface Preset {
  id: 'grocery' | 'trusted' | 'coached'
  title: string
  summary: string
  form: PaymentForm
}

export const PRESETS: Preset[] = [
  {
    id: 'grocery',
    title: 'Grocery payment',
    summary: 'Small payment to a regular shop. Expected: LOW, no friction.',
    form: { ...EMPTY_FORM, payee_vpa: 'freshmart.kirana@okaxis', amount: '450', note: 'Groceries', trusted_payee: true },
  },
  {
    id: 'trusted',
    title: 'Transfer to a saved payee',
    summary: 'Larger transfer to family. Trusted-payee suppression applies.',
    form: { ...EMPTY_FORM, payee_vpa: 'meena.sharma@oksbi', amount: '8000', note: 'Rent share', trusted_payee: true },
  },
  {
    id: 'coached',
    title: 'Coached-victim trace',
    summary: 'A caller guides the victim over two minutes. Expected: HOLD before debit.',
    form: { ...EMPTY_FORM, payee_vpa: 'my.savings@oksbi', amount: '500', signals: { ...NO_SIGNALS, call_in_progress: true } },
  },
]

export interface TraceStep {
  t: number
  narrative: string
  form: PaymentForm
}

const base = PRESETS[2].form
const withMessage: PaymentForm = { ...base, message: COACHED_VICTIM_MESSAGE, consent: true }
const withShare: PaymentForm = { ...withMessage, signals: { ...withMessage.signals, screen_share: true } }
const newPayee: PaymentForm = {
  ...withShare,
  payee_vpa: 'kyc.secure.desk@ybl',
  amount: '15000',
  note: 'KYC verification',
  signals: { ...withShare.signals, fresh_payee: true },
}

/** Deck reference trace: R = 18 → 40 → 66 → 82 → 90 over T+0s … T+120s. */
export const COACHED_TRACE: TraceStep[] = [
  { t: 0, narrative: 'A caller posing as bank staff asks for a ₹500 "test" payment to a saved account.', form: base },
  { t: 30, narrative: 'The victim forwards the caller\'s "KYC expired" SMS for checking.', form: withMessage },
  { t: 60, narrative: 'The caller asks the victim to share their screen "to help".', form: withShare },
  { t: 90, narrative: 'The caller dictates a new payee and raises the amount to ₹15,000.', form: newPayee },
  { t: 120, narrative: 'The caller pushes for ₹49,999 "to secure the account".', form: { ...newPayee, amount: '49999' } },
]


/**
 * Live-API version of the coached-victim trace (the deck numbers 18→40→66→82→90 come from the mock
 * engine and are not what the evaluated engine produces). Same story, with two changes so it is
 * realistic for the frozen engine:
 *  - T+0 is a payment to the victim's own saved account (marked as a saved payee).
 *  - T+120 adds the caller's final instruction: "to get the held refund back, approve the collect
 *    request and enter your UPI PIN". Receiving money never needs a PIN, so the hard rule fires (CRITICAL).
 * R values are whatever the engine returns; nothing here is tuned to hit target numbers.
 */
export const LIVE_FINAL_INSTRUCTION =
  'Sir, your refund of Rs 49,999 is on hold for security. To receive it back safely, approve the collect request and enter your UPI PIN now.'
const liveBase: PaymentForm = { ...base, trusted_payee: true, note: 'Test payment' }
const liveMessage: PaymentForm = { ...liveBase, message: COACHED_VICTIM_MESSAGE, consent: true }
const liveShare: PaymentForm = { ...liveMessage, signals: { ...liveMessage.signals, screen_share: true } }
const liveNewPayee: PaymentForm = {
  ...liveShare,
  trusted_payee: false,
  payee_vpa: 'kyc.secure.desk@ybl',
  amount: '15000',
  note: 'KYC verification',
  signals: { ...liveShare.signals, fresh_payee: true },
}

export const LIVE_COACHED_TRACE: TraceStep[] = [
  { t: 0, narrative: 'A caller posing as bank staff asks for a ₹500 "test" payment to the victim\'s own saved account.', form: liveBase },
  { t: 30, narrative: 'The victim forwards the caller\'s "KYC expired" SMS for checking.', form: liveMessage },
  { t: 60, narrative: 'The caller asks the victim to share their screen "to help" (simulated signal, shown but not scored).', form: liveShare },
  { t: 90, narrative: 'The caller dictates a new payee and raises the amount to ₹15,000.', form: liveNewPayee },
  {
    t: 120,
    narrative: 'The caller pushes ₹49,999 and says: "approve the collect request and enter your UPI PIN to get the refund back".',
    form: { ...liveNewPayee, amount: '49999', message: `${COACHED_VICTIM_MESSAGE}\n${LIVE_FINAL_INSTRUCTION}` },
  },
]
