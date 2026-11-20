import { cn } from '@/lib/utils'

/**
 * Two overlapping circles, a candidate and a job; the filled overlap is the fit.
 * Its colours come from the surface it sits on (--mark-a, --mark-b, --mark-fill).
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" aria-hidden="true" className={cn('size-7', className)}>
      <circle cx="12" cy="16" r="8.5" strokeWidth="2" style={{ stroke: 'var(--mark-a)' }} />
      <circle cx="20" cy="16" r="8.5" strokeWidth="2" style={{ stroke: 'var(--mark-b)' }} />
      <path d="M16 8.5A8.5 8.5 0 0 1 16 23.5A8.5 8.5 0 0 1 16 8.5Z" style={{ fill: 'var(--mark-fill)' }} />
    </svg>
  )
}

export function BrandLogo({ className, size = 'md' }: { className?: string; size?: 'md' | 'lg' }) {
  return (
    <span
      className={cn(
        'inline-flex items-center font-semibold uppercase text-accent-ink',
        size === 'lg' ? 'gap-3 text-lg tracking-[0.22em] sm:text-xl' : 'gap-2.5 text-[15px] tracking-[0.2em]',
        className,
      )}
    >
      <BrandMark className={size === 'lg' ? 'size-9 sm:size-10' : 'size-7'} />
      FITSCAN
    </span>
  )
}
