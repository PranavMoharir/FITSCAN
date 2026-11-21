// Shared empty, error and loading states for the application pages.

import { CloudOff, RotateCw, SearchX, ServerCrash, TriangleAlert, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { ApiError } from '@/api/client'
import { downServices, useSystemStatus } from '@/components/app/system-status'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description?: ReactNode
  action?: ReactNode
  className?: string
  compact?: boolean
}

/** Says what is missing and what to do next, never just "No data". */
export function EmptyState({ icon: Icon, title, description, action, className, compact = false }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center text-center', compact ? 'px-4 py-8' : 'px-6 py-14', className)}>
      <span className="grid size-11 place-items-center rounded-full bg-accent-solid/[0.08] text-accent-ink" aria-hidden="true">
        <Icon className="size-5" />
      </span>
      <p className="mt-4 text-[15px] font-semibold text-foreground">{title}</p>
      {description && <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-muted-foreground">{description}</p>}
      {action && <div className="mt-5 flex flex-wrap items-center justify-center gap-2">{action}</div>}
    </div>
  )
}

/** A heading and a sentence for an API error, in words a user can act on. */
export function describeError(error: ApiError): { title: string; message: string; icon: LucideIcon } {
  if (error.status === 0) {
    return { title: 'Cannot reach the API', message: `${error.message} Check that the API server is running.`, icon: CloudOff }
  }
  if (error.status === 503) {
    const down = ['database', 'redis', 'broker'].filter((key) => error.details?.[key] === 'down')
    const names = down.map((key) => (key === 'database' ? 'PostgreSQL' : key === 'redis' ? 'Redis' : 'the job queue'))
    const sentence = `${names.join(' and ')} ${names.length > 1 ? 'are' : 'is'} not available right now. Try again in a moment.`
    return {
      title: 'A service is unavailable',
      // Capitalised, because "the job queue" can start the sentence.
      message: names.length ? sentence[0].toUpperCase() + sentence.slice(1) : error.message,
      icon: ServerCrash,
    }
  }
  if (error.status === 404) return { title: 'Not found', message: error.message, icon: SearchX }
  if (error.status === 422) return { title: 'This link is not valid', message: error.message, icon: SearchX }
  if (error.status >= 500) {
    return { title: 'Something went wrong on the server', message: `${error.message} If it keeps happening, check the API logs.`, icon: ServerCrash }
  }
  return { title: 'The request failed', message: error.message, icon: TriangleAlert }
}

interface ErrorNoticeProps {
  error: ApiError
  onRetry?: () => void
  retrying?: boolean
  className?: string
  /** Shown as a full panel (a page that could not load) instead of an inline banner. */
  block?: boolean
}

export function ErrorNotice({ error, onRetry, retrying, className, block = false }: ErrorNoticeProps) {
  const { status } = useSystemStatus()
  const down = downServices(status)
  // A data request that failed on the server while the health check reports a service down: say which.
  const { title, message, icon: Icon } =
    error.status >= 500 && down.length
      ? {
          title: `${down.join(' and ')} ${down.length > 1 ? 'are' : 'is'} unavailable`,
          message: `This page needs ${down.join(' and ')} to load its data. It reloads by itself when ${down.length > 1 ? 'they are' : 'it is'} back.`,
          icon: ServerCrash,
        }
      : describeError(error)
  const retry = onRetry && (
    <Button variant="outline" size="sm" onClick={onRetry} disabled={retrying}>
      <RotateCw className={cn(retrying && 'animate-spin')} aria-hidden="true" />
      Try again
    </Button>
  )
  if (block) {
    return (
      <div role="alert" className={cn('rounded-xl border border-border bg-card', className)}>
        <EmptyState icon={Icon} title={title} description={message} action={retry} />
      </div>
    )
  }
  return (
    <div role="alert" className={cn('flex flex-col gap-3 rounded-xl border border-destructive/25 bg-destructive/[0.05] p-4 sm:flex-row sm:items-center', className)}>
      <Icon className="size-5 shrink-0 text-destructive" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-foreground">{title}</p>
        <p className="mt-0.5 text-[13px] leading-relaxed text-muted-foreground">{message}</p>
      </div>
      {retry}
    </div>
  )
}

/** Placeholder rows shaped like the content that is loading, so nothing jumps when it arrives. */
export function ListSkeleton({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn('space-y-4', className)} aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton className="size-9 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3.5 w-2/5" />
            <Skeleton className="h-3 w-3/5" />
          </div>
        </div>
      ))}
    </div>
  )
}

/** Shown inside the shell while a page's code loads. */
export function PageSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading page">
      <div className="space-y-3">
        <Skeleton className="h-10 w-56" />
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-32 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-72 rounded-xl" />
    </div>
  )
}
