// One candidate (LLD §8.2): fields, parse warnings, then the top 10 jobs from GET /candidates/{id}/matches.

import { ArrowLeft, TriangleAlert } from 'lucide-react'
import { Link, useParams } from 'react-router'

import { getCandidate, getCandidateMatches } from '@/api/client'
import { Facts, SkillList } from '@/components/app/data-display'
import { PageHeader } from '@/components/app/PageHeader'
import { Panel } from '@/components/app/Panel'
import { ErrorNotice } from '@/components/app/states'
import { useReloadWhenHealthy } from '@/components/app/system-status'
import { MatchList } from '@/components/matches/MatchList'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useResource } from '@/hooks/useResource'
import { formatDateTime, formatYears } from '@/lib/format'
import { OcrBadge } from '@/components/app/OcrBadge'

const linkClass = 'break-all text-accent-ink underline-offset-4 hover:underline'

export default function CandidateDetailPage() {
  const { id = '' } = useParams()
  const person = useResource((signal) => getCandidate(id, signal), [id])
  const matches = useResource((signal) => getCandidateMatches(id, signal), [id])
  const reloadAll = () => {
    void person.reload()
    void matches.reload()
  }
  useReloadWhenHealthy(reloadAll, Boolean(person.error || matches.error))
  const c = person.data
  const name = c ? (c.name ?? 'Unnamed candidate') : undefined
  useDocumentTitle(name ?? 'Candidate')

  if (person.error && !c) {
    return (
      <>
        <PageHeader title="Candidate" back={{ to: '/candidates', label: 'Candidates' }} />
        <ErrorNotice block error={person.error} onRetry={person.error.status === 404 || person.error.status === 422 ? undefined : reloadAll} retrying={person.refreshing} />
        <Button asChild variant="outline" className="mt-4">
          <Link to="/candidates">
            <ArrowLeft aria-hidden="true" />
            All candidates
          </Link>
        </Button>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title={name ?? <Skeleton className="h-11 w-64" />}
        back={{ to: '/candidates', label: 'Candidates' }}
        titleAddon={c?.parsed_with_ocr && <OcrBadge />}
        description={c && ([c.current_title, c.city, c.years_experience !== null && `${formatYears(c.years_experience)} of experience`].filter(Boolean).join(' · ') || 'Title, city and experience were not found in the resume.')}
      />
      <div className="grid items-start gap-4 lg:grid-cols-3 lg:gap-5">
        <div className="lg:col-span-2">
          {matches.error && !matches.data ? (
            <ErrorNotice error={matches.error} onRetry={() => void matches.reload()} />
          ) : (
            <MatchList title="Top jobs" noun="jobs" loading={matches.loading} computedAt={matches.data?.computed_at} matches={matches.data?.items} />
          )}
        </div>
        <div className="grid gap-4 lg:gap-5">
          {c && c.parse_warnings.length > 0 && (
            <div role="note" aria-label="Parse warnings" className="rounded-xl border border-destructive/25 bg-destructive/[0.05] p-4">
              <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <TriangleAlert className="size-4 text-destructive" aria-hidden="true" />
                Parse warnings
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-6 text-[13px] leading-relaxed text-muted-foreground">
                {c.parse_warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          )}
          <Panel id="profile" title="Profile">
            {c ? (
              <Facts
                items={[
                  ['Email', c.email ? <a href={`mailto:${c.email}`} className={linkClass}>{c.email}</a> : 'Not found'],
                  ['Phone', c.phone ? <a href={`tel:${c.phone}`} className={linkClass}>{c.phone}</a> : 'Not found'],
                  ['City', c.city ?? 'Not found'],
                  ['Current title', c.current_title ?? 'Not found'],
                  ['Experience', c.years_experience === null ? 'Not found' : formatYears(c.years_experience)],
                ]}
              />
            ) : (
              <Skeleton className="h-48" />
            )}
          </Panel>
          <Panel id="candidate-skills" title="Skills">
            {c ? <SkillList skills={c.skills} empty="No skills identified" /> : <Skeleton className="h-16" />}
          </Panel>
          {c?.summary && (
            <Panel id="summary" title="Summary">
              <p className="text-sm leading-relaxed text-muted-foreground">{c.summary}</p>
            </Panel>
          )}
          {c && c.education.length > 0 && (
            <Panel id="education" title="Education">
              <ul className="space-y-3">
                {c.education.map((e, i) => (
                  <li key={i}>
                    <p className="text-sm font-medium text-foreground">{e.degree ?? 'Degree not found'}</p>
                    <p className="text-[13px] text-muted-foreground">{[e.institution, e.years].filter(Boolean).join(' · ')}</p>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
          {c && (
            <Panel id="resume" title="Resume">
              <Facts
                items={[
                  ['Source file', <span className="break-all">{c.source_file}</span>],
                  ['Read with', c.parsed_with_ocr ? 'OCR (scanned PDF)' : 'PDF text'],
                  ['Added', formatDateTime(c.created_at)],
                  ['Updated', formatDateTime(c.updated_at)],
                ]}
              />
            </Panel>
          )}
        </div>
      </div>
    </>
  )
}
