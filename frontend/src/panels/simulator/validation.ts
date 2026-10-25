import type { PaymentForm } from './presets'

export const MAX_AMOUNT = 100_000
export const MAX_MESSAGE = 2000
const VPA = /^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$/

export type FormErrors = Partial<Record<'payee_vpa' | 'amount' | 'message', string>>

export function validate(form: PaymentForm): FormErrors {
  const errors: FormErrors = {}
  if (!VPA.test(form.payee_vpa.trim())) errors.payee_vpa = 'Enter a UPI ID like name@bank.'
  const amount = Number(form.amount)
  if (!form.amount || !Number.isFinite(amount) || amount <= 0) errors.amount = 'Enter an amount greater than zero.'
  else if (amount > MAX_AMOUNT) errors.amount = `UPI payments are limited to ₹${MAX_AMOUNT.toLocaleString('en-IN')} here.`
  if (form.message.length > MAX_MESSAGE) errors.message = `Keep the message under ${MAX_MESSAGE} characters.`
  return errors
}
