import { useId } from 'react'

import { cn } from '@/lib/utils'

/** Two overlapping circles, a candidate and a job; the filled overlap is the fit. */
export function BrandMark({ className }: { className?: string }) {
  const gradient = `fitscan-mark-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`
  return (
    <svg viewBox="0 0 32 32" fill="none" aria-hidden="true" className={cn('size-7', className)}>
      <defs>
        <linearGradient id={gradient} x1="12" y1="9" x2="20" y2="23" gradientUnits="userSpaceOnUse">
          <stop stopColor="#a594ff" />
          <stop offset="1" stopColor="#5b7cff" />
        </linearGradient>
      </defs>
      <circle cx="12" cy="16" r="8.5" stroke="#a594ff" strokeWidth="2" />
      <circle cx="20" cy="16" r="8.5" stroke="#5b7cff" strokeWidth="2" />
      <path d="M16 8.5A8.5 8.5 0 0 1 16 23.5A8.5 8.5 0 0 1 16 8.5Z" fill={`url(#${gradient})`} />
    </svg>
  )
}

export function BrandLogo({ className }: { className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2.5 text-[15px] font-semibold tracking-[0.02em] text-foreground', className)}>
      <BrandMark />
      FITSCAN
    </span>
  )
}
