// Exports: full CSV/JSON downloads of jobs, candidates and the match table (plain links to
// /exports/*). Filtered exports live on the Jobs and Candidates pages.

import { Briefcase, Download, Target, Users, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { exportUrl, listBackgroundJobs, searchCandidates, searchJobs } from '@/api/client'
import { PageHeader } from '@/components/app/PageHeader'
import { Panel } from '@/components/app/Panel'
import { RelativeTime } from '@/components/app/RelativeTime'
import { ErrorNotice } from '@/components/app/states'
import { useReloadWhenHealthy } from '@/components/app/system-status'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useResource } from '@/hooks/useResource'
import { plural } from '@/lib/format'

async function loadCounts(signal: AbortSignal) {
  const [jobs, candidates, match] = await Promise.all([
    searchJobs({ page_size: 1 }, signal),
    searchCandidates({ page_size: 1 }, signal),
    listBackgroundJobs({ type: 'match', status: 'completed', page_size: 1 }, signal),
  ])
  return { jobs: jobs.total, candidates: candidates.total, lastMatch: match.items[0]?.finished_at ?? null }
}

interface ExportCardProps {
  icon: LucideIcon
  title: string
  description: string
  meta: React.ReactNode
  csv: string
  json: string
  children?: React.ReactNode
  /** Where the filtered version of this export lives. */
  filtered?: { to: string; label: string }
}

function ExportCard({ icon: Icon, title, description, meta, csv, json, children, filtered }: ExportCardProps) {
  return (
    <Panel className="h-full" bodyClassName="flex h-full flex-col">
      <span className="grid size-10 place-items-center rounded-full bg-accent-solid/[0.08] text-accent-ink" aria-hidden="true">
        <Icon className="size-5" />
      </span>
      <h2 className="mt-4 font-display text-[1.75rem] font-normal leading-tight text-foreground">{title}</h2>
      <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{description}</p>
      {/* A div, not a p: while loading, `meta` is a Skeleton (a div), which a p may not contain. */}
      <div className="mt-3 text-[13px] text-subtle-foreground">{meta}</div>
      {children}
      <div className="mt-auto pt-6">
        <div className="flex flex-wrap gap-2" role="group" aria-label={`Download ${title.toLowerCase()}`}>
          <Button asChild>
            <a href={csv} download>
              <Download aria-hidden="true" />
              Download CSV
            </a>
          </Button>
          <Button asChild variant="outline">
            <a href={json} download>
              <Download aria-hidden="true" />
              JSON
            </a>
          </Button>
        </div>
        {filtered && (
          <p className="mt-3 text-xs text-subtle-foreground">
            Need only some?{' '}
            <Link to={filtered.to} className="font-medium text-accent-ink underline-offset-4 hover:underline">
              {filtered.label}
            </Link>
          </p>
        )}
      </div>
    </Panel>
  )
}

export default function ExportsPage() {
  useDocumentTitle('Exports')
  const counts = useResource(loadCounts, [])
  useReloadWhenHealthy(counts.reload, Boolean(counts.error))
  const [top, setTop] = useState('10')
  const c = counts.data
  const meta = (n: number | undefined, one: string) => (c ? plural(n ?? 0, one) : <Skeleton className="inline-block h-3 w-20 align-middle" />)

  return (
    <>
      <PageHeader title="Exports" description="Download everything as CSV or JSON. To export only what a filter shows, use the export buttons on the Jobs or Candidates page." />
      {counts.error && <ErrorNotice error={counts.error} onRetry={() => void counts.reload()} className="mb-5" />}
      <div className="grid gap-4 md:grid-cols-3 lg:gap-5">
        <ExportCard
          icon={Briefcase}
          title="Jobs"
          description="Every crawled posting with its company, location, type, salary, dates, skills and source."
          meta={meta(c?.jobs, 'job')}
          csv={exportUrl('jobs', 'csv')}
          json={exportUrl('jobs', 'json')}
          filtered={{ to: '/jobs', label: 'Filter on the Jobs page' }}
        />
        <ExportCard
          icon={Users}
          title="Candidates"
          description="Every parsed resume: name, contact details, city, title, experience, education and skills."
          meta={meta(c?.candidates, 'candidate')}
          csv={exportUrl('candidates', 'csv')}
          json={exportUrl('candidates', 'json')}
          filtered={{ to: '/candidates', label: 'Filter on the Candidates page' }}
        />
        <ExportCard
          icon={Target}
          title="Match table"
          description="Each candidate’s top jobs with the score, matched and missing skills, the points of each part and the explanation."
          meta={c ? c.lastMatch ? <>From the match run <RelativeTime value={c.lastMatch} /></> : 'No match run yet, so the table is empty.' : <Skeleton className="inline-block h-3 w-32 align-middle" />}
          csv={exportUrl('matches', 'csv', { top: Number(top) })}
          json={exportUrl('matches', 'json', { top: Number(top) })}
          filtered={{ to: '/candidates', label: 'Choose candidates on the Candidates page' }}
        >
          <div className="mt-4 flex items-center gap-2">
            <span className="text-[13px] text-muted-foreground" id="top-label">
              Jobs per candidate
            </span>
            <Select value={top} onValueChange={setTop}>
              <SelectTrigger className="h-8 w-20" aria-labelledby="top-label">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Array.from({ length: 10 }, (_, i) => String(i + 1)).map((n) => (
                  <SelectItem key={n} value={n}>
                    {n}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </ExportCard>
      </div>
      <Panel className="mt-5" title="About the files">
        <ul className="grid gap-2 text-[13px] leading-relaxed text-muted-foreground sm:grid-cols-2">
          <li>Files are named after what they hold and when, for example <span className="font-mono text-[12px] text-foreground">jobs_2026-11-21T12-00-00Z.csv</span>.</li>
          <li>CSV text that a spreadsheet would run as a formula starts with an apostrophe, so it stays text. Numbers are never changed.</li>
          <li>JSON holds the same rows as a list of objects, with numbers as numbers.</li>
          <li>The match table uses the stored results of the last completed match run.</li>
        </ul>
      </Panel>
    </>
  )
}
