// Candidates (LLD §8.2): searchable, paginated table of parsed resumes, CSV/JSON export, and
// "Export match table" for the same candidates' top 10 jobs (decision LLD-10). Filters live in the address.

import { Search, Users, X } from 'lucide-react'
import { useId } from 'react'
import { Link } from 'react-router'

import { exportUrl, searchCandidates } from '@/api/client'
import { ExportButtons, SkillList } from '@/components/app/data-display'
import { OcrBadge } from '@/components/app/OcrBadge'
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
import { positiveInt, useQueryState } from '@/hooks/useQueryState'
import { useResource } from '@/hooks/useResource'
import { useSkills } from '@/hooks/useSkills'
import { formatYears } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { CandidateFilters, CandidateSort, CandidateSummary, SortOrder } from '@/types/api'

const PAGE_SIZES = [20, 50, 100]
const SORTS: { value: string; label: string; sort?: CandidateSort; order?: SortOrder }[] = [
  { value: 'name', label: 'Name A–Z' },
  { value: 'name-desc', label: 'Name Z–A', sort: 'name', order: 'desc' },
  { value: 'most', label: 'Most experience', sort: 'years_experience' },
  { value: 'least', label: 'Least experience', sort: 'years_experience', order: 'asc' },
]

function Who({ c }: { c: CandidateSummary }) {
  return (
    <div className="min-w-0">
      <Link to={`/candidates/${c.candidate_id}`} className="rounded font-medium text-foreground underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50">
        {c.name ?? 'Unnamed candidate'}
      </Link>
      <p className="mt-0.5 truncate text-[13px] text-muted-foreground">{c.current_title ?? 'Title not found'}</p>
    </div>
  )
}

