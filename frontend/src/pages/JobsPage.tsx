// Jobs (LLD §8.2): searchable, paginated table of crawled postings with CSV/JSON export using the
// same filters ("what you see is what you export", LLD §4.5). Filters live in the address.

import { Briefcase, Search, X } from 'lucide-react'
import { useId } from 'react'
import { Link } from 'react-router'

import { exportUrl, searchJobs } from '@/api/client'
import { ExportButtons, SkillList } from '@/components/app/data-display'
import { PageHeader } from '@/components/app/PageHeader'
import { Pagination } from '@/components/app/Pagination'
import { EmptyState, ErrorNotice } from '@/components/app/states'
import { useReloadWhenHealthy } from '@/components/app/system-status'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useDebouncedParam } from '@/hooks/useDebouncedParam'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { oneOf, positiveInt, useQueryState } from '@/hooks/useQueryState'
import { useResource } from '@/hooks/useResource'
import { useSkills } from '@/hooks/useSkills'
import { formatDate, JOB_TYPE_LABEL, jobTypeText } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { JobFilters, JobSort, JobSummary, JobType, SortOrder } from '@/types/api'

const JOB_TYPES = Object.keys(JOB_TYPE_LABEL) as JobType[]
const PAGE_SIZES = [20, 50, 100]
const SORTS: { value: string; label: string; sort?: JobSort; order?: SortOrder }[] = [
  { value: 'newest', label: 'Newest posted' },
  { value: 'oldest', label: 'Oldest posted', sort: 'posted_date', order: 'asc' },
  { value: 'title', label: 'Title A–Z', sort: 'title' },
  { value: 'title-desc', label: 'Title Z–A', sort: 'title', order: 'desc' },
]

/** `inLine`: shown in a list line without the "Experience" column header, so it names itself. */
const experience = (years: number | null, inLine = false) =>
  years === null ? (inLine ? 'Experience not stated' : 'Not stated') : years === 0 ? 'No minimum' : `${years}+ yrs`

function JobCells({ job }: { job: JobSummary }) {
  return (
    <div className="min-w-0">
      <Link to={`/jobs/${job.job_id}`} className="rounded font-medium text-foreground underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50">
        {job.title}
      </Link>
      <p className="mt-0.5 truncate text-[13px] text-muted-foreground">{job.company ?? 'Company not stated'}</p>
    </div>
  )
}

