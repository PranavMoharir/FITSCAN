import { motion } from 'framer-motion'
import { Briefcase, ChevronLeft, ChevronRight, Sparkles, Users } from 'lucide-react'
import { Tabs } from 'radix-ui'
import { useMemo, useState, type CSSProperties } from 'react'

import { EASE_OUT, Reveal } from '@/components/landing/Reveal'
import { SectionHeading } from '@/components/landing/SectionHeading'
import { ShowcaseControls } from '@/components/landing/showcase/ShowcaseControls'
import {
  ACCENTS,
  CandidateView,
  JobView,
  MatchView,
  type Accent,
  type Density,
  type Display,
  type ShowcaseTab,
} from '@/components/landing/showcase/ShowcaseViews'
import { demoCandidates, formatScore, topCandidatesFor, topJobsFor } from '@/lib/demo-matches'
import { SECTION } from '@/lib/landing'
import { cn } from '@/lib/utils'

const TABS: { value: ShowcaseTab; label: string; icon: typeof Users }[] = [
  { value: 'candidates', label: 'Candidates', icon: Users },
  { value: 'jobs', label: 'Jobs', icon: Briefcase },
  { value: 'matches', label: 'Matches', icon: Sparkles },
]

export function ProductShowcase() {
  const [tab, setTab] = useState<ShowcaseTab>('matches')
  const [index, setIndex] = useState(0)
  const [accent, setAccent] = useState<Accent>('violet')
  const [density, setDensity] = useState<Density>('comfortable')
  const [display, setDisplay] = useState<Display>('skills')

  const candidate = demoCandidates[index]
  const jobMatches = useMemo(() => topJobsFor(candidate), [candidate])
  const best = jobMatches[0]
  const ranking = useMemo(() => topCandidatesFor(best.job), [best.job])

  const step = (delta: number) => setIndex((i) => (i + delta + demoCandidates.length) % demoCandidates.length)
  const palette = ACCENTS[accent]
  const accentVars = { '--demo-accent': palette.solid, '--demo-accent-soft': palette.soft, '--demo-accent-tint': palette.tint } as CSSProperties

  return (
    <section id={SECTION.showcase} aria-labelledby="showcase-title" className="scroll-mt-20 relative overflow-hidden border-t border-white/[0.06]">
      <div aria-hidden="true" className="pointer-events-none absolute left-1/2 top-40 h-[36rem] w-[60rem] -translate-x-1/2 rounded-full bg-[radial-gradient(closest-side,rgb(124_92_255/0.14),transparent)]" />
      <div className="relative mx-auto max-w-7xl px-4 py-20 sm:px-6 sm:py-28 lg:px-8">
        <SectionHeading
          id="showcase-title"
          align="center"
          eyebrow="Product tour"
          title="See how a match comes together."
          description="An interactive preview of the candidate, job and match views. Switch views, step through candidates and change the layout. Every name and number here is sample data."
        />

        <Reveal className="mt-12">
          <ShowcaseControls accent={accent} density={density} display={display} onAccent={setAccent} onDensity={setDensity} onDisplay={setDisplay} />
        </Reveal>

        <Reveal y={28} className="mx-auto mt-6 max-w-5xl">
          <div
            style={accentVars}
            className="overflow-hidden rounded-2xl border border-white/[0.1] bg-surface shadow-[0_50px_140px_-40px_rgb(0_0_0/0.95),0_0_0_1px_rgb(255_255_255/0.02)]"
          >
            {/* Browser chrome */}
            <div className="flex items-center gap-3 border-b border-white/[0.06] px-4 py-3">
              <span aria-hidden="true" className="flex gap-1.5">
                <i className="size-2.5 rounded-full bg-white/15" />
                <i className="size-2.5 rounded-full bg-white/15" />
                <i className="size-2.5 rounded-full bg-white/15" />
              </span>
              <span className="mx-auto truncate rounded-md bg-white/[0.05] px-3 py-1 text-xs text-subtle-foreground sm:mx-0 sm:ml-3">FITSCAN · interactive preview</span>
              <span className="hidden rounded-full border border-white/10 px-2 py-0.5 text-[11px] text-subtle-foreground sm:inline">Sample data</span>
            </div>

            <Tabs.Root value={tab} onValueChange={(v) => setTab(v as ShowcaseTab)}>
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/[0.06] px-3 py-2">
                <Tabs.List aria-label="Preview views" className="flex gap-1">
                  {TABS.map(({ value, label, icon: Icon }) => (
                    <Tabs.Trigger
                      key={value}
                      value={value}
                      className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-muted-foreground outline-none transition-colors duration-200 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring data-[state=active]:bg-[var(--demo-accent-tint)] data-[state=active]:text-foreground"
                    >
                      <Icon className="size-4" aria-hidden="true" />
                      {label}
                    </Tabs.Trigger>
                  ))}
                </Tabs.List>
                <div className="flex items-center gap-1">
                  <button type="button" onClick={() => step(-1)} aria-label="Previous candidate" className="grid size-9 place-items-center rounded-lg text-muted-foreground outline-none hover:bg-white/[0.06] hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">
                    <ChevronLeft className="size-4" aria-hidden="true" />
                  </button>
                  <span className="min-w-[4.5rem] text-center text-xs tabular-nums text-muted-foreground">
                    Candidate {index + 1} / {demoCandidates.length}
                  </span>
                  <button type="button" onClick={() => step(1)} aria-label="Next candidate" className="grid size-9 place-items-center rounded-lg text-muted-foreground outline-none hover:bg-white/[0.06] hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">
                    <ChevronRight className="size-4" aria-hidden="true" />
                  </button>
                  <span className="sr-only" aria-live="polite">
                    Showing {candidate.name}
                  </span>
                </div>
              </div>

              <div className="grid md:grid-cols-[14rem_minmax(0,1fr)]">
                <aside aria-label="Sample candidates" className="hidden border-r border-white/[0.06] p-3 md:block">
                  <p className="px-2 pb-2 pt-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle-foreground">Candidates</p>
                  <ul className="space-y-1">
                    {demoCandidates.map((person, i) => {
                      const top = topJobsFor(person)[0]
                      const active = i === index
                      return (
                        <li key={person.id}>
                          <button
                            type="button"
                            onClick={() => setIndex(i)}
                            aria-pressed={active}
                            className={cn(
                              'w-full rounded-xl px-3 py-2.5 text-left outline-none transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-ring',
                              active
                                ? 'text-foreground [&_.text-subtle-foreground]:text-muted-foreground'
                                : 'text-muted-foreground hover:bg-white/[0.04] hover:text-foreground',
                            )}
                            style={active ? { backgroundColor: 'var(--demo-accent-tint)' } : undefined}
                          >
                            <span className="flex items-center justify-between gap-2 text-sm font-medium">
                              {person.name}
                              <span className="text-xs tabular-nums text-subtle-foreground">{formatScore(top.score)}</span>
                            </span>
                            <span className="block truncate text-xs text-subtle-foreground">
                              {person.title} · {person.city}
                            </span>
                          </button>
                        </li>
                      )
                    })}
                  </ul>
                </aside>

                <div className="min-h-[28rem]">
                  {TABS.map(({ value }) => (
                    <Tabs.Content key={value} value={value} className="outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
                      <motion.div
                        key={`${candidate.id}-${density}-${display}`}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.3, ease: EASE_OUT }}
                      >
                        {value === 'candidates' && <CandidateView candidate={candidate} matches={jobMatches} density={density} display={display} />}
                        {value === 'jobs' && <JobView job={best.job} ranking={ranking} selectedId={candidate.id} density={density} display={display} />}
                        {value === 'matches' && <MatchView match={best} density={density} display={display} />}
                      </motion.div>
                    </Tabs.Content>
                  ))}
                </div>
              </div>
            </Tabs.Root>
          </div>
          <p className="mt-4 text-center text-xs text-subtle-foreground">
            A front-end demonstration. The real application shows scores computed by the FITSCAN backend.
          </p>
        </Reveal>
      </div>
    </section>
  )
}