export default function CandidatesPage() {
  useDocumentTitle('Candidates')
  const skills = useSkills()
  const listId = useId()
  const { get, set } = useQueryState()

  const filters: CandidateFilters = { q: get('q') || undefined, skill: get('skill') || undefined, city: get('city') || undefined }
  const sortKey = SORTS.find((s) => s.sort === (get('sort') || undefined) && s.order === (get('order') || undefined))?.value ?? 'name'
  const sort = SORTS.find((s) => s.value === sortKey)!
  const page = positiveInt(get('page'), 1)
  const pageSize = PAGE_SIZES.includes(Number(get('page_size'))) ? Number(get('page_size')) : 20
  const query = { ...filters, sort: sort.sort, order: sort.order }

  const list = useResource((signal) => searchCandidates({ ...query, page, page_size: pageSize }, signal), [JSON.stringify(query), page, pageSize])
  useReloadWhenHealthy(list.reload, Boolean(list.error))

  const [q, setQ] = useDebouncedParam(get('q'), (v) => set({ q: v }))
  const [skill, setSkill] = useDebouncedParam(get('skill'), (v) => set({ skill: v }))
  const [city, setCity] = useDebouncedParam(get('city'), (v) => set({ city: v }))

  const filtered = Boolean(filters.q || filters.skill || filters.city)
  const clear = () => set({ q: null, skill: null, city: null })
  const people = list.data?.items ?? []

  return (
    <>
      <PageHeader
        title="Candidates"
        description="Parsed resumes. Open one to see its top jobs."
      />

      <div className="mb-4 grid gap-3 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]" role="search" aria-label="Filter candidates">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-subtle-foreground" aria-hidden="true" />
          <Input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name or current title" aria-label="Search name or current title" className="pl-9" />
        </div>
        <Input value={skill} onChange={(e) => setSkill(e.target.value)} placeholder="Skill, e.g. React or reactjs" aria-label="Skill" list={listId} autoComplete="off" />
        <datalist id={listId}>
          {skills.map((s) => (
            <option key={s.skill} value={s.skill} />
          ))}
        </datalist>
        <Input value={city} onChange={(e) => setCity(e.target.value)} placeholder="City, e.g. Bengaluru" aria-label="City" />
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Select
          value={sortKey}
          onValueChange={(v) => {
            const s = SORTS.find((x) => x.value === v)!
            set({ sort: s.sort, order: s.order })
          }}
        >
          <SelectTrigger className="h-9 w-[11rem] rounded-full" aria-label="Sort">
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
        <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-2">
          <ExportButtons label="Export" name="Export these candidates" csv={exportUrl('candidates', 'csv', query)} json={exportUrl('candidates', 'json', query)} />
          <ExportButtons
            label="Match table"
            name="Export their match table (each candidate's top 10 jobs)"
            csv={exportUrl('matches', 'csv', { ...query, top: 10 })}
            json={exportUrl('matches', 'json', { ...query, top: 10 })}
          />
        </div>
      </div>

      {list.error && !list.data ? (
        <ErrorNotice block error={list.error} onRetry={() => void list.reload()} retrying={list.refreshing} />
      ) : (
        <Card className={cn('gap-0 py-0 transition-opacity duration-200', list.refreshing && 'opacity-70')} aria-busy={list.loading || list.refreshing}>
          {list.error && <ErrorNotice error={list.error} onRetry={() => void list.reload()} className="m-4" />}
          {list.loading ? (
            <div className="space-y-5 p-5" aria-label="Loading candidates">
              {Array.from({ length: 8 }, (_, i) => (
                <div key={i} className="grid grid-cols-[2fr_1fr_1fr] items-center gap-6">
                  <div className="space-y-2">
                    <Skeleton className="h-4 w-2/3" />
                    <Skeleton className="h-3 w-1/2" />
                  </div>
                  <Skeleton className="h-3.5 w-1/2" />
                  <Skeleton className="h-6 w-full rounded-full" />
                </div>
              ))}
            </div>
          ) : people.length === 0 ? (
            filtered ? (
              <EmptyState icon={Search} title="No candidates match these filters" description="Try a broader search, another skill spelling, or clear the filters." action={<Button variant="outline" onClick={clear}>Clear filters</Button>} />
            ) : (
              <EmptyState
                icon={Users}
                title="No candidates yet"
                description="Candidates appear here after resumes are uploaded and parsed."
                action={
                  <Button asChild>
                    <Link to="/background-jobs?new=upload">Upload resumes</Link>
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
                      <TableHead className="w-[30%]">Candidate</TableHead>
                      <TableHead>City</TableHead>
                      <TableHead>Experience</TableHead>
                      <TableHead className="w-[34%]">Skills</TableHead>
                      <TableHead>
                        <span className="sr-only">Parsed with OCR</span>
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {people.map((c) => (
                      <TableRow key={c.candidate_id}>
                        <TableCell className="max-w-0">
                          <Who c={c} />
                        </TableCell>
                        <TableCell className="text-[13px] text-muted-foreground">{c.city ?? '—'}</TableCell>
                        <TableCell className="whitespace-nowrap text-[13px] tabular-nums text-muted-foreground">{formatYears(c.years_experience)}</TableCell>
                        <TableCell>
                          <SkillList skills={c.skills} limit={4} />
                        </TableCell>
                        <TableCell className="text-right">{c.parsed_with_ocr && <OcrBadge />}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <ul className="divide-y divide-border lg:hidden">
                {people.map((c) => (
                  <li key={c.candidate_id} className="p-4">
                    <div className="flex items-start justify-between gap-3">
                      <Who c={c} />
                      {c.parsed_with_ocr && <OcrBadge />}
                    </div>
                    <p className="mt-1.5 text-xs text-subtle-foreground">{[c.city, c.years_experience !== null && formatYears(c.years_experience)].filter(Boolean).join(' · ') || 'City and experience not found'}</p>
                    <SkillList skills={c.skills} limit={4} className="mt-2.5" />
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
                  noun={['candidate', 'candidates']}
                />
              </div>
            </>
          )}
        </Card>
      )}
    </>
  )
}
