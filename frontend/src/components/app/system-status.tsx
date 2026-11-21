// System status from GET /health, shared by the header indicator and the dashboard card.
// This is the check the /app entry page showed before the dashboard (moved here, not removed).

import { CircleCheck, CircleX, CloudOff, Loader2, RotateCw, TriangleAlert } from 'lucide-react'
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'

import { API_BASE_URL, ApiError, getHealth } from '@/api/client'
import { Panel } from '@/components/app/Panel'
import { RelativeTime } from '@/components/app/RelativeTime'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { usePolling } from '@/hooks/usePolling'
import { HEALTH_INTERVAL_MS } from '@/lib/app'
import { cn } from '@/lib/utils'

export type ServiceStatus = 'checking' | 'ok' | 'down' | 'unknown'

export interface SystemStatus {
  api: ServiceStatus
  database: ServiceStatus
  redis: ServiceStatus
  message?: string
  checkedAt?: Date
}

const CHECKING: SystemStatus = { api: 'checking', database: 'checking', redis: 'checking' }

function asServiceStatus(value: unknown): ServiceStatus {
  return value === 'ok' || value === 'down' ? value : 'unknown'
}

async function loadStatus(): Promise<SystemStatus> {
  const checkedAt = new Date()
  try {
    const health = await getHealth()
    return { api: 'ok', database: health.database, redis: health.redis, checkedAt }
  } catch (error) {
    if (error instanceof ApiError && error.status === 503) {
      // The API answered, but a dependency is down; details say which one.
      return {
        api: 'ok',
        database: asServiceStatus(error.details?.database),
        redis: asServiceStatus(error.details?.redis),
        message: error.message,
        checkedAt,
      }
    }
    const message = error instanceof Error ? error.message : 'Unknown error.'
    return { api: 'down', database: 'unknown', redis: 'unknown', message, checkedAt }
  }
}

/** 'ok', 'degraded' (the API answers but a dependency is down), 'down' or 'checking'. */
export type Overall = 'checking' | 'ok' | 'degraded' | 'down'

export function overallOf(status: SystemStatus): Overall {
  if (status.api === 'checking') return 'checking'
  if (status.api !== 'ok') return 'down'
  return status.database === 'ok' && status.redis === 'ok' ? 'ok' : 'degraded'
}

interface ContextValue {
  status: SystemStatus
  checking: boolean
  refresh: () => Promise<void>
}

const SystemStatusContext = createContext<ContextValue>({ status: CHECKING, checking: true, refresh: async () => {} })

export function SystemStatusProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SystemStatus>(CHECKING)
  const [checking, setChecking] = useState(true)
  const latestCheck = useRef(0)

  const refresh = useCallback(async () => {
    const check = ++latestCheck.current
    setChecking(true)
    const next = await loadStatus()
    // A slow, older check must not overwrite a newer answer (for example "down" after "ok").
    if (check !== latestCheck.current) return
    setStatus(next)
    setChecking(false)
  }, [])

  useEffect(() => {
    void refresh()
    const onFocus = () => void refresh()
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [refresh])
  usePolling(refresh, HEALTH_INTERVAL_MS, true)

  const value = useMemo(() => ({ status, checking, refresh }), [status, checking, refresh])
  return <SystemStatusContext.Provider value={value}>{children}</SystemStatusContext.Provider>
}

export const useSystemStatus = () => useContext(SystemStatusContext)

export function downServices(status: SystemStatus): string[] {
  return [status.database === 'down' && 'PostgreSQL', status.redis === 'down' && 'Redis'].filter(Boolean) as string[]
}

/**
 * Runs `reload` once when the services come back after an outage, if the page shows an error.
 * The error may also arrive after the recovery: a request sent while the database was down can
 * fail after the health check already says "ok". It is reloaded then, once.
 */
export function useReloadWhenHealthy(reload: () => unknown, hasError: boolean) {
  const { status } = useSystemStatus()
  const overall = overallOf(status)
  const outageSeen = useRef(false)
  const reloadRef = useRef(reload)
  reloadRef.current = reload
  useEffect(() => {
    if (overall === 'degraded' || overall === 'down') outageSeen.current = true
    else if (overall === 'ok' && hasError && outageSeen.current) {
      outageSeen.current = false
      void reloadRef.current()
    }
  }, [overall, hasError])
}