export default function JobsPage() {
  useDocumentTitle('Jobs')
  const skills = useSkills()
  const listId = useId()
  const { get, set } = useQueryState()

  const filters: JobFilters = {
    q: get('q') || undefined,
    skill: get('skill') || undefined,
    location: get('location') || undefined,
    job_type: oneOf(get('job_type'), JOB_TYPES),
    max_required_years: get('max_required_years') !== '' && Number(get('max_required_years')) >= 0 ? Number(get('max_required_years')) : undefined,
  }
  const sortKey = SORTS.find((s) => s.sort === (get('sort') || undefined) && s.order === (get('order') || undefined))?.value ?? 'newest'
  const sort = SORTS.find((s) => s.value === sortKey)!
  const page = positiveInt(get('page'), 1)
  const pageSize = PAGE_SIZES.includes(Number(get('page_size'))) ? Number(get('page_size')) : 20
  const query = { ...filters, sort: sort.sort, order: sort.order }

  const list = useResource((signal) => searchJobs({ ...query, page, page_size: pageSize }, signal), [JSON.stringify(query), page, pageSize])
  useReloadWhenHealthy(list.reload, Boolean(list.error))

  const [q, setQ] = useDebouncedParam(get('q'), (v) => set({ q: v }))
  const [skill, setSkill] = useDebouncedParam(get('skill'), (v) => set({ skill: v }))
  const [location, setLocation] = useDebouncedParam(get('location'), (v) => set({ location: v }))
  const [years, setYears] = useDebouncedParam(get('max_required_years'), (v) => set({ max_required_years: v }))

  const filtered = Boolean(filters.q || filters.skill || filters.location || filters.job_type || filters.max_required_years !== undefined)
  const clear = () => set({ q: null, skill: null, location: null, job_type: null, max_required_years: null })
  const jobs = list.data?.items ?? []

  return (
    <>
      <PageHeader
        title="Jobs"
        description="Crawled job postings. Open one to see its top candidates."
      />

      <div className="mb-4 grid gap-3 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]" role="search" aria-label="Filter jobs">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-subtle-foreground" aria-hidden="true" />
          <Input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title or company" aria-label="Search title or company" className="pl-9" />
        </div>
        <Input value={skill} onChange={(e) => setSkill(e.target.value)} placeholder="Skill, e.g. Python or js" aria-label="Skill" list={listId} autoComplete="off" />
        <datalist id={listId}>
          {skills.map((s) => (
            <option key={s.skill} value={s.skill} />
          ))}
        </datalist>
        <Input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Location, e.g. Pune" aria-label="Location" />
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Select value={filters.job_type ?? 'all'} onValueChange={(v) => set({ job_type: v === 'all' ? null : v })}>
          <SelectTrigger className="h-9 w-[10.5rem] rounded-full" aria-label="Job type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All job types</SelectItem>
            {JOB_TYPES.map((t) => (
              <SelectItem key={t} value={t}>
                {jobTypeText(t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <label className="flex h-9 items-center gap-2 rounded-full border border-input bg-card pl-3.5 pr-1 text-[13px] text-muted-foreground focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/15">
          Asks at most
          <input
            type="number"
            inputMode="decimal"
            min={0}
            max={50}
            value={years}
            onChange={(e) => setYears(e.target.value)}
            className="h-7 w-14 rounded-full bg-transparent px-2 text-base text-foreground outline-none placeholder:text-subtle-foreground md:text-sm"
            aria-label="Maximum years of experience required"
            placeholder="any"
          />
          <span className="pr-2.5">yrs</span>
        </label>
        <Select value={sortKey} onValueChange={(v) => { const s = SORTS.find((x) => x.value === v)!; set({ sort: s.sort, order: s.order }) }}>
          <SelectTrigger className="h-9 w-[10.5rem] rounded-full" aria-label="Sort">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SORTS.map((s) => (
              <SelectItem key={s.value} value={s.value}>
                {s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {filtered && (
          <Button variant="ghost" size="sm" onClick={clear}>
            <X aria-hidden="true" />
            Clear filters
          </Button>
        )}
        <ExportButtons className="ml-auto" label="Export" name="Export these jobs" csv={exportUrl('jobs', 'csv', query)} json={exportUrl('jobs', 'json', query)} />
      </div>

      {list.error && !list.data ? (
        <ErrorNotice block error={list.error} onRetry={() => void list.reload()} retrying={list.refreshing} />
      ) : (
        <Card className={cn('gap-0 py-0 transition-opacity duration-200', list.refreshing && 'opacity-70')} aria-busy={list.loading || list.refreshing}>
          {list.error && <ErrorNotice error={list.error} onRetry={() => void list.reload()} className="m-4" />}
          {list.loading ? (
            <div className="space-y-5 p-5" aria-label="Loading jobs">
              {Array.from({ length: 8 }, (_, i) => (
                <div key={i} className="grid grid-cols-[2fr_1fr_1fr] items-center gap-6">
                  <div className="space-y-2">
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-3 w-1/2" />
                  </div>
                  <Skeleton className="h-3.5 w-2/3" />
                  <Skeleton className="h-6 w-full rounded-full" />
                </div>
              ))}
            </div>
          ) : jobs.length === 0 ? (
            filtered ? (
              <EmptyState icon={Search} title="No jobs match these filters" description="Try a broader search, another skill spelling, or clear the filters." action={<Button variant="outline" onClick={clear}>Clear filters</Button>} />
            ) : (
              <EmptyState
                icon={Briefcase}
                title="No jobs yet"
                description="Jobs appear here after a crawl collects postings from a careers site."
                action={
                  <Button asChild>
                    <Link to="/background-jobs?new=crawl">Start a crawl</Link>
                  </Button>
                }
              />
            )
          ) : (
            <>
              <div className="hidden lg:block">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="w-[30%]">Job</TableHead>
                      <TableHead>Location</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Posted</TableHead>
                      <TableHead>Experience</TableHead>
                      <TableHead className="w-[28%]">Required skills</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {jobs.map((job) => (
                      <TableRow key={job.job_id}>
                        <TableCell className="max-w-0">
                          <JobCells job={job} />
                        </TableCell>
                        <TableCell className="text-[13px] text-muted-foreground">{job.location ?? '—'}</TableCell>
                        <TableCell className="whitespace-nowrap text-[13px] text-muted-foreground">{JOB_TYPE_LABEL[job.job_type]}</TableCell>
                        <TableCell className="whitespace-nowrap text-[13px] tabular-nums text-muted-foreground">{formatDate(job.posted_date)}</TableCell>
                        <TableCell className="whitespace-nowrap text-[13px] text-muted-foreground">{experience(job.min_experience_years)}</TableCell>
                        <TableCell>
                          <SkillList skills={job.required_skills} limit={3} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <ul className="divide-y divide-border lg:hidden">
                {jobs.map((job) => (
                  <li key={job.job_id} className="p-4">
                    <JobCells job={job} />
                    <p className="mt-1.5 text-xs text-subtle-foreground">
                      {[job.location, jobTypeText(job.job_type), job.posted_date && `Posted ${formatDate(job.posted_date)}`, experience(job.min_experience_years, true)].filter(Boolean).join(' · ')}
                    </p>
                    <SkillList skills={job.required_skills} limit={4} className="mt-2.5" />
                  </li>
                ))}
              </ul>
              <div className="border-t border-border px-5 py-3">
                <Pagination
                  page={page}
                  pageSize={pageSize}
                  total={list.data?.total ?? 0}
                  onPage={(p) => set({ page: p > 1 ? p : null })}
                  pageSizes={PAGE_SIZES}
                  onPageSize={(size) => set({ page_size: size === 20 ? null : size })}
                  noun={['job', 'jobs']}
                />
              </div>
            </>
          )}
        </Card>
      )}
    </>
  )
}
