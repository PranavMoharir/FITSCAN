import { ArrowRight, Briefcase, FileText, GraduationCap, MapPin } from 'lucide-react'

import { ComponentBar, ScoreBar } from '@/components/landing/ScoreBar'
import { SkillChip } from '@/components/landing/SkillChip'
import { formatPercent, formatScore, type DemoCandidate, type DemoJob, type DemoMatch } from '@/lib/demo-matches'
import { cn } from '@/lib/utils'

export type ShowcaseTab = 'candidates' | 'jobs' | 'matches'
export type Accent = 'violet' | 'blue' | 'emerald'
export type Density = 'compact' | 'comfortable' | 'detailed'
export type Display = 'skills' | 'explanation'

export const ACCENTS: Record<Accent, { label: string; solid: string; soft: string; tint: string }> = {
  violet: { label: 'Violet', solid: '#7c5cff', soft: '#a594ff', tint: 'rgb(124 92 255 / 0.16)' },
  blue: { label: 'Blue', solid: '#3b82f6', soft: '#93c5fd', tint: 'rgb(59 130 246 / 0.16)' },
  emerald: { label: 'Emerald', solid: '#10b981', soft: '#6ee7b7', tint: 'rgb(16 185 129 / 0.16)' },
}

/** Bar colours inside the demo follow the chosen accent. */
export const DEMO_BAR_COLORS = [
  'var(--demo-accent)',
  'var(--demo-accent-soft)',
  'color-mix(in oklab, var(--demo-accent) 45%, white)',
  'rgb(255 255 255 / 0.5)',
] as const

const DENSITY: Record<Density, { body: string; title: string; chips: number; rows: number; extra: boolean }> = {
  compact: { body: 'gap-4 p-4 text-[13px]', title: 'text-base', chips: 4, rows: 3, extra: false },
  comfortable: { body: 'gap-6 p-5 text-sm sm:p-6', title: 'text-lg', chips: 6, rows: 4, extra: false },
  detailed: { body: 'gap-6 p-5 text-sm sm:p-6', title: 'text-lg', chips: 99, rows: 4, extra: true },
}

interface ViewProps {
  density: Density
  display: Display
}

function Label({ children }: { children: string }) {
  return <h4 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle-foreground">{children}</h4>
}

function Chips({ skills, kind, limit }: { skills: string[]; kind: 'matched' | 'missing' | 'neutral'; limit: number }) {
  const shown = skills.slice(0, limit)
  return (
    <ul className="flex flex-wrap gap-1.5">
      {shown.map((skill) => (
        <li key={skill}>
          <SkillChip name={skill} kind={kind} />
        </li>
      ))}
      {skills.length > shown.length && <li className="self-center text-xs text-subtle-foreground">+{skills.length - shown.length} more</li>}
    </ul>
  )
}

function Score({ value, className }: { value: number; className?: string }) {
  return <span className={cn('font-semibold tabular-nums', className)}>{formatScore(value)}</span>
}

function Points({ match }: { match: DemoMatch }) {
  return (
    <p className="font-mono text-[11px] text-subtle-foreground tabular-nums">
      R {match.required.points.toFixed(2)} · N {match.nice.points.toFixed(2)} · E {match.experience.points.toFixed(2)} · L {match.location.points.toFixed(2)}
    </p>
  )
}

function jobPlace(job: DemoJob) {
  return job.remote ? 'Remote' : job.city
}

