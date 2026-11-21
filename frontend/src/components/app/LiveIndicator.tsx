import { RotateCw } from 'lucide-react'

import { PulseDot } from '@/components/app/StatusBadge'
import { Button } from '@/components/ui/button'
import { POLL_INTERVAL_MS } from '@/lib/app'
import { formatTime } from '@/lib/format'
import { cn } from '@/lib/utils'

interface LiveIndicatorProps {
  /** True while the page refreshes itself because a background job is active. */
  live: boolean
  updatedAt?: Date
  refreshing?: boolean
  onRefresh: () => void
  className?: string
}

/** "Live" while auto-refreshing; otherwise the time of the last update and a refresh button. */
export function LiveIndicator({ live, updatedAt, refreshing, onRefresh, className }: LiveIndicatorProps) {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      {live ? (
        <span
          className="inline-flex h-8 items-center gap-2 rounded-full bg-primary/[0.08] px-3 text-[13px] font-medium text-accent-ink"
          title={`Refreshing every ${Math.round(POLL_INTERVAL_MS / 100) / 10} seconds while a background job is active`}
        >
          <PulseDot />
          Live
          <span className="sr-only">: refreshing every {Math.round(POLL_INTERVAL_MS / 100) / 10} seconds while a background job is active</span>
        </span>
      ) : (
        updatedAt && <span className="text-[13px] text-subtle-foreground">Updated {formatTime(updatedAt)}</span>
      )}
      <Button variant="outline" size="sm" onClick={onRefresh} disabled={refreshing}>
        <RotateCw className={cn(refreshing && 'animate-spin')} aria-hidden="true" />
        Refresh
      </Button>
    </div>
  )
}
