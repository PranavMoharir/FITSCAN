// One job (LLD §8.2): its fields, its source (real or demo listing) and industry with the evidence
// (LLD §5.16-5.18), then its top 10 candidates from GET /jobs/{id}/matches.

import { ArrowLeft, ArrowUpRight } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { getJob, getJobMatches } from '@/api/client'
import { DemoBadge, Facts, SkillList } from '@/components/app/data-display'
import { PageHeader } from '@/components/app/PageHeader'
import { Panel } from '@/components/app/Panel'
import { ErrorNotice } from '@/components/app/states'
import { useReloadWhenHealthy } from '@/components/app/system-status'
import { MatchList } from '@/components/matches/MatchList'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useResource } from '@/hooks/useResource'
import { sourceLabel, useSources } from '@/hooks/useSources'
import { formatDate, formatDateTime, formatSalary, hostOf, INDUSTRY_LABEL, JOB_TYPE_LABEL, jobTypeText } from '@/lib/format'
import type { JobView, SourceInfo } from '@/types/api'

function Description({ text }: { text: string }) {
  const long = text.length > 700
  const [open, setOpen] = useState(!long)
  return (
    <div>
      <p className={open ? 'whitespace-pre-line text-sm leading-relaxed text-muted-foreground' : 'line-clamp-[9] whitespace-pre-line text-sm leading-relaxed text-muted-foreground'}>{text}</p>
      {long && (
        <Button variant="link" size="xs" className="mt-2 h-auto px-0" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          {open ? 'Show less' : 'Show the full description'}
        </Button>
      )}
    </div>
  )
}

function JobFacts({ job }: { job: JobView }) {
  return (
    <Facts
      items={[
        ['Salary', formatSalary(job.salary, job.salary_text) ?? 'Not stated'],
        ['Job type', JOB_TYPE_LABEL[job.job_type]],
        ['Remote', job.is_remote ? 'Yes' : 'No'],
        ['Experience', job.min_experience_years === null ? 'Not stated' : job.min_experience_years === 0 ? 'No minimum' : `At least ${job.min_experience_years} years`],
        ['Posted', formatDate(job.posted_date)],
        ['Industry', INDUSTRY_LABEL[job.industry]],
        ['Added', formatDateTime(job.created_at)],
        ['Updated', formatDateTime(job.updated_at)],
      ]}
    />
  )
}

function ExternalLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="inline-flex max-w-full items-center gap-1 break-all rounded text-accent-ink underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50">
      {children}
      <ArrowUpRight className="size-3.5 shrink-0" aria-hidden="true" />
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  )
}

/** Where the job comes from: a real company source, or a demo site whose jobs are invented. */
function JobSource({ job, sources }: { job: JobView; sources: SourceInfo[] }) {
  const demo = job.listing === 'demo'
  return (
    <div className="grid gap-3">
      <p className="flex flex-wrap items-center gap-2 text-sm text-foreground">
        {demo ? <DemoBadge /> : null}
        {demo ? 'An invented job from a demo site. It is not a real opening.' : 'A real listing, collected from the source below.'}
      </p>
      <Facts
        items={[
          ['Source', sourceLabel(sources, job.source)],
          ['Read from', job.source_url ? <ExternalLink href={job.source_url}>{hostOf(job.source_url) ?? job.source_url}</ExternalLink> : 'Not recorded'],
          [demo ? 'Demo posting' : 'Original posting', <ExternalLink href={job.apply_url}>{hostOf(job.apply_url) ?? job.apply_url}</ExternalLink>],
        ]}
      />
    </div>
  )
}