export function CandidateView({ candidate, matches, density, display }: ViewProps & { candidate: DemoCandidate; matches: DemoMatch[] }) {
  const d = DENSITY[density]
  return (
    <div className={cn('grid', d.body)}>
      <header className="flex flex-wrap items-center gap-4">
        <span className="grid size-12 place-items-center rounded-full text-sm font-semibold text-white" style={{ background: 'linear-gradient(135deg, var(--demo-accent), color-mix(in oklab, var(--demo-accent) 40%, #0a0a0f))' }}>
          {candidate.initials}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className={cn('font-semibold', d.title)}>{candidate.name}</h3>
          <p className="text-muted-foreground">
            {candidate.title} · {candidate.city} · {candidate.years} yrs
          </p>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 px-2.5 py-1 text-xs text-muted-foreground">
          <FileText className="size-3.5" aria-hidden="true" />
          {candidate.source}
        </span>
      </header>
      {d.extra && (
        <p className="flex items-center gap-2 text-muted-foreground">
          <GraduationCap className="size-4 text-[var(--demo-accent-soft)]" aria-hidden="true" />
          {candidate.education}
        </p>
      )}
      <section className="space-y-2.5">
        <Label>Extracted skills</Label>
        <Chips skills={candidate.skills} kind="neutral" limit={d.chips} />
      </section>
      <section className="space-y-2.5">
        <Label>Top matching jobs</Label>
        <ol className="space-y-2">
          {matches.slice(0, d.rows).map((match, i) => (
            <li key={match.job.id} className={cn('rounded-xl border border-white/[0.06] bg-white/[0.02]', density === 'compact' ? 'p-3' : 'p-4')}>
              <div className="flex items-center gap-3">
                <span className="w-5 text-xs tabular-nums text-subtle-foreground">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{match.job.title}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {match.job.company} · {jobPlace(match.job)}
                  </p>
                </div>
                <Score value={match.score} />
              </div>
              <div className="mt-3 pl-8">
                {display === 'skills' ? (
                  <ScoreBar match={match} colors={DEMO_BAR_COLORS} />
                ) : (
                  <p className="text-xs leading-relaxed text-muted-foreground">{match.explanation}</p>
                )}
                {d.extra && <div className="mt-2">{<Points match={match} />}</div>}
              </div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}

export function JobView({ job, ranking, selectedId, density, display }: ViewProps & { job: DemoJob; ranking: DemoMatch[]; selectedId: string }) {
  const d = DENSITY[density]
  return (
    <div className={cn('grid', d.body)}>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className={cn('font-semibold', d.title)}>{job.title}</h3>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <Briefcase className="size-3.5" aria-hidden="true" />
              {job.company}
            </span>
            <span className="inline-flex items-center gap-1">
              <MapPin className="size-3.5" aria-hidden="true" />
              {jobPlace(job)}
            </span>
            <span>{job.jobType}</span>
            {job.minYears !== null && <span>{job.minYears}+ yrs</span>}
          </p>
        </div>
        <span className="rounded-full px-2.5 py-1 text-xs font-medium" style={{ backgroundColor: 'var(--demo-accent-tint)', color: 'var(--demo-accent-soft)' }}>
          Best match for the selected candidate
        </span>
      </header>
      <div className={cn('grid gap-4', density !== 'compact' && 'sm:grid-cols-2')}>
        <section className="space-y-2.5">
          <Label>Required skills</Label>
          <Chips skills={job.required} kind="neutral" limit={d.chips} />
        </section>
        <section className="space-y-2.5">
          <Label>Nice-to-have skills</Label>
          <Chips skills={job.niceToHave} kind="neutral" limit={d.chips} />
        </section>
      </div>
      <section className="space-y-2.5">
        <Label>Top candidates</Label>
        <ol className="space-y-2">
          {ranking.slice(0, d.rows).map((match, i) => {
            const selected = match.candidate.id === selectedId
            return (
              <li
                key={match.candidate.id}
                className={cn(
                  'rounded-xl border bg-white/[0.02]',
                  density === 'compact' ? 'p-3' : 'p-4',
                  selected ? 'border-[var(--demo-accent)]/60 [&_.text-subtle-foreground]:text-muted-foreground' : 'border-white/[0.06]',
                )}
                style={selected ? { backgroundColor: 'var(--demo-accent-tint)' } : undefined}
                aria-current={selected || undefined}
              >
                <div className="flex items-center gap-3">
                  <span className="w-5 text-xs tabular-nums text-subtle-foreground">{i + 1}</span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{match.candidate.name}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {match.candidate.title} · {match.candidate.city}
                    </p>
                  </div>
                  <Score value={match.score} />
                </div>
                <div className="mt-3 pl-8">
                  {display === 'skills' ? (
                    <Chips skills={[...match.required.missing, ...match.nice.missing]} kind="missing" limit={density === 'compact' ? 2 : 4} />
                  ) : (
                    <p className="text-xs leading-relaxed text-muted-foreground">{match.explanation}</p>
                  )}
                  {display === 'skills' && match.required.missing.length + match.nice.missing.length === 0 && (
                    <p className="text-xs text-muted-foreground">No missing skills</p>
                  )}
                  {d.extra && <div className="mt-2">{<Points match={match} />}</div>}
                </div>
              </li>
            )
          })}
        </ol>
      </section>
    </div>
  )
}

export function MatchView({ match, density, display }: ViewProps & { match: DemoMatch }) {
  const d = DENSITY[density]
  const { candidate, job } = match
  const rows = [
    { label: 'Required skills', detail: `${match.required.matched.length} of ${job.required.length}`, part: match.required, weight: 70 },
    { label: 'Nice-to-have skills', detail: `${match.nice.matched.length} of ${job.niceToHave.length}`, part: match.nice, weight: 15 },
    { label: 'Experience', detail: `${candidate.years} of ${job.minYears ?? 0} yrs`, part: match.experience, weight: 10 },
    { label: 'Location', detail: match.location.reason, part: match.location, weight: 5 },
  ]
  return (
    <div className={cn('grid', d.body)}>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 text-muted-foreground">
            {candidate.name}
            <ArrowRight className="size-3.5" aria-hidden="true" />
            <span className="text-foreground">{job.title}</span>
          </p>
          <p className="mt-0.5 text-xs text-subtle-foreground">
            {job.company} · {jobPlace(job)} · {job.jobType}
          </p>
        </div>
        <p className="text-right">
          <Score value={match.score} className={density === 'compact' ? 'text-3xl' : 'text-4xl'} />
          <span className="block text-xs text-subtle-foreground">match score</span>
        </p>
      </header>
      <ScoreBar match={match} colors={DEMO_BAR_COLORS} className="h-2" />

      {display === 'skills' ? (
        <>
          <div className={cn('grid gap-4', density !== 'compact' && 'sm:grid-cols-2')}>
            {rows.map((row, i) => (
              <ComponentBar key={row.label} label={row.label} detail={`${row.detail} · ${formatPercent(row.part.fit)}`} fit={row.part.fit} color={DEMO_BAR_COLORS[i]} delay={i * 0.06} />
            ))}
          </div>
          <div className={cn('grid gap-4', density !== 'compact' && 'sm:grid-cols-2')}>
            <section className="space-y-2.5">
              <Label>Matched skills</Label>
              <Chips skills={[...match.required.matched, ...match.nice.matched]} kind="matched" limit={d.chips} />
            </section>
            <section className="space-y-2.5">
              <Label>Missing skills</Label>
              {match.required.missing.length + match.nice.missing.length > 0 ? (
                <Chips skills={[...match.required.missing, ...match.nice.missing]} kind="missing" limit={d.chips} />
              ) : (
                <p className="text-muted-foreground">None</p>
              )}
            </section>
          </div>
        </>
      ) : (
        <>
          <p className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4 leading-relaxed text-muted-foreground">{match.explanation}</p>
          <dl className="divide-y divide-white/[0.06] rounded-xl border border-white/[0.06]">
            {rows.map((row) => (
              <div key={row.label} className={cn('flex items-center justify-between gap-4', density === 'compact' ? 'px-3 py-2' : 'px-4 py-3')}>
                <dt>
                  <span className="font-medium">{row.label}</span>
                  <span className="block text-xs text-muted-foreground">{row.detail}</span>
                </dt>
                <dd className="text-right tabular-nums">
                  {row.part.points.toFixed(2)} <span className="text-subtle-foreground">/ {row.weight}</span>
                </dd>
              </div>
            ))}
          </dl>
        </>
      )}
      {d.extra && (
        <p className="font-mono text-[12px] text-subtle-foreground tabular-nums">
          70×{match.required.fit.toFixed(2)} + 15×{match.nice.fit.toFixed(2)} + 10×{match.experience.fit.toFixed(2)} + 5×{match.location.fit.toFixed(2)} = {formatScore(match.score)}
        </p>
      )}
    </div>
  )
}
