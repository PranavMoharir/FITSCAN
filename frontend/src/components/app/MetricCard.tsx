import { ArrowUpRight, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { Skeleton } from '@/components/ui/skeleton'
import { formatNumber } from '@/lib/format'
import { cn } from '@/lib/utils'

interface MetricCardProps {
  label: string
  /** undefined while loading; null when it could not be loaded (shown as a dash, never as 0). */
  value: number | null | undefined
  icon: LucideIcon
  hint?: ReactNode
  to: string
  className?: string
}

/** One count from the API, linking to the page where it comes from. */
export function MetricCard({ label, value, icon: Icon, hint, to, className }: MetricCardProps) {
  return (
    <Link
      to={to}
      className={cn(
        'group relative flex flex-col rounded-xl bg-card p-5 text-card-foreground shadow-xs ring-1 ring-foreground/10 outline-none',
        'transition-[box-shadow,translate] duration-200 ease-out hover:-translate-y-0.5 hover:shadow-[0_14px_34px_-20px_rgb(11_11_11/0.35)] focus-visible:ring-3 focus-visible:ring-ring/50',
        className,
      )}
    >
      <span className="flex items-start justify-between gap-3">
        <span className="pt-1.5 text-[13px] font-medium leading-snug text-muted-foreground">{label}</span>
        <span className="hidden size-8 shrink-0 place-items-center rounded-full bg-accent-solid/[0.08] text-accent-ink sm:grid" aria-hidden="true">
          <Icon className="size-4" />
        </span>
      </span>
      <span className="mt-4 flex h-12 items-end">
        {value === undefined ? (
          <Skeleton className="h-11 w-24" />
        ) : (
          <span className="font-display text-5xl font-normal leading-none text-foreground">{value === null ? '—' : formatNumber(value)}</span>
        )}
      </span>
      <span className="mt-auto flex items-end justify-between gap-2 pt-2 text-xs leading-snug text-subtle-foreground">
        <span className="min-w-0">{value === null ? 'Could not load' : (hint ?? ' ')}</span>
        <ArrowUpRight
          className="size-3.5 shrink-0 opacity-0 transition-[opacity,translate] duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:opacity-100 group-focus-visible:opacity-100"
          aria-hidden="true"
        />
      </span>
    </Link>
  )
}