const OVERALL_TEXT: Record<Overall, (status: SystemStatus) => string> = {
  checking: () => 'Checking services…',
  ok: () => 'All systems operational',
  degraded: (s) => {
    const down = downServices(s)
    return down.length ? `${down.join(' and ')} unavailable` : 'A service is unavailable'
  },
  down: () => 'API unreachable',
}

/** The header indicator: icon and text on wide screens, icon with a tooltip on phones. */
export function SystemStatusPill() {
  const { status } = useSystemStatus()
  const overall = overallOf(status)
  const text = OVERALL_TEXT[overall](status)
  const Icon = overall === 'ok' ? CircleCheck : overall === 'checking' ? Loader2 : overall === 'down' ? CloudOff : TriangleAlert
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          to="/app"
          aria-label={`System status: ${text}`}
          className={cn(
            'inline-flex h-8 items-center gap-2 rounded-full border px-2.5 text-[13px] font-medium outline-none transition-colors duration-150 focus-visible:ring-3 focus-visible:ring-ring/50 sm:px-3',
            overall === 'ok' && 'border-border text-muted-foreground hover:text-foreground',
            overall === 'checking' && 'border-border text-subtle-foreground',
            (overall === 'degraded' || overall === 'down') && 'border-destructive/30 bg-destructive/[0.06] text-destructive',
          )}
        >
          <Icon className={cn('size-4', overall === 'ok' && 'text-accent-ink', overall === 'checking' && 'animate-spin')} aria-hidden="true" />
          <span className="hidden sm:inline">{text}</span>
        </Link>
      </TooltipTrigger>
      <TooltipContent side="bottom">
        {status.checkedAt ? `${text}. Checked at ${status.checkedAt.toLocaleTimeString()}.` : text}
      </TooltipContent>
    </Tooltip>
  )
}

function ServiceRow({ name, status }: { name: string; status: ServiceStatus }) {
  const label = status === 'ok' ? 'Operational' : status === 'down' ? 'Down' : status === 'checking' ? 'Checking…' : 'Unknown'
  const Icon = status === 'ok' ? CircleCheck : status === 'down' ? CircleX : status === 'checking' ? Loader2 : TriangleAlert
  return (
    <li className="flex items-center justify-between gap-4 py-2.5">
      <span className="text-sm font-medium">{name}</span>
      <span
        className={cn(
          'inline-flex items-center gap-1.5 text-[13px]',
          status === 'ok' && 'text-muted-foreground',
          status === 'down' && 'font-medium text-destructive',
          (status === 'checking' || status === 'unknown') && 'text-subtle-foreground',
        )}
      >
        <Icon className={cn('size-4', status === 'ok' && 'text-accent-ink', status === 'checking' && 'animate-spin')} aria-hidden="true" />
        {label}
      </span>
    </li>
  )
}

/** The dashboard card: API, PostgreSQL and Redis, the time of the check and "Check again". */
export function SystemStatusCard({ className }: { className?: string }) {
  const { status, checking, refresh } = useSystemStatus()
  return (
    <Panel
      id="system-status"
      className={className}
      title="System status"
      description={
        <>
          Live result of <code className="font-mono text-[12px]">GET /health</code>
        </>
      }
      action={
        <Button variant="ghost" size="icon-sm" onClick={() => void refresh()} disabled={checking} aria-label="Check again">
          <RotateCw className={cn(checking && 'animate-spin')} aria-hidden="true" />
        </Button>
      }
    >
      <ul className="divide-y divide-border">
        <ServiceRow name="API" status={status.api} />
        <ServiceRow name="PostgreSQL" status={status.database} />
        <ServiceRow name="Redis" status={status.redis} />
      </ul>
      {status.message && overallOf(status) !== 'ok' && (
        <p className="mt-3 text-[13px] leading-relaxed text-destructive" role="status">
          {status.message}
        </p>
      )}
      <p className="mt-3 text-xs text-subtle-foreground">
        {status.checkedAt ? (
          <>
            Checked <RelativeTime value={status.checkedAt.toISOString()} /> · {API_BASE_URL.replace(/^https?:\/\//, '')}
          </>
        ) : (
          'Checking…'
        )}
      </p>
    </Panel>
  )
}
