// Application entry at /app (Phase 1 status page): proves that the frontend builds, runs and
// can reach the API. It calls GET /health and shows whether the API, PostgreSQL and Redis are
// reachable. The Background jobs page (LLD §8.2) takes over the /app entry in a later phase.

import { useCallback, useEffect, useState } from 'react'

import { API_BASE_URL, ApiError, getHealth } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'

type ServiceStatus = 'checking' | 'ok' | 'down' | 'unknown'

interface SystemStatus {
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

function StatusBadge({ status }: { status: ServiceStatus }) {
  if (status === 'ok') return <Badge className="bg-emerald-600 text-white">OK</Badge>
  if (status === 'down') return <Badge variant="destructive">Down</Badge>
  if (status === 'checking') return <Badge variant="secondary">Checking…</Badge>
  return <Badge variant="outline">Unknown</Badge>
}

export default function HomePage() {
  const [status, setStatus] = useState<SystemStatus>(CHECKING)

  const refresh = useCallback(async () => {
    setStatus(CHECKING)
    setStatus(await loadStatus())
  }, [])

  useEffect(() => {
    let active = true
    loadStatus().then((result) => {
      if (active) setStatus(result)
    })
    return () => {
      active = false
    }
  }, [])

  const rows: Array<[string, ServiceStatus]> = [
    ['API', status.api],
    ['PostgreSQL', status.database],
    ['Redis', status.redis],
  ]

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 px-4 py-12">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">FITSCAN</h1>
        <p className="text-muted-foreground">
          Job–Candidate Matching Platform: crawls job openings, parses resumes and matches candidates to jobs.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>System status</CardTitle>
          <CardDescription>
            Live result of <code className="font-mono text-sm">GET {API_BASE_URL}/health</code>
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="divide-y">
            {rows.map(([name, value]) => (
              <li key={name} className="flex items-center justify-between py-2">
                <span>{name}</span>
                <StatusBadge status={value} />
              </li>
            ))}
          </ul>
          {status.message && <p className="mt-3 text-sm text-destructive">{status.message}</p>}
        </CardContent>
        <CardFooter className="flex items-center justify-between gap-4">
          <span className="text-sm text-muted-foreground">
            {status.checkedAt ? `Checked at ${status.checkedAt.toLocaleTimeString()}` : 'Checking…'}
          </span>
          <div className="flex gap-2">
            <Button variant="outline" asChild>
              <a href={`${API_BASE_URL}/docs`} target="_blank" rel="noreferrer">
                API docs
              </a>
            </Button>
            <Button onClick={refresh} disabled={status.api === 'checking'}>
              Check again
            </Button>
          </div>
        </CardFooter>
      </Card>
    </main>
  )
}