/** The industry and the evidence for it (title terms, skills, description terms), or why there is none. */
function JobIndustry({ job }: { job: JobView }) {
  return (
    <div>
      <p className="text-sm font-medium text-foreground">{INDUSTRY_LABEL[job.industry]}</p>
      <ul className="mt-2 grid gap-1 text-[13px] leading-relaxed text-muted-foreground">
        {job.industry_reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
      <p className="mt-3 text-xs leading-relaxed text-subtle-foreground">
        From the title, skills and description. The industry helps you browse; it never changes a match score.
      </p>
    </div>
  )
}

export default function JobDetailPage() {
  const { id = '' } = useParams()
  const job = useResource((signal) => getJob(id, signal), [id])
  const matches = useResource((signal) => getJobMatches(id, signal), [id])
  const sources = useSources()
  const reloadAll = () => {
    void job.reload()
    void matches.reload()
  }
  useReloadWhenHealthy(reloadAll, Boolean(job.error || matches.error))
  const data = job.data
  useDocumentTitle(data?.title ?? 'Job')

  if (job.error && !data) {
    return (
      <>
        <PageHeader title="Job" back={{ to: '/jobs', label: 'Jobs' }} />
        <ErrorNotice block error={job.error} onRetry={job.error.status === 404 || job.error.status === 422 ? undefined : reloadAll} retrying={job.refreshing} />
        <Button asChild variant="outline" className="mt-4">
          <Link to="/jobs">
            <ArrowLeft aria-hidden="true" />
            All jobs
          </Link>
        </Button>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title={data ? data.title : <Skeleton className="h-11 w-72" />}
        back={{ to: '/jobs', label: 'Jobs' }}
        titleAddon={
          data && (data.is_remote || data.listing === 'demo') ? (
            <span className="flex flex-wrap items-center gap-2">
              {data.listing === 'demo' && <DemoBadge className="h-6 px-2.5 text-xs" />}
              {data.is_remote && <Badge variant="outline" className="h-6 border-foreground/20 px-2.5 text-muted-foreground">Remote</Badge>}
            </span>
          ) : undefined
        }
        description={data && [data.company ?? 'Company not stated', data.location, jobTypeText(data.job_type)].filter(Boolean).join(' · ')}
        actions={
          data && (
            <Button asChild variant="outline">
              <a href={data.apply_url} target="_blank" rel="noreferrer">
                {data.listing === 'demo' ? 'Open the demo posting' : 'Open the original posting'}
                <ArrowUpRight aria-hidden="true" />
                <span className="sr-only">(opens in a new tab)</span>
              </a>
            </Button>
          )
        }
      />
      <div className="grid items-start gap-4 lg:grid-cols-3 lg:gap-5">
        <div className="lg:col-span-2">
          {matches.error && !matches.data ? (
            <ErrorNotice error={matches.error} onRetry={() => void matches.reload()} />
          ) : (
            <MatchList title="Top candidates" noun="candidates" loading={matches.loading} computedAt={matches.data?.computed_at} matches={matches.data?.items} />
          )}
        </div>
        <div className="grid gap-4 lg:gap-5">
          <Panel id="job-facts" title="About this job">
            {data ? <JobFacts job={data} /> : <Skeleton className="h-64" />}
          </Panel>
          <Panel id="job-skills" title="Skills">
            {data ? (
              <div className="grid gap-4">
                <div>
                  <p className="mb-2 text-xs font-medium text-subtle-foreground">Required</p>
                  <SkillList skills={data.required_skills} empty="None identified" />
                </div>
                <div>
                  <p className="mb-2 text-xs font-medium text-subtle-foreground">Nice-to-have</p>
                  <SkillList skills={data.nice_to_have_skills} empty="None listed" />
                </div>
              </div>
            ) : (
              <Skeleton className="h-20" />
            )}
          </Panel>
          <Panel id="job-industry" title="Industry">
            {data ? <JobIndustry job={data} /> : <Skeleton className="h-20" />}
          </Panel>
          <Panel id="job-source" title="Source">
            {data ? <JobSource job={data} sources={sources} /> : <Skeleton className="h-28" />}
          </Panel>
          {data?.description && (
            <Panel id="job-description" title="Description">
              <Description text={data.description} />
            </Panel>
          )}
        </div>
      </div>
    </>
  )
}
