import type { ReactNode } from 'react'

import { Reveal } from '@/components/landing/Reveal'
import { cn } from '@/lib/utils'

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 rounded-full border border-brand/25 bg-brand/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-brand-soft',
        className,
      )}
    >
      {children}
    </span>
  )
}

interface SectionHeadingProps {
  eyebrow: string
  title: ReactNode
  description?: ReactNode
  align?: 'left' | 'center'
  /** Id of the heading, for the section's aria-labelledby. */
  id: string
  className?: string
}

export function SectionHeading({ eyebrow, title, description, align = 'left', id, className }: SectionHeadingProps) {
  return (
    <Reveal className={cn(align === 'center' && 'mx-auto text-center', 'max-w-3xl', className)}>
      <Eyebrow>{eyebrow}</Eyebrow>
      <h2 id={id} className="mt-5 text-3xl font-semibold leading-[1.08] tracking-[-0.035em] text-balance sm:text-4xl lg:text-5xl">
        {title}
      </h2>
      {description && (
        <p className={cn('mt-5 text-base leading-relaxed text-muted-foreground sm:text-lg', align === 'center' ? 'mx-auto max-w-2xl' : 'max-w-xl')}>
          {description}
        </p>
      )}
    </Reveal>
  )
}

/** Muted second line of a two-line heading. */
export function HeadingMuted({ children }: { children: ReactNode }) {
  return <span className="block text-muted-foreground">{children}</span>
}
