// The top 10 matches of a job or a candidate (LLD §8.6): in the API's order with the API's ranks,
// the 2-decimal score as sent, matched and missing skills with their level, the explanation, and
// text similarity labelled as a tie-breaker. Scores are never re-sorted or recomputed here.

import { ChevronDown, Target } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Panel } from '@/components/app/Panel'
import { RelativeTime } from '@/components/app/RelativeTime'
import { EmptyState } from '@/components/app/states'
import { ComponentBar } from '@/components/landing/ScoreBar'
import { SkillChip } from '@/components/landing/SkillChip'
import { Button } from '@/components/ui/button'
import { formatNumber } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Breakdown, CandidateMatch, JobMatch, SkillLevel, SkillRef } from '@/types/api'

const LEVEL_LABEL: Record<SkillLevel, string> = { required: 'Required', nice_to_have: 'Nice-to-have' }
const two = (n: number) => n.toFixed(2)

function SkillsByLevel({ matched, missing }: { matched: SkillRef[]; missing: SkillRef[] }) {
  return (
    <div className="grid gap-2">
      {(['required', 'nice_to_have'] as const).map((level) => {
        const has = matched.filter((s) => s.level === level)
        const lacks = missing.filter((s) => s.level === level)
        return (
          <div key={level} className="grid gap-1.5 sm:grid-cols-[6.5rem_minmax(0,1fr)] sm:items-start">
            <p className="pt-0.5 text-xs font-medium text-subtle-foreground">{LEVEL_LABEL[level]}</p>
            {has.length + lacks.length === 0 ? (
              <p className="text-[13px] text-subtle-foreground">None listed for this job</p>
            ) : (
              <ul className="flex flex-wrap gap-1.5" aria-label={`${LEVEL_LABEL[level]} skills`}>
                {has.map((s) => (
                  <li key={s.skill}>
                    <SkillChip name={s.skill} kind="matched" />
                  </li>
                ))}
                {lacks.map((s) => (
                  <li key={s.skill}>
                    <SkillChip name={s.skill} kind="missing" />
                  </li>
                ))}
              </ul>
            )}
          </div>
        )
      })}
    </div>
  )
}

const SKILL_RULE: Record<string, string> = {
  none_listed: 'The job lists no nice-to-have skills, so this part gets full points.',
  no_required_identified: 'No required skills were identified for this job, so this part gets 0 points.',
  no_skills_identified: 'No skills could be identified for this job, so this part gets 0 points.',
}
const EXPERIENCE_RULE: Record<string, string> = {
  no_minimum: 'The job states no minimum, so this part gets full points.',
  years_unknown: 'The candidate’s years of experience are unknown, so this part gets 0 points.',
}
const LOCATION_RULE: Record<string, string> = {
  remote: 'Remote role.',
  same_city: 'Same city.',
  different_city: 'Different cities.',
  candidate_city_unknown: 'The candidate’s city is unknown.',
  job_city_unknown: 'No city could be found in the job’s location.',
}

/** The four components as the API computed them: fit (bar), points and the rule that applied. */
function ScoreBreakdown({ breakdown }: { breakdown: Breakdown }) {
  const { required: r, nice_to_have: n, experience: e, location: l } = breakdown
  const rows = [
    { label: 'Required skills', fit: r.ratio, detail: `${r.matched} of ${r.total} · ${two(r.points)} points`, note: SKILL_RULE[r.rule] },
    { label: 'Nice-to-have skills', fit: n.ratio, detail: `${n.matched} of ${n.total} · ${two(n.points)} points`, note: SKILL_RULE[n.rule] },
    {
      label: 'Experience',
      fit: e.fit,
      detail: `${
        e.minimum === null
          ? `${e.candidate_years === null ? 'Years unknown' : `${e.candidate_years} yrs`}, no minimum`
          : `${e.candidate_years ?? '?'} of ${e.minimum} yrs`
      } · ${two(e.points)} points`,
      note: EXPERIENCE_RULE[e.rule],
    },
    {
      label: 'Location',
      fit: l.fit,
      detail: `${two(l.points)} points`,
      note: `${LOCATION_RULE[l.rule] ?? ''} ${[l.candidate_city && `Candidate: ${l.candidate_city}.`, l.job_location && `Job: ${l.job_location}.`].filter(Boolean).join(' ')}`.trim(),
    },
  ]
  return (
    <div className="grid gap-4 rounded-lg bg-foreground/[0.03] p-4">
      {rows.map((row) => (
        <div key={row.label}>
          <ComponentBar label={row.label} detail={row.detail} fit={Math.max(0, Math.min(1, row.fit))} color="var(--primary)" />
          {row.note && <p className="mt-1.5 text-xs leading-relaxed text-subtle-foreground">{row.note}</p>}
        </div>
      ))}
    </div>
  )
}

