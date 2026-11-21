import { ChevronLeft, ChevronRight } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { formatNumber } from '@/lib/format'
import { cn } from '@/lib/utils'

interface PaginationProps {
  page: number
  pageSize: number
  total: number
  onPage: (page: number) => void
  /** Offered page sizes; omit to hide the selector. */
  pageSizes?: number[]
  onPageSize?: (size: number) => void
  noun?: [string, string]
  className?: string
}

/** "21–40 of 108 jobs", previous and next, and an optional page size. */
export function Pagination({ page, pageSize, total, onPage, pageSizes, onPageSize, noun = ['item', 'items'], className }: PaginationProps) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  const to = Math.min(total, page * pageSize)
  return (
    <nav aria-label="Pagination" className={cn('flex flex-wrap items-center justify-between gap-3', className)}>
      <p className="text-[13px] tabular-nums text-muted-foreground" aria-live="polite">
        {total === 0 ? `No ${noun[1]}` : `${formatNumber(from)}–${formatNumber(to)} of ${formatNumber(total)} ${total === 1 ? noun[0] : noun[1]}`}
      </p>
      <div className="flex items-center gap-2">
        {pageSizes && onPageSize && (
          <Select value={String(pageSize)} onValueChange={(v) => onPageSize(Number(v))}>
            <SelectTrigger className="h-8 w-[8.5rem] text-[13px]" aria-label="Rows per page">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {pageSizes.map((size) => (
                <SelectItem key={size} value={String(size)}>
                  {size} per page
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <span className="hidden text-[13px] tabular-nums text-subtle-foreground sm:inline">
          Page {page} of {pages}
        </span>
        <Button variant="outline" size="icon-sm" onClick={() => onPage(page - 1)} disabled={page <= 1} aria-label="Previous page">
          <ChevronLeft aria-hidden="true" />
        </Button>
        <Button variant="outline" size="icon-sm" onClick={() => onPage(page + 1)} disabled={page >= pages} aria-label="Next page">
          <ChevronRight aria-hidden="true" />
        </Button>
      </div>
    </nav>
  )
}
