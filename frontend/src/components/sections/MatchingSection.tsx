import { Briefcase, Gauge, MapPin, Sparkles } from 'lucide-react'

import { Reveal } from '@/components/landing/Reveal'
import { ComponentBar } from '@/components/landing/ScoreBar'
import { HeadingMuted, SectionHeading } from '@/components/landing/SectionHeading'
import { SkillChip } from '@/components/landing/SkillChip'
import { useCountUp } from '@/hooks/useCountUp'
import { demoCandidates, demoJobs, demoMatch, formatPercent, WEIGHTS } from '@/lib/demo-matches'
import { SECTION } from '@/lib/landing'

// Ananya Rao × Senior Python Developer: 70·1 + 15·0.6 + 10·0.8 + 5·1 = 92.00
const match = demoMatch(demoCandidates[0], demoJobs[0])

const dimensions = [
  { icon: Sparkles, title: 'Required skill compatibility', weight: WEIGHTS.required, text: 'The share of the job’s must-have skills the candidate has.' },
  { icon: Gauge, title: 'Nice-to-have skill compatibility', weight: WEIGHTS.nice, text: 'Extra credit for the preferred skills a candidate brings.' },
  { icon: Briefcase, title: 'Experience compatibility', weight: WEIGHTS.experience, text: 'Years of experience against the job’s stated minimum.' },
  { icon: MapPin, title: 'Location compatibility', weight: WEIGHTS.location, text: 'Same city or a remote role.' },
]

function MatchBreakdown() {
  const [ref, value] = useCountUp<HTMLParagraphElement>(match.score, 0.8)
  const [whole, decimals] = value.toFixed(2).split('.')
  const { candidate, job } = match
  return (
    <div className="relative">
      <figure className="relative rounded-xl border border-border bg-card p-6 sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium text-subtle-foreground">Overall match</p>
            <p ref={ref} aria-hidden="true" className="mt-1 font-display text-7xl font-normal leading-none tabular-nums">
              {whole}
              <span className="text-3xl text-subtle-foreground">.{decimals}</span>
            </p>
            <p className="sr-only">Overall match {match.score.toFixed(2)} out of 100</p>
          </div>
          <div className="text-right text-sm">
            <p className="font-medium">{candidate.name}</p>
            <p className="text-muted-foreground">{job.title}</p>
          </div>
        </div>

        <div className="mt-8 space-y-5">
          <ComponentBar label="Required skills" detail={`${match.required.matched.length} of ${job.required.length} · ${formatPercent(match.required.fit)}`} fit={match.required.fit} color="var(--viz-1)" />
          <ComponentBar label="Nice-to-have skills" detail={`${match.nice.matched.length} of ${job.niceToHave.length} · ${formatPercent(match.nice.fit)}`} fit={match.nice.fit} color="var(--viz-2)" delay={0.08} />
          <ComponentBar label="Experience" detail={`${candidate.years} of ${job.minYears} yrs · ${formatPercent(match.experience.fit)}`} fit={match.experience.fit} color="var(--viz-3)" delay={0.16} />
          <ComponentBar label="Location" detail={`Same city · ${formatPercent(match.location.fit)}`} fit={match.location.fit} color="var(--viz-4)" delay={0.24} />
        </div>

        <div className="mt-7">
          <p className="text-xs font-medium text-subtle-foreground">Skills</p>
          <ul className="mt-2.5 flex flex-wrap gap-1.5">
            {[...match.required.matched, ...match.nice.matched].map((skill) => (
              <li key={skill}>
                <SkillChip name={skill} kind="matched" />
              </li>
            ))}
            {[...match.required.missing, ...match.nice.missing].map((skill) => (
              <li key={skill}>
                <SkillChip name={skill} kind="missing" />
              </li>
            ))}
          </ul>
        </div>

        <div className="mt-6 rounded-xl border border-foreground/[0.06] bg-foreground/[0.03] p-4">
          <p className="text-xs font-medium text-subtle-foreground">Why this score</p>
          <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{match.explanation}</p>
          <p className="mt-3 font-mono text-[12px] text-subtle-foreground tabular-nums">
            70×{match.required.fit.toFixed(2)} + 15×{match.nice.fit.toFixed(2)} + 10×{match.experience.fit.toFixed(2)} + 5×{match.location.fit.toFixed(2)} ={' '}
            <span className="text-foreground">{match.score.toFixed(2)}</span>
          </p>
        </div>
        <figcaption className="mt-4 text-xs text-subtle-foreground">Illustrative example with sample data, not an API response.</figcaption>
      </figure>
    </div>
  )
}

export function MatchingSection() {
  return (
    <section id={SECTION.matching} aria-labelledby="matching-title" className="surface-ink scroll-mt-20 relative overflow-hidden">
      <div className="mx-auto grid max-w-7xl items-center gap-14 px-4 py-20 sm:px-6 sm:py-28 lg:grid-cols-2 lg:gap-20 lg:px-8">
        <div>
          <SectionHeading
            id="matching-title"
            eyebrow="Explainable matching"
            title={
              <>
                Beyond Keywords.
                <HeadingMuted>Understand Compatibility.</HeadingMuted>
              </>
            }
            description="FITSCAN evaluates the relationship between a candidate's profile and a job's requirements to produce meaningful, explainable match scores."
          />
          <ul className="mt-10 space-y-3">
            {dimensions.map((dimension, i) => (
              <Reveal
                key={dimension.title}
                as="li"
                delay={i * 0.06}
                className="flex items-start gap-4 rounded-xl border border-foreground/[0.07] bg-foreground/[0.02] p-4 transition-colors duration-300 hover:border-foreground/[0.12] hover:bg-foreground/[0.04]"
              >
                  <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent-solid/12 text-accent-ink">
                    <dimension.icon className="size-[18px]" aria-hidden="true" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline justify-between gap-3">
                      <span className="font-medium">{dimension.title}</span>
                      <span className="shrink-0 text-xs font-medium tabular-nums text-accent-ink">up to {dimension.weight} pts</span>
                    </span>
                    <span className="mt-1 block text-sm leading-relaxed text-muted-foreground">{dimension.text}</span>
                  </span>
              </Reveal>
            ))}
          </ul>
          <Reveal delay={0.24}>
            <p className="mt-6 text-sm leading-relaxed text-muted-foreground">
              <span className="font-mono text-[13px] text-foreground">Score = 70R + 15N + 10E + 5L</span>, where each part is a fraction from 0 to 1.
              Text similarity is used only to break exact-score ties; it never changes a score.
            </p>
          </Reveal>
        </div>
        <Reveal y={24}>
          <MatchBreakdown />
        </Reveal>
      </div>
    </section>
  )
}