type AnyMatch = JobMatch | CandidateMatch

function MatchCard({ match }: { match: AnyMatch }) {
  const [open, setOpen] = useState(false)
  const isJob = 'job_id' in match
  const to = isJob ? `/jobs/${match.job_id}` : `/candidates/${match.candidate_id}`
  const title = isJob ? match.title : (match.name ?? 'Unnamed candidate')
  const subtitle = isJob ? match.company : [match.current_title, match.city].filter(Boolean).join(' · ')
  const breakdownId = `breakdown-${isJob ? match.job_id : match.candidate_id}`
  return (
    <li className="py-5 first:pt-1 last:pb-1">
      <div className="flex items-start gap-4">
        <span className="w-7 shrink-0 pt-0.5 text-right font-display text-2xl leading-none text-subtle-foreground">
          <span aria-hidden="true">{match.rank}</span>
          <span className="sr-only">Rank {match.rank}</span>
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
            <div className="min-w-0">
              <Link to={to} className="rounded text-[15px] font-semibold text-foreground underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50">
                {title}
              </Link>
              {subtitle && <p className="mt-0.5 text-[13px] text-muted-foreground">{subtitle}</p>}
            </div>
            <p className="text-right">
              <span className="sr-only">Score </span>
              <span className="font-display text-[2rem] leading-none text-foreground">{two(match.score)}</span>
              <span className="ml-1 text-xs text-subtle-foreground">
                <span aria-hidden="true">/ 100</span>
                <span className="sr-only"> out of 100</span>
              </span>
            </p>
          </div>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-primary/[0.13]" aria-hidden="true">
            <div className="h-full rounded-full bg-primary" style={{ width: `${Math.max(0, Math.min(100, match.score))}%` }} />
          </div>
          <div className="mt-4">
            <SkillsByLevel matched={match.matched_skills} missing={match.missing_skills} />
          </div>
          <p className="mt-3 text-[13px] leading-relaxed text-muted-foreground">{match.explanation}</p>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-subtle-foreground">
              Text similarity {match.text_similarity === null ? '—' : two(match.text_similarity)}
              <span> · used to order equal scores</span>
            </p>
            <Button variant="ghost" size="xs" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls={breakdownId}>
              Score breakdown
              <ChevronDown className={cn('transition-transform duration-200', open && 'rotate-180')} aria-hidden="true" />
            </Button>
          </div>
          {open && (
            <div id={breakdownId} className="mt-3">
              <ScoreBreakdown breakdown={match.breakdown} />
            </div>
          )}
        </div>
      </div>
    </li>
  )
}

interface MatchListProps {
  title: string
  computedAt?: string | null
  matches?: AnyMatch[]
  /** What the other side is called: "candidates" for a job, "jobs" for a candidate. */
  noun: 'candidates' | 'jobs'
  loading?: boolean
  className?: string
}

export function MatchList({ title, computedAt, matches, noun, loading, className }: MatchListProps) {
  return (
    <Panel
      id="matches"
      className={className}
      title={title}
      description={
        computedAt ? (
          <>
            From the last match run, <RelativeTime value={computedAt} /> · best first
          </>
        ) : loading ? (
          'Loading…'
        ) : (
          'Not computed yet'
        )
      }
    >
      {loading ? (
        <div className="space-y-6 py-2" aria-hidden="true">
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className="flex gap-4">
              <div className="h-6 w-7 rounded bg-foreground/[0.07]" />
              <div className="flex-1 space-y-2.5">
                <div className="h-4 w-1/3 animate-pulse rounded bg-foreground/[0.07]" />
                <div className="h-1.5 animate-pulse rounded bg-foreground/[0.07]" />
                <div className="h-3 w-2/3 animate-pulse rounded bg-foreground/[0.07]" />
              </div>
            </div>
          ))}
        </div>
      ) : !computedAt ? (
        <EmptyState
          compact
          icon={Target}
          title="Matches not computed yet"
          description={`No match run has included this ${noun === 'candidates' ? 'job' : 'candidate'} yet. Recompute matches to score every candidate against every job.`}
          action={
            <Button asChild size="sm">
              <Link to="/background-jobs?new=match">Recompute matches</Link>
            </Button>
          }
        />
      ) : !matches?.length ? (
        <EmptyState compact icon={Target} title={`No ${noun} to show`} description={`The last match run had no ${noun} to score against.`} />
      ) : (
        <>
          <ol className="divide-y divide-border">
            {matches.map((m) => (
              <MatchCard key={'job_id' in m ? m.job_id : m.candidate_id} match={m} />
            ))}
          </ol>
          <p className="mt-2 text-xs text-subtle-foreground">
            Showing the top {formatNumber(matches.length)} in the order the API ranks them.
          </p>
        </>
      )}
    </Panel>
  )
}
