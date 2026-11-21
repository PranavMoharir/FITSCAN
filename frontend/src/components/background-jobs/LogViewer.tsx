import { ChevronRight } from 'lucide-react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'

import { ApiError, getBackgroundJobLogs } from '@/api/client'
import { Panel } from '@/components/app/Panel'
import { ErrorNotice } from '@/components/app/states'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { usePolling } from '@/hooks/usePolling'
import { toApiError } from '@/hooks/useResource'
import { POLL_INTERVAL_MS } from '@/lib/app'
import { formatNumber, formatTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { LogLevel, LogLine } from '@/types/api'

const LEVELS: { value: LogLevel | 'ALL'; label: string }[] = [
  { value: 'ALL', label: 'All levels' },
  { value: 'INFO', label: 'Info and above' },
  { value: 'WARNING', label: 'Warnings and errors' },
  { value: 'ERROR', label: 'Errors only' },
]

const LEVEL_STYLE: Record<LogLevel, string> = {
  DEBUG: 'text-subtle-foreground',
  INFO: 'text-muted-foreground',
  WARNING: 'text-accent-ink',
  ERROR: 'text-destructive font-semibold',
}

const PAGE = 500 // the API's maximum lines per request

/**
 * The live log viewer (LLD §8.5): loads every line once, then asks only for lines after the last
 * one seen (`after_id`) every POLL_INTERVAL while the run is active. A level filter starts again.
 */
export function LogViewer({ jobId, live }: { jobId: string; live: boolean }) {
  const [level, setLevel] = useState<LogLevel | 'ALL'>('ALL')
  const [lines, setLines] = useState<LogLine[]>([])
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState<ApiError>()
  const [follow, setFollow] = useState(true)
  const afterRef = useRef(0)
  const generation = useRef(0)
  const boxRef = useRef<HTMLDivElement>(null)

  const inFlight = useRef(-1)

  const fetchNew = useCallback(async () => {
    const gen = generation.current
    if (inFlight.current === gen) return // the previous request for these lines is still running
    inFlight.current = gen
    try {
      // Keep asking while full pages come back, so a long log loads completely.
      for (;;) {
        const page = await getBackgroundJobLogs(jobId, afterRef.current, level === 'ALL' ? undefined : level)
        if (gen !== generation.current) return
        afterRef.current = page.next_after_id
        if (page.items.length) setLines((current) => [...current, ...page.items])
        if (page.items.length < PAGE) break
      }
      setError(undefined)
    } catch (e) {
      if (gen === generation.current) setError(toApiError(e))
    } finally {
      if (inFlight.current === gen) inFlight.current = -1
      if (gen === generation.current) setLoaded(true)
    }
  }, [jobId, level])

  // Start again when the run or the level filter changes.
  useEffect(() => {
    generation.current += 1
    afterRef.current = 0
    setLines([])
    setLoaded(false)
    void fetchNew()
  }, [fetchNew])

  usePolling(fetchNew, POLL_INTERVAL_MS, live)

  // When the run ends, fetch once more for its last lines.
  const wasLive = useRef(live)
  useEffect(() => {
    if (wasLive.current && !live) void fetchNew()
    wasLive.current = live
  }, [live, fetchNew])

  // Follow: keep the newest line in view unless the reader scrolled up.
  useLayoutEffect(() => {
    const box = boxRef.current
    if (box && follow) box.scrollTop = box.scrollHeight
  }, [lines, follow])

  const onScroll = () => {
    const box = boxRef.current
    if (!box) return
    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 24
    if (atBottom !== follow) setFollow(atBottom)
  }

  return (
    <Panel
      id="logs"
      title="Log"
      description={loaded ? `${formatNumber(lines.length)} ${lines.length === 1 ? 'line' : 'lines'}${live ? ' · updating live' : ''}` : 'Loading…'}
      action={
        <Select value={level} onValueChange={(v) => setLevel(v as LogLevel | 'ALL')}>
          <SelectTrigger className="h-8 w-[11.5rem] text-[13px]" aria-label="Minimum log level">
            <SelectValue />
          </SelectTrigger>
          <SelectContent align="end">
            {LEVELS.map((l) => (
              <SelectItem key={l.value} value={l.value}>
                {l.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      }
    >
      {error && <ErrorNotice error={error} onRetry={() => void fetchNew()} className="mb-3" />}
      <div className="surface-ink overflow-hidden rounded-lg bg-background">
        <div
          ref={boxRef}
          onScroll={onScroll}
          role="log"
          aria-live="off"
          aria-label="Log lines"
          tabIndex={0}
          className="max-h-[28rem] min-h-40 overflow-y-auto px-1 py-2 font-mono text-[12.5px] leading-relaxed outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
        >
          {!loaded ? (
            <div className="space-y-2 p-3" aria-hidden="true">
              {Array.from({ length: 5 }, (_, i) => (
                <Skeleton key={i} className="h-3.5 bg-foreground/10" style={{ width: `${55 + ((i * 17) % 40)}%` }} />
              ))}
            </div>
          ) : lines.length === 0 ? (
            <p className="px-3 py-6 text-center font-sans text-[13px] text-muted-foreground">
              {level === 'ALL' ? (live ? 'No log lines yet. They appear here as the run works.' : 'This run wrote no log lines.') : 'No lines at this level.'}
            </p>
          ) : (
            <ol>
              {lines.map((line) => (
                <li key={line.log_id} className="grid grid-cols-[auto_4.5rem_minmax(0,1fr)] gap-x-3 rounded px-2.5 py-0.5 hover:bg-foreground/[0.04]">
                  <time dateTime={line.created_at} className="tabular-nums text-subtle-foreground">
                    {formatTime(line.created_at)}
                  </time>
                  <span className={cn('uppercase', LEVEL_STYLE[line.level])}>{line.level}</span>
                  <div className="min-w-0 text-foreground">
                    <span className="break-words">{line.message}</span>
                    {line.context && Object.keys(line.context).length > 0 && (
                      <details className="group mt-0.5">
                        <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded text-[11.5px] text-subtle-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
                          <ChevronRight className="size-3 transition-transform duration-150 group-open:rotate-90" aria-hidden="true" />
                          Context
                        </summary>
                        <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-all rounded bg-foreground/[0.05] p-2 text-[11.5px] text-muted-foreground">
                          {JSON.stringify(line.context, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
      {!follow && lines.length > 0 && (
        <button
          type="button"
          onClick={() => setFollow(true)}
          className="mt-2 rounded text-xs font-medium text-accent-ink underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          Jump to the newest line
        </button>
      )}
    </Panel>
  )
}
