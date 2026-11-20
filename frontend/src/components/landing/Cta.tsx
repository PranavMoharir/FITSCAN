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

/** Pill-shaped call to action built on the shadcn Button. */
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
        'group/cta rounded-full font-semibold transition-[background-color,box-shadow,transform] duration-300 ease-out',
        size === 'md' ? 'h-11 gap-2 px-5 text-sm has-data-[icon=inline-end]:pr-4' : 'h-9 gap-1.5 px-4 text-sm',
        variant === 'primary'
          ? 'shadow-[inset_0_0_0_1px_rgb(255_255_255/0.14),0_10px_32px_-12px_rgb(124_92_255/0.8)] hover:bg-[#7856ff] hover:shadow-[inset_0_0_0_1px_rgb(255_255_255/0.2),0_14px_40px_-12px_rgb(124_92_255/0.95)]'
          : 'border-white/12 bg-white/[0.03] text-foreground shadow-none hover:bg-white/[0.08] hover:text-foreground',
        className,
      )}
    >
      {to ? <Link to={to}>{content}</Link> : <a href={href}>{content}</a>}
    </Button>
  )
}
