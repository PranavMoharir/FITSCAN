import { ArrowRight, Check, CircleDashed, Workflow } from 'lucide-react'
import { Link } from 'react-router'

import { lastTime, jobLabel, noun, outcomeText, progressText } from '@/components/app/job-text'
import { Panel } from '@/components/app/Panel'
import { RelativeTime } from '@/components/app/RelativeTime'
import { EmptyState, ListSkeleton } from '@/components/app/states'
import { JobTypeIcon, StatusBadge, TYPE_ICON } from '@/components/app/StatusBadge'
import { STATUSES, TYPES, type DashboardActivity } from '@/components/dashboard/data'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { useNow } from '@/hooks/useNow'
import { formatNumber, plural, shortId } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { BackgroundJobType } from '@/types/api'

function ViewAll({ to, label = 'View all' }: { to: string; label?: string }) {
  return (
    <Button variant="ghost" size="sm" asChild>
      <Link to={to}>
        {label}
        <ArrowRight aria-hidden="true" />
      </Link>
    </Button>
  )
}

/** Active runs with live progress, then every run counted by status. */
export function JobStatusOverview({ data, className }: { data?: DashboardActivity; className?: string }) {
  return (
    <Panel id="job-status" className={className} title="Background jobs" description="Active runs and every run by status" action={<ViewAll to="/background-jobs" />}>
      {!data ? (
        <div className="space-y-5" aria-hidden="true">
          <ListSkeleton rows={1} />
          <div className="space-y-3 border-t border-border pt-4">
            {STATUSES.map((s) => (
              <Skeleton key={s} className="h-6" />
            ))}
          </div>
        </div>
      ) : (
        <>
          {data.active.length === 0 ? (
            <div className="flex items-center gap-3 rounded-lg bg-foreground/[0.03] px-4 py-3.5">
              <CircleDashed className="size-5 shrink-0 text-subtle-foreground" aria-hidden="true" />
              <p className="text-sm text-muted-foreground">
                Nothing is running. Start a crawl, upload resumes or recompute matches on{' '}
                <Link to="/background-jobs" className="font-medium text-accent-ink underline-offset-4 hover:underline">
                  Background jobs
                </Link>
                .
              </p>
            </div>
          ) : (
            <ul className="space-y-1" aria-label="Active runs">
              {data.active.map((job) => (
                <li key={job.background_job_id}>
                  <Link
                    to={`/background-jobs/${job.background_job_id}`}
                    className="-mx-2 flex items-center gap-3 rounded-lg p-2 outline-none transition-colors duration-150 hover:bg-foreground/[0.03] focus-visible:ring-3 focus-visible:ring-ring/50"
                  >
                    <JobTypeIcon type={job.type} />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium text-foreground">{jobLabel(job)}</span>
                        <StatusBadge status={job.status} />
                      </span>
                      <Progress
                        className="mt-2.5"
                        value={job.status === 'queued' ? 0 : job.progress.total ? job.progress.percent : null}
                        aria-label={`${jobLabel(job)} progress`}
                      />
                      <span className="mt-1.5 block text-xs tabular-nums text-subtle-foreground">
                        {progressText(job)}
                        {job.started_at && (
                          <>
                            {' · started '}
                            <RelativeTime value={job.started_at} />
                          </>
                        )}
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-5 border-t border-border pt-4">
            <ul className="space-y-1" aria-label="Runs by status">
              {STATUSES.map((status) => {
                const count = data.counts[status]
                const share = data.total ? (count / data.total) * 100 : 0
                return (
                  <li key={status}>
                    <Link
                      to={`/background-jobs?status=${status}`}
                      className="-mx-2 grid grid-cols-[7.25rem_minmax(0,1fr)_3rem] items-center gap-3 rounded-lg px-2 py-1.5 outline-none transition-colors duration-150 hover:bg-foreground/[0.03] focus-visible:ring-3 focus-visible:ring-ring/50"
                    >
                      <StatusBadge status={status} className="justify-self-start" />
                      <span className="h-1.5 overflow-hidden rounded-full bg-track" aria-hidden="true">
                        <span
                          className={cn(
                            'block h-full rounded-full transition-[width] duration-500 ease-out',
                            status === 'running' ? 'bg-primary' : status === 'failed' ? 'bg-destructive' : 'bg-foreground/35',
                          )}
                          style={{ width: count ? `max(${share}%, 4px)` : '0' }}
                        />
                      </span>
                      <span className="text-right text-sm font-medium tabular-nums text-foreground">{formatNumber(count)}</span>
                    </Link>
                  </li>
                )
              })}
            </ul>
            <p className="mt-3 text-xs text-subtle-foreground">{plural(data.total, 'run')} in total</p>
          </div>
        </>
      )}
    </Panel>
  )
}

const STEP: Record<BackgroundJobType, string> = { crawl: 'Crawl job postings', resume: 'Parse resumes', match: 'Compute matches' }

/** The last completed run of each step of the workflow: crawl, resumes, matches. */
export function PipelineCard({ data, className }: { data?: DashboardActivity; className?: string }) {
  return (
    <Panel id="pipeline" className={className} title="Pipeline" description="The last completed run of each step">
      <ol className="relative space-y-5">
        <span aria-hidden="true" className="absolute bottom-4 left-[17px] top-4 w-px bg-border" />
        {TYPES.map((type) => {
          const Icon = TYPE_ICON[type]
          const last = data?.lastCompleted[type]
          return (
            <li key={type} className="relative flex gap-3.5">
              <span
                className={cn(
                  'relative grid size-9 shrink-0 place-items-center rounded-full ring-4 ring-card',
                  last ? 'bg-primary text-primary-foreground' : 'bg-secondary text-subtle-foreground',
                )}
                aria-hidden="true"
              >
                <Icon className="size-4" />
              </span>
              <div className="min-w-0 pt-0.5">
                <p className="text-sm font-medium text-foreground">{STEP[type]}</p>
                {!data ? (
                  <Skeleton className="mt-1.5 h-3 w-40" />
                ) : last ? (
                  <p className="mt-0.5 text-[13px] text-muted-foreground">
                    <RelativeTime value={last.finished_at} /> · {noun(last, last.items_succeeded)}
                  </p>
                ) : (
                  <p className="mt-0.5 text-[13px] text-subtle-foreground">Not run yet</p>
                )}
                <Link
                  to={`/background-jobs?type=${type}`}
                  className="mt-1 inline-flex rounded text-xs font-medium text-accent-ink underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  View runs<span className="sr-only">: {STEP[type]}</span>
                </Link>
              </div>
            </li>
          )
        })}
      </ol>
    </Panel>
  )
}

/** The newest background jobs: what ran, how it ended and when. */
export function RecentActivity({ data, className }: { data?: DashboardActivity; className?: string }) {
  const now = useNow()
  return (
    <Panel id="recent-activity" className={className} title="Recent activity" description="The newest background jobs first" action={data?.recent.length ? <ViewAll to="/background-jobs" /> : undefined}>
      {!data ? (
        <ListSkeleton rows={4} />
      ) : data.recent.length === 0 ? (
        <EmptyState
          compact
          icon={Workflow}
          title="No background jobs yet"
          description="Runs appear here when you start a crawl, upload resumes or recompute matches."
          action={
            <Button asChild size="sm">
              <Link to="/background-jobs">Go to Background jobs</Link>
            </Button>
          }
        />
      ) : (
        <ul className="divide-y divide-border">
          {data.recent.map((job) => (
            <li key={job.background_job_id} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
              <JobTypeIcon type={job.type} className="mt-0.5" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                  <p className="flex min-w-0 flex-wrap items-baseline gap-x-2">
                    <Link
                      to={`/background-jobs/${job.background_job_id}`}
                      className="rounded text-sm font-medium text-foreground underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
                    >
                      {jobLabel(job)}
                    </Link>
                    <span className="font-mono text-[11px] text-subtle-foreground">#{shortId(job.background_job_id)}</span>
                  </p>
                  <StatusBadge status={job.status} />
                </div>
                <div className="mt-1 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 text-[13px]">
                  <p className="min-w-0 leading-relaxed text-muted-foreground">{outcomeText(job, now)}</p>
                  <RelativeTime value={lastTime(job)} className="shrink-0 text-xs text-subtle-foreground" />
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}

interface SetupProps {
  jobs: number | null
  candidates: number | null
  matched: boolean
}

/** Shown until the three set-up steps have each happened once. A burgundy panel, like the landing page's call to action. */
export function GettingStarted({ jobs, candidates, matched }: SetupProps) {
  const steps = [
    { done: (jobs ?? 0) > 0, title: 'Crawl job postings', text: 'Point the crawler at a careers site; each posting is saved with its skills.', to: '/background-jobs?new=crawl', cta: 'Start a crawl' },
    { done: (candidates ?? 0) > 0, title: 'Upload resumes', text: 'PDF resumes are parsed into candidates, with OCR for scanned files.', to: '/background-jobs?new=upload', cta: 'Upload resumes' },
    { done: matched, title: 'Compute matches', text: 'Score every candidate against every job with the weighted formula.', to: '/background-jobs?new=match', cta: 'Recompute matches' },
  ]
  const doneCount = steps.filter((s) => s.done).length
  if (doneCount === steps.length) return null
  const next = steps.findIndex((s) => !s.done)
  return (
    <section aria-labelledby="setup-title" className="surface-wine relative overflow-hidden rounded-xl bg-background bg-[radial-gradient(90%_120%_at_0%_0%,rgb(255_255_255/0.08),transparent_55%)] p-6 text-foreground sm:p-7">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-subtle-foreground">Getting started</p>
          <h2 id="setup-title" className="mt-1.5 font-display text-3xl font-normal leading-tight">
            Set up FITSCAN in three steps
          </h2>
        </div>
        <p className="text-[13px] text-muted-foreground">
          {doneCount} of {steps.length} done
        </p>
      </div>
      <ol className="mt-6 grid gap-3 md:grid-cols-3">
        {steps.map((step, i) => (
          <li key={step.title} className="flex flex-col rounded-lg bg-card/60 p-4 ring-1 ring-border">
            <div className="flex items-center gap-2.5">
              <span
                className={cn('grid size-7 place-items-center rounded-full text-xs font-semibold', step.done ? 'bg-primary text-primary-foreground' : 'ring-1 ring-foreground/40')}
                aria-hidden="true"
              >
                {step.done ? <Check className="size-3.5" /> : i + 1}
              </span>
              <p className="text-sm font-semibold">
                {step.title}
                {step.done && <span className="sr-only"> (done)</span>}
              </p>
            </div>
            <p className="mt-2 flex-1 text-[13px] leading-relaxed text-muted-foreground">{step.text}</p>
            {!step.done && (
              <Button asChild size="sm" variant={i === next ? 'default' : 'outline'} className="mt-4 self-start">
                <Link to={step.to}>
                  {step.cta}
                  <ArrowRight aria-hidden="true" />
                </Link>
              </Button>
            )}
          </li>
        ))}
      </ol>
    </section>
  )
}
