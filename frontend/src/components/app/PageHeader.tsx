import { ArrowLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { cn } from '@/lib/utils'

interface PageHeaderProps {
  title: ReactNode
  description?: ReactNode
  /** Shown beside the title, for example a status badge. */
  titleAddon?: ReactNode
  actions?: ReactNode
  /** A back link for detail pages; on wide screens the header's breadcrumb does this job. */
  back?: { to: string; label: string }
  children?: ReactNode
  className?: string
}

/**
 * The top of every application page: the title in Instrument Serif (as on the landing page), one
 * practical line under it, and the page's actions on the right.
 */
export function PageHeader({ title, description, titleAddon, actions, back, children, className }: PageHeaderProps) {
  return (
    <header className={cn('flex flex-col gap-4 pb-7 lg:flex-row lg:items-end lg:justify-between', className)}>
      <div className="min-w-0">
        {back && (
          <Link
            to={back.to}
            className="mb-3 inline-flex items-center gap-1.5 rounded text-[13px] font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 md:hidden"
          >
            <ArrowLeft className="size-3.5" aria-hidden="true" />
            {back.label}
          </Link>
        )}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <h1
            tabIndex={-1}
            className="min-w-0 break-words font-display text-[2.25rem] font-normal leading-[1.05] tracking-[-0.01em] text-foreground outline-none sm:text-[2.75rem]"
          >
            {title}
          </h1>
          {titleAddon}
        </div>
        {description && <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground sm:text-[15px]">{description}</p>}
        {children}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2 lg:shrink-0 lg:justify-end">{actions}</div>}
    </header>
  )
}
