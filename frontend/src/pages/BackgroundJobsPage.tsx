// Background jobs (LLD §8.2): every crawl, resume upload and match run, with live progress while one
// is active, and the actions that start them. Filters live in the address.

import { FileUp, Plus, Target, Workflow } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { listBackgroundJobs } from '@/api/client'
import { jobLabel, outcomeText, progressText } from '@/components/app/job-text'
import { LiveIndicator } from '@/components/app/LiveIndicator'
import { PageHeader } from '@/components/app/PageHeader'
import { Pagination } from '@/components/app/Pagination'
import { RelativeTime } from '@/components/app/RelativeTime'
import { Segmented } from '@/components/app/Segmented'
import { EmptyState, ErrorNotice } from '@/components/app/states'
import { JobTypeIcon, StatusBadge } from '@/components/app/StatusBadge'
import { useReloadWhenHealthy } from '@/components/app/system-status'
import { useToast } from '@/components/app/toaster'
import { CancelJobButton, RecomputeMatchesDialog } from '@/components/background-jobs/actions'
import { NewCrawlDialog } from '@/components/background-jobs/NewCrawlDialog'
import { UploadResumesDialog } from '@/components/background-jobs/UploadResumesDialog'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useNow } from '@/hooks/useNow'
import { usePolling } from '@/hooks/usePolling'
import { oneOf, positiveInt, useQueryState } from '@/hooks/useQueryState'
import { useResource } from '@/hooks/useResource'
import { POLL_INTERVAL_MS } from '@/lib/app'
import { isActive, jobDuration, shortId, STATUS_LABEL } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { BackgroundJobCreated, BackgroundJobStatus, BackgroundJobSummary, BackgroundJobType } from '@/types/api'

const TYPES = ['crawl', 'resume', 'match'] as const
const STATUSES = ['queued', 'running', 'completed', 'failed', 'cancelled'] as const
const DIALOGS = ['crawl', 'upload', 'match'] as const
const PAGE_SIZE = 20

const TYPE_OPTIONS: { value: BackgroundJobType | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'crawl', label: 'Crawls' },
  { value: 'resume', label: 'Resume uploads' },
  { value: 'match', label: 'Match runs' },
]

function RunProgress({ job }: { job: BackgroundJobSummary }) {
  if (!isActive(job.status)) return null
  return (
    <div className="min-w-[9rem]">
      <Progress value={job.status === 'queued' ? 0 : job.progress.total ? job.progress.percent : null} aria-label={`${jobLabel(job)} progress`} />
      <p className="mt-1.5 text-xs tabular-nums text-subtle-foreground">{progressText(job)}</p>
    </div>
  )
}

