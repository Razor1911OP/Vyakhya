export const palette = {
  navy: {
    950: '#09111F',
    900: '#0C1628',
    850: '#101C33',
    800: '#14223D',
    700: '#1C2D4E',
    600: '#283B61',
    500: '#3A4F78',
  },
  ink: {
    50: '#EEF2F8',
    200: '#C9D2E1',
    300: '#A3AFC4',
    400: '#7D8AA3',
    500: '#5E6B84',
  },
  teal: {
    300: '#6FD3C7',
    400: '#3DBFB0',
    500: '#24A396',
    600: '#1B8379',
    900: '#0F2F33',
  },
  tier: {
    low: '#46A86F',
    lowSoft: '#132E25',
    medium: '#D6A23A',
    mediumSoft: '#302816',
    high: '#E07D3C',
    highSoft: '#33221A',
    critical: '#D9574F',
    criticalSoft: '#35191B',
  },
  info: '#7FA6D6',
  infoSoft: '#16263E',
  white: '#FFFFFF',
  transparent: 'transparent',
} as const

export type TierKey = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'

export const tierColor: Record<TierKey, { fg: string; bg: string }> = {
  LOW: { fg: palette.tier.low, bg: palette.tier.lowSoft },
  MEDIUM: { fg: palette.tier.medium, bg: palette.tier.mediumSoft },
  HIGH: { fg: palette.tier.high, bg: palette.tier.highSoft },
  CRITICAL: { fg: palette.tier.critical, bg: palette.tier.criticalSoft },
}

export const chart = {
  grid: palette.navy[700],
  axis: palette.ink[400],
  primary: palette.teal[400],
  secondary: palette.ink[300],
  muted: palette.navy[500],
  tooltipBg: palette.navy[850],
  tooltipBorder: palette.navy[600],
}
