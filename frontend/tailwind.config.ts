import type { Config } from 'tailwindcss'
import { palette } from './src/theme/tokens'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    colors: {
      transparent: palette.transparent,
      current: 'currentColor',
      white: palette.white,
      navy: palette.navy,
      ink: palette.ink,
      teal: palette.teal,
      tier: palette.tier,
      info: { DEFAULT: palette.info, soft: palette.infoSoft },
      // Tailwind preflight uses gray.400 for placeholders.
      gray: { 400: palette.ink[500] },
    },
    extend: {
      fontFamily: {
        sans: ['"Inter Variable"', 'Inter', 'system-ui', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      fontSize: { '2xs': ['0.6875rem', '1rem'] },
    },
  },
  plugins: [],
} satisfies Config
