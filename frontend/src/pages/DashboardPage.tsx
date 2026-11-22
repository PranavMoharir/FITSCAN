// Dashboard at /app, the application entry (Phase 7B.1). Every number comes from the API; when a
// request fails the value shows as a dash, never as a made-up zero.

import { Briefcase, Tags, Users, Workflow } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { LiveIndicator } from '@/components/app/LiveIndicator'
import { MetricCard } from '@/components/app/MetricCard'
import { PageHeader } from '@/components/app/PageHeader'
import { ErrorNotice } from '@/components/app/states'
import { SystemStatusCard, useReloadWhenHealthy, useSystemStatus } from '@/components/app/system-status'
import { loadActivity, loadTotals } from '@/components/dashboard/data'
import { GettingStarted, JobStatusOverview, PipelineCard, RecentActivity } from '@/components/dashboard/panels'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { usePolling } from '@/hooks/usePolling'
import { useResource } from '@/hooks/useResource'
import { POLL_INTERVAL_MS } from '@/lib/app'
import { formatNumber, plural } from '@/lib/format'

export default function DashboardPage() {
  useDocumentTitle('Dashboard')
  const totals = useResource(loadTotals, [])
  const activity = useResource(loadActivity, [])
  const { refresh: refreshHealth } = useSystemStatus()

  const counts = activity.data?.counts
  const activeCount = counts ? counts.running + counts.queued : 0
  const live = activeCount > 0
  usePolling(activity.reload, POLL_INTERVAL_MS, live)

  // When the last active run finishes, the totals may have changed (a crawl adds jobs).
  const wasLive = useRef(false)
  const reloadTotals = totals.reload
  useEffect(() => {
    if (wasLive.current && !live) void reloadTotals()
    wasLive.current = live
  }, [live, reloadTotals])

  const [updatedAt, setUpdatedAt] = useState<Date>()
  useEffect(() => {
    if (activity.data) setUpdatedAt(new Date())
  }, [activity.data])

  const refreshAll = () => {
    void totals.reload()
    void activity.reload()
    void refreshHealth()
  }

  const error = activity.error ?? totals.error
  useReloadWhenHealthy(refreshAll, Boolean(error))
  const t = totals.data
  const value = (n: number | null | undefined) => (totals.loading ? undefined : t ? n : null)

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Jobs, candidates and background work at a glance."
        actions={<LiveIndicator live={live} updatedAt={updatedAt} refreshing={totals.refreshing || activity.refreshing} onRefresh={refreshAll} />}
      />

      {error && <ErrorNotice error={error} onRetry={refreshAll} retrying={totals.refreshing || activity.refreshing} className="mb-6" />}

      <section aria-label="Totals" className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <MetricCard
          label="Jobs"
          icon={Briefcase}
          to="/jobs"
          value={value(t?.jobs)}
          hint={t && t.realJobs !== null && t.demoJobs !== null ? `${formatNumber(t.realJobs)} real · ${formatNumber(t.demoJobs)} demo` : 'Crawled job postings'}
        />
        <MetricCard label="Candidates" icon={Users} to="/candidates" value={value(t?.candidates)} hint="Parsed resumes" />
        <MetricCard
          label="Skills"
          icon={Tags}
          to="/skills"
          value={value(t?.skills)}
          hint={t?.categories ? `In ${plural(t.categories, 'category', 'categories')}` : 'Canonical skill list'}
        />
        <MetricCard
          label="Active background jobs"
          icon={Workflow}
          to="/background-jobs"
          value={activity.loading ? undefined : counts ? activeCount : null}
          hint={counts ? (live ? `${counts.running} running · ${counts.queued} queued` : 'Nothing running') : undefined}
        />
      </section>

      {t && activity.data && (
        <div className="mt-6">
          <GettingStarted jobs={t.jobs} candidates={t.candidates} matched={activity.data.lastCompleted.match !== null} />
        </div>
      )}

      <div className="mt-6 grid items-start gap-4 lg:grid-cols-3 lg:gap-5">
        <div className="grid gap-4 lg:col-span-2 lg:gap-5">
          <JobStatusOverview data={activity.data} />
          <RecentActivity data={activity.data} />
        </div>
        <div className="grid gap-4 lg:gap-5">
          <PipelineCard data={activity.data} />
          <SystemStatusCard />
        </div>
      </div>
    </>
  )
}
