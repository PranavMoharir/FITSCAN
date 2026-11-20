import type { ReactNode } from 'react'

import { Reveal } from '@/components/landing/Reveal'
import { cn } from '@/lib/utils'

/** A small uppercase label with a short accent rule. */
export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-3 text-[11px] font-semibold uppercase tracking-[0.24em] text-accent-ink', className)}>
      <span aria-hidden="true" className="hidden h-px w-8 bg-accent-solid/60 sm:block" />
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
      <h2 id={id} className="mt-5 font-display text-4xl font-normal leading-[1.04] tracking-[-0.01em] text-balance sm:text-5xl lg:text-6xl">
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

/** Second line of a two-line heading, in the accent colour and italic. */
export function HeadingMuted({ children }: { children: ReactNode }) {
  return <span className="block italic text-accent-ink">{children}</span>
}
