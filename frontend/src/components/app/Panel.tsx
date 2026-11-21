import type { ReactNode } from 'react'

import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'

interface PanelProps {
  id?: string
  title?: ReactNode
  description?: ReactNode
  action?: ReactNode
  children?: ReactNode
  className?: string
  bodyClassName?: string
}

/** A titled card: the standard container on application pages (shadcn Card underneath). */
export function Panel({ id, title, description, action, children, className, bodyClassName }: PanelProps) {
  const headingId = id ? `${id}-title` : undefined
  return (
    <Card id={id} aria-labelledby={title ? headingId : undefined} className={cn('gap-0 py-0', className)} role={title ? 'region' : undefined}>
      {(title || action) && (
        <div className="flex items-start justify-between gap-4 px-5 pb-3 pt-5">
          <div className="min-w-0">
            {title && (
              <h2 id={headingId} className="text-[15px] font-semibold leading-snug text-foreground">
                {title}
              </h2>
            )}
            {description && <p className="mt-0.5 text-[13px] leading-relaxed text-subtle-foreground">{description}</p>}
          </div>
          {action && <div className="-mr-1.5 -mt-1 flex shrink-0 items-center gap-1">{action}</div>}
        </div>
      )}
      <div className={cn('px-5 pb-5', !(title || action) && 'pt-5', bodyClassName)}>{children}</div>
    </Card>
  )
}
