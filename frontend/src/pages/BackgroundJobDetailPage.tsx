// One background job (LLD §8.2): its parameters, counters, failure reason and the live log viewer.

import { ArrowLeft, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'

import { getBackgroundJob } from '@/api/client'
import { jobLabel, noun } from '@/components/app/job-text'
import { LiveIndicator } from '@/components/app/LiveIndicator'
import { PageHeader } from '@/components/app/PageHeader'
import { Panel } from '@/components/app/Panel'
import { RelativeTime } from '@/components/app/RelativeTime'
import { ErrorNotice } from '@/components/app/states'
import { StatusBadge } from '@/components/app/StatusBadge'
import { useReloadWhenHealthy } from '@/components/app/system-status'
import { CancelJobButton } from '@/components/background-jobs/actions'
import { JobParams } from '@/components/background-jobs/JobParams'
import { LogViewer } from '@/components/background-jobs/LogViewer'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useNow } from '@/hooks/useNow'
import { usePolling } from '@/hooks/usePolling'
import { useResource } from '@/hooks/useResource'
import { POLL_INTERVAL_MS } from '@/lib/app'
import { formatDateTime, formatNumber, isActive, jobDuration, shortId } from '@/lib/format'
import type { BackgroundJobDetail } from '@/types/api'

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[13px] text-muted-foreground">{label}</dt>
      <dd className="mt-1 font-display text-3xl font-normal leading-none text-foreground">{value}</dd>
    </div>
  )
}

function ProgressPanel({ job }: { job: BackgroundJobDetail }) {
  const { current, total, percent } = job.progress
  const active = isActive(job.status)
  return (
    <Panel id="progress" title="Progress">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <p className="font-display text-6xl font-normal leading-none text-foreground">
          {total ? percent : formatNumber(current)}
          <span className="ml-1 text-2xl text-subtle-foreground">{total ? '%' : ''}</span>
        </p>
        <p className="text-[13px] tabular-nums text-muted-foreground">
          {job.status === 'queued' ? 'Waiting for a worker' : total ? `${formatNumber(current)} of ${noun(job, total)}` : `${noun(job, current)} processed`}
        </p>
      </div>
      <Progress
        className="mt-4 h-2"
        value={job.status === 'queued' ? 0 : total ? percent : null}
        aria-label={`${jobLabel(job)} progress`}
        indicatorClassName={active ? undefined : job.status === 'failed' ? 'bg-destructive' : job.status === 'cancelled' ? 'bg-foreground/35' : undefined}
      />
      <dl className="mt-6 grid grid-cols-3 gap-4 border-t border-border pt-5">
        <Stat label="Succeeded" value={formatNumber(job.items_succeeded)} />
        <Stat label="Failed" value={formatNumber(job.items_failed)} />
        <Stat label="Processed" value={formatNumber(current)} />
      </dl>
    </Panel>
  )
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[6.5rem_minmax(0,1fr)] gap-3 py-2.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-foreground">{children}</dd>
    </div>
  )
}

export default function BackgroundJobDetailPage() {
  const { id = '' } = useParams()
  const now = useNow()
  const job = useResource((signal) => getBackgroundJob(id, signal), [id])
  const data = job.data
  const live = data ? isActive(data.status) : false
  usePolling(job.reload, POLL_INTERVAL_MS, live)
  useReloadWhenHealthy(job.reload, Boolean(job.error))
  useDocumentTitle(data ? `${jobLabel(data)} #${shortId(data.background_job_id)}` : 'Background job')

  const [updatedAt, setUpdatedAt] = useState<Date>()
  useEffect(() => {
    if (data) setUpdatedAt(new Date())
  }, [data])

  if (job.error && !data) {
    return (
      <>
        <PageHeader title="Background job" back={{ to: '/background-jobs', label: 'Background jobs' }} />
        <ErrorNotice
          block
          error={job.error}
          onRetry={job.error.status === 404 || job.error.status === 422 ? undefined : () => void job.reload()}
          retrying={job.refreshing}
        />
        <Button asChild variant="outline" className="mt-4">
          <Link to="/background-jobs">
            <ArrowLeft aria-hidden="true" />
            All background jobs
          </Link>
        </Button>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title={data ? jobLabel(data) : <Skeleton className="h-11 w-56" />}
        titleAddon={data && <StatusBadge status={data.status} />}
        back={{ to: '/background-jobs', label: 'Background jobs' }}
        description={
          data && (
            <>
              Run <span className="font-mono text-[13px]">#{shortId(data.background_job_id)}</span> · created <RelativeTime value={data.created_at} />
            </>
          )
        }
        actions={
          data && (
            <>
              <LiveIndicator live={live} updatedAt={updatedAt} refreshing={job.refreshing} onRefresh={() => void job.reload()} />
              {live && <CancelJobButton job={data} onDone={() => void job.reload()} />}
            </>
          )
        }
      />
      {job.error && <ErrorNotice error={job.error} onRetry={() => void job.reload()} className="mb-5" />}

      {!data ? (
        <div className="grid gap-5 lg:grid-cols-3" aria-hidden="true">
          <Skeleton className="h-64 rounded-xl lg:col-span-2" />
          <Skeleton className="h-64 rounded-xl" />
        </div>
      ) : (
        <div className="grid items-start gap-4 lg:grid-cols-3 lg:gap-5">
          <div className="grid gap-4 lg:col-span-2 lg:gap-5">
            {data.status === 'failed' && data.error_message && (
              <div role="alert" className="flex gap-3 rounded-xl border border-destructive/25 bg-destructive/[0.05] p-4">
                <TriangleAlert className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden="true" />
                <div>
                  <p className="text-sm font-semibold text-foreground">Why it failed</p>
                  <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{data.error_message}</p>
                </div>
              </div>
            )}
            <ProgressPanel job={data} />
            <LogViewer jobId={data.background_job_id} live={live} />
          </div>
          <div className="grid gap-4 lg:gap-5">
            <Panel id="details" title="Details">
              <dl className="divide-y divide-border">
                <DetailRow label="Type">{jobLabel(data)}</DetailRow>
                <DetailRow label="Status">
                  <StatusBadge status={data.status} />
                </DetailRow>
                <DetailRow label="Created">{formatDateTime(data.created_at)}</DetailRow>
                <DetailRow label="Started">{data.started_at ? formatDateTime(data.started_at) : 'Not yet'}</DetailRow>
                <DetailRow label="Finished">{data.finished_at ? formatDateTime(data.finished_at) : live ? 'Still running' : '—'}</DetailRow>
                <DetailRow label="Duration">{jobDuration(data.started_at, data.finished_at, now) ?? '—'}</DetailRow>
                <DetailRow label="Run ID">
                  <span className="break-all font-mono text-[12px]">{data.background_job_id}</span>
                </DetailRow>
              </dl>
            </Panel>
            <Panel id="parameters" title="Parameters">
              <JobParams job={data} />
            </Panel>
          </div>
        </div>
      )}
    </>
  )
}