export default function BackgroundJobsPage() {
  useDocumentTitle('Background jobs')
  const navigate = useNavigate()
  const toast = useToast()
  const now = useNow()
  const { get, set } = useQueryState()
  const type = oneOf(get('type'), TYPES)
  const status = oneOf(get('status'), STATUSES)
  const page = positiveInt(get('page'), 1)
  const dialog = oneOf(get('new'), DIALOGS)
  const openDialog = (name: (typeof DIALOGS)[number] | null) => set({ new: name, page: page === 1 ? null : page }, { replace: true })

  const list = useResource((signal) => listBackgroundJobs({ type, status, page, page_size: PAGE_SIZE }, signal), [type, status, page])
  const jobs = list.data?.items ?? []
  // Poll while a visible job is queued or running (LLD §8.5).
  const live = jobs.some((j) => isActive(j.status))
  usePolling(list.reload, POLL_INTERVAL_MS, live)
  useReloadWhenHealthy(list.reload, Boolean(list.error))

  const [updatedAt, setUpdatedAt] = useState<Date>()
  useEffect(() => {
    if (list.data) setUpdatedAt(new Date())
  }, [list.data])

  // A page past the end (for example after filtering) goes back to the last page.
  useEffect(() => {
    if (list.data && list.data.total > 0 && jobs.length === 0 && page > 1) set({ page: Math.ceil(list.data.total / PAGE_SIZE) })
  }, [list.data, jobs.length, page, set])

  const created = (job: BackgroundJobCreated, what: string) => {
    openDialog(null)
    void list.reload()
    toast({ title: `${what} queued`, description: 'It starts as soon as a worker is free.', action: { label: 'View the run', onClick: () => navigate(`/background-jobs/${job.background_job_id}`) } })
  }

  const filtered = Boolean(type || status)
  const empty = list.data && list.data.total === 0

  return (
    <>
      <PageHeader
        title="Background jobs"
        description="Crawls, resume uploads and match runs, with live progress."
        actions={
          <>
            <Button variant="outline" onClick={() => openDialog('match')}>
              <Target aria-hidden="true" />
              Recompute matches
            </Button>
            <Button variant="outline" onClick={() => openDialog('upload')}>
              <FileUp aria-hidden="true" />
              Upload resumes
            </Button>
            <Button onClick={() => openDialog('crawl')}>
              <Plus aria-hidden="true" />
              New crawl
            </Button>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Segmented label="Job type" value={type ?? 'all'} options={TYPE_OPTIONS} onChange={(v) => set({ type: v === 'all' ? null : v })} />
        <Select value={status ?? 'all'} onValueChange={(v) => set({ status: v === 'all' ? null : v })}>
          <SelectTrigger className="h-9 w-[11rem] rounded-full" aria-label="Status">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {STATUSES.map((s) => (
              <SelectItem key={s} value={s}>
                {STATUS_LABEL[s as BackgroundJobStatus]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {filtered && (
          <Button variant="ghost" size="sm" onClick={() => set({ type: null, status: null })}>
            Clear filters
          </Button>
        )}
        <LiveIndicator className="ml-auto" live={live} updatedAt={updatedAt} refreshing={list.refreshing} onRefresh={() => void list.reload()} />
      </div>

      {list.error && !list.data ? (
        <ErrorNotice block error={list.error} onRetry={() => void list.reload()} retrying={list.refreshing} />
      ) : (
        <Card className={cn('gap-0 py-0 transition-opacity duration-200', list.refreshing && !live && 'opacity-70')} aria-busy={list.loading || list.refreshing}>
          {list.error && <ErrorNotice error={list.error} onRetry={() => void list.reload()} className="m-4" />}
          {list.loading ? (
            <div className="space-y-4 p-5" aria-label="Loading runs">
              {Array.from({ length: 6 }, (_, i) => (
                <div key={i} className="flex items-center gap-4">
                  <Skeleton className="size-9 rounded-full" />
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="ml-auto h-6 w-24 rounded-full" />
                </div>
              ))}
            </div>
          ) : empty ? (
            filtered ? (
              <EmptyState
                icon={Workflow}
                title="No runs match these filters"
                description="Try another type or status, or clear the filters."
                action={
                  <Button variant="outline" onClick={() => set({ type: null, status: null })}>
                    Clear filters
                  </Button>
                }
              />
            ) : (
              <EmptyState
                icon={Workflow}
                title="No background jobs yet"
                description="Start a crawl to collect job postings, or upload resumes to add candidates. Each run appears here with live progress."
                action={
                  <>
                    <Button onClick={() => openDialog('crawl')}>
                      <Plus aria-hidden="true" />
                      New crawl
                    </Button>
                    <Button variant="outline" onClick={() => openDialog('upload')}>
                      <FileUp aria-hidden="true" />
                      Upload resumes
                    </Button>
                  </>
                }
              />
            )
          ) : (
            <>
              {/* Wide screens: a table. */}
              <div className="hidden md:block">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead>Run</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Progress or result</TableHead>
                      <TableHead>Created</TableHead>
                      <TableHead>Duration</TableHead>
                      <TableHead className="text-right">
                        <span className="sr-only">Actions</span>
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {jobs.map((job) => (
                      <TableRow key={job.background_job_id}>
                        <TableCell>
                          <div className="flex items-center gap-3">
                            <JobTypeIcon type={job.type} />
                            <div className="min-w-0">
                              <Link
                                to={`/background-jobs/${job.background_job_id}`}
                                className="rounded font-medium text-foreground underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
                              >
                                {jobLabel(job)}
                              </Link>
                              <p className="font-mono text-[11px] text-subtle-foreground">#{shortId(job.background_job_id)}</p>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>
                          <StatusBadge status={job.status} />
                        </TableCell>
                        <TableCell className="max-w-[22rem]">
                          {isActive(job.status) ? <RunProgress job={job} /> : <span className="text-[13px] text-muted-foreground">{outcomeText(job, now)}</span>}
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-[13px] text-muted-foreground">
                          <RelativeTime value={job.created_at} />
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-[13px] tabular-nums text-muted-foreground">{jobDuration(job.started_at, job.finished_at, now) ?? '—'}</TableCell>
                        <TableCell className="text-right">{isActive(job.status) && <CancelJobButton job={job} onDone={() => void list.reload()} size="xs" />}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              {/* Phones: one card per run. */}
              <ul className="divide-y divide-border md:hidden">
                {jobs.map((job) => (
                  <li key={job.background_job_id} className="flex gap-3 p-4">
                    <JobTypeIcon type={job.type} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <Link to={`/background-jobs/${job.background_job_id}`} className="rounded font-medium text-foreground underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50">
                          {jobLabel(job)} <span className="font-mono text-[11px] font-normal text-subtle-foreground">#{shortId(job.background_job_id)}</span>
                        </Link>
                        <StatusBadge status={job.status} />
                      </div>
                      <div className="mt-2">
                        {isActive(job.status) ? <RunProgress job={job} /> : <p className="text-[13px] text-muted-foreground">{outcomeText(job, now)}</p>}
                      </div>
                      <div className="mt-2 flex items-center justify-between gap-2 text-xs text-subtle-foreground">
                        <span>
                          Created <RelativeTime value={job.created_at} />
                        </span>
                        {isActive(job.status) && <CancelJobButton job={job} onDone={() => void list.reload()} size="xs" />}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
              <div className="border-t border-border px-5 py-3">
                <Pagination page={page} pageSize={PAGE_SIZE} total={list.data?.total ?? 0} onPage={(p) => set({ page: p > 1 ? p : null })} noun={['run', 'runs']} />
              </div>
            </>
          )}
        </Card>
      )}

      <NewCrawlDialog open={dialog === 'crawl'} onOpenChange={(open) => openDialog(open ? 'crawl' : null)} onCreated={(job) => created(job, 'Crawl')} />
      <UploadResumesDialog
        open={dialog === 'upload'}
        onOpenChange={(open) => openDialog(open ? 'upload' : null)}
        onCreated={() => void list.reload()}
        onViewJob={(id) => navigate(`/background-jobs/${id}`)}
      />
      <RecomputeMatchesDialog open={dialog === 'match'} onOpenChange={(open) => openDialog(open ? 'match' : null)} onCreated={(job) => created(job, 'Match run')} />
    </>
  )
}
