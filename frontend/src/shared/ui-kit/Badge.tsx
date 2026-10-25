import type { ReactNode } from 'react'
import type { Tier } from '../api-client/types'
import { cx } from './cx'

type Tone = 'neutral' | 'accent' | 'info' | 'low' | 'medium' | 'high' | 'critical'

const TONE: Record<Tone, string> = {
  neutral: 'border-navy-600 bg-navy-800 text-ink-200',
  accent: 'border-teal-600/60 bg-teal-900 text-teal-300',
  info: 'border-info/40 bg-info-soft text-info',
  low: 'border-tier-low/40 bg-tier-lowSoft text-tier-low',
  medium: 'border-tier-medium/40 bg-tier-mediumSoft text-tier-medium',
  high: 'border-tier-high/40 bg-tier-highSoft text-tier-high',
  critical: 'border-tier-critical/50 bg-tier-criticalSoft text-tier-critical',
}

export function Badge({ tone = 'neutral', children, title, className }: { tone?: Tone; children: ReactNode; title?: string; className?: string }) {
  return (
    <span
      title={title}
      className={cx('inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-0.5 text-2xs font-medium', TONE[tone], className)}
    >
      {children}
    </span>
  )
}

export const TIER_TONE: Record<Tier, Tone> = { LOW: 'low', MEDIUM: 'medium', HIGH: 'high', CRITICAL: 'critical' }

export function TierBadge({ tier, className }: { tier: Tier; className?: string }) {
  return (
    <Badge tone={TIER_TONE[tier]} className={cx('font-semibold tracking-wide', className)}>
      {tier}
    </Badge>
  )
}

export type Label = 'SYNTHETIC' | 'SIMULATED' | 'BUILT' | 'ROADMAP' | 'PLACEHOLDER'

const LABEL_INFO: Record<Label, { tone: Tone; title: string }> = {
  SYNTHETIC: { tone: 'info', title: 'Measured on synthetic data. Not production performance.' },
  SIMULATED: { tone: 'medium', title: 'Signal is simulated in this prototype, not read from a real device or network.' },
  BUILT: { tone: 'accent', title: 'Implemented and working in this build.' },
  ROADMAP: { tone: 'neutral', title: 'Planned. Not part of this build.' },
  PLACEHOLDER: { tone: 'high', title: 'Placeholder numbers for UI development, not a measured result.' },
}

export function LabelBadge({ label, className }: { label: Label; className?: string }) {
  const info = LABEL_INFO[label]
  return (
    <Badge tone={info.tone} title={info.title} className={cx('uppercase tracking-wider', className)}>
      {label}
    </Badge>
  )
}
