import { useNow } from '@/hooks/useNow'
import { formatDateTime, formatRelative } from '@/lib/format'

/** "5 minutes ago", kept current; the exact date and time on hover. */
export function RelativeTime({ value, className }: { value: string | null | undefined; className?: string }) {
  const now = useNow()
  if (!value) return <span className={className}>—</span>
  return (
    <time dateTime={value} title={formatDateTime(value)} className={className}>
      {formatRelative(value, now)}
    </time>
  )
}
