import { Ban, Check, Clock3, FileText, Radar, Target, TriangleAlert, type LucideIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { STATUS_LABEL } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { BackgroundJobStatus, BackgroundJobType } from '@/types/api'

const STATUS_STYLE: Record<BackgroundJobStatus, { icon?: LucideIcon; className: string }> = {
  queued: { icon: Clock3, className: 'border-foreground/20 bg-transparent text-muted-foreground' },
  running: { className: 'border-transparent bg-primary text-primary-foreground' },
  completed: { icon: Check, className: 'border-transparent bg-foreground/[0.07] text-foreground' },
  failed: { icon: TriangleAlert, className: 'border-destructive/25 bg-destructive/10 text-destructive' },
  cancelled: { icon: Ban, className: 'border-dashed border-foreground/30 bg-transparent text-subtle-foreground' },
}

/** A small live dot; it stops pulsing when "reduce motion" is on. */
export function PulseDot({ className }: { className?: string }) {
  return (
    <span className={cn('relative flex size-2 shrink-0', className)} aria-hidden="true">
      <span className="absolute inline-flex size-full animate-ping rounded-full bg-current opacity-60" />
      <span className="relative inline-flex size-2 rounded-full bg-current" />
    </span>
  )
}

/** Background job status: an icon and a word, so the state never depends on colour alone. */
export function StatusBadge({ status, className }: { status: BackgroundJobStatus; className?: string }) {
  const style = STATUS_STYLE[status]
  const Icon = style.icon
  return (
    <Badge variant="outline" className={cn('h-6 gap-1.5 px-2.5 text-xs font-medium', style.className, className)}>
      {Icon ? <Icon className="size-3.5!" aria-hidden="true" /> : <PulseDot />}
      {STATUS_LABEL[status]}
    </Badge>
  )
}

const TYPE_ICON: Record<BackgroundJobType, LucideIcon> = { crawl: Radar, resume: FileText, match: Target }

/** The icon of a background job type, in a soft circle (the same icons as the landing page). */
export function JobTypeIcon({ type, className }: { type: BackgroundJobType; className?: string }) {
  const Icon = TYPE_ICON[type]
  return (
    <span className={cn('grid size-9 shrink-0 place-items-center rounded-full bg-accent-solid/[0.08] text-accent-ink', className)} aria-hidden="true">
      <Icon className="size-[17px]" />
    </span>
  )
}

export { TYPE_ICON }
