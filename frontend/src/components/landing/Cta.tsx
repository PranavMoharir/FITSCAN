import { ArrowRight } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface CtaProps {
  children: ReactNode
  /** Router path inside the app, for example "/app". */
  to?: string
  /** Section anchor or external address. */
  href?: string
  variant?: 'primary' | 'secondary'
  size?: 'md' | 'sm'
  arrow?: boolean
  className?: string
}

/**
 * Pill-shaped call to action built on the shadcn Button. Its colours come from the surface:
 * burgundy with cream text on cream, cream with dark text on black or burgundy.
 */
export function Cta({ children, to, href, variant = 'primary', size = 'md', arrow = false, className }: CtaProps) {
  const content = (
    <>
      {children}
      {arrow && <ArrowRight aria-hidden="true" className="transition-transform duration-300 ease-out group-hover/cta:translate-x-1" />}
    </>
  )
  return (
    <Button
      asChild
      variant={variant === 'primary' ? 'default' : 'outline'}
      className={cn(
        'group/cta rounded-full font-medium shadow-none transition-[background-color,border-color,color,translate] duration-300 ease-out hover:-translate-y-px',
        size === 'md' ? 'h-11 gap-2 px-6 text-sm' : 'h-9 gap-1.5 px-4 text-sm',
        variant === 'primary'
          ? 'bg-primary text-primary-foreground hover:bg-primary-hover'
          : 'border-foreground/25 bg-transparent text-foreground hover:border-foreground/45 hover:bg-foreground/[0.04] hover:text-foreground',
        className,
      )}
    >
      {to ? <Link to={to}>{content}</Link> : <a href={href}>{content}</a>}
    </Button>
  )
}
