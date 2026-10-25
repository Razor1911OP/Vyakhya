export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden className="shrink-0">
      <rect width="32" height="32" rx="7" className="fill-navy-800" />
      <path d="M16 5l9 3.5v6.8c0 5.6-3.8 10-9 11.7-5.2-1.7-9-6.1-9-11.7V8.5L16 5z" fill="none" className="stroke-teal-400" strokeWidth="2" />
      <path d="M11.5 12l4.5 9 4.5-9" fill="none" className="stroke-ink-50" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
