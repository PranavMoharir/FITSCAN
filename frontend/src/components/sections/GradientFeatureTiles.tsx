import { ArrowUpRight, Search } from 'lucide-react'
import type { ReactNode } from 'react'

import { Reveal } from '@/components/landing/Reveal'
import { SectionHeading } from '@/components/landing/SectionHeading'
import { demoJobs, formatScore, topCandidatesFor } from '@/lib/demo-matches'
import { hash, SECTION } from '@/lib/landing'
import { cn } from '@/lib/utils'

/* Small, original CSS illustrations of the product. Decorative only. */

function JobsVisual() {
  const rows = [
    ['Senior Python Developer', 'Pune', 'w-[72%]'],
    ['Data Engineer', 'Bengaluru', 'w-[56%]'],
    ['Frontend Developer', 'Remote', 'w-[64%]'],
  ]
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-xs text-muted-foreground">
        <Search className="size-3.5" /> python developer
      </div>
      {rows.map(([title, place, width]) => (
        <div key={title} className="flex items-center gap-3 rounded-xl border border-white/[0.06] bg-white/[0.03] px-3 py-2">
          <span className="size-6 rounded-md bg-brand/25" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-xs font-medium text-foreground">{title}</span>
            <span className={cn('mt-1 block h-1 rounded-full bg-white/10', width)} />
          </span>
          <span className="text-[11px] text-subtle-foreground">{place}</span>
        </div>
      ))}
    </div>
  )
}

function ResumeVisual() {
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
      <div className="relative overflow-hidden rounded-xl border border-white/10 bg-white/[0.04] p-3">
        <span className="block h-2 w-1/2 rounded bg-white/25" />
        {['w-full', 'w-5/6', 'w-4/6', 'w-full', 'w-3/6', 'w-5/6'].map((w, i) => (
          <span key={i} className={cn('mt-2 block h-1 rounded bg-white/10', w)} />
        ))}
        <span className="absolute inset-x-0 top-1/2 h-px bg-brand-blue shadow-[0_0_12px_2px_rgb(91_124_255/0.7)]" />
      </div>
      <ArrowUpRight className="size-4 rotate-45 text-subtle-foreground" />
      <div className="flex flex-wrap gap-1.5">
        {['Python', 'SQL', 'Docker', 'React', 'AWS'].map((s) => (
          <span key={s} className="rounded-full border border-brand-blue/30 bg-brand-blue/15 px-2 py-0.5 text-[11px] text-foreground/90">
            {s}
          </span>
        ))}
      </div>
    </div>
  )
}

function CompareVisual() {
  const circumference = 2 * Math.PI * 30
  return (
    <div className="flex items-center gap-5">
      <svg viewBox="0 0 72 72" className="size-24 shrink-0 -rotate-90">
        <circle cx="36" cy="36" r="30" stroke="rgb(255 255 255 / 0.08)" strokeWidth="6" fill="none" />
        <circle cx="36" cy="36" r="30" stroke="var(--brand-soft)" strokeWidth="6" fill="none" strokeLinecap="round" strokeDasharray={`${circumference * 0.92} ${circumference}`} />
        <text x="36" y="41" textAnchor="middle" className="fill-foreground text-[15px] font-semibold" transform="rotate(90 36 36)">
          92
        </text>
      </svg>
      <div className="flex-1 space-y-2.5">
        {[
          ['Required', 'w-full'],
          ['Nice-to-have', 'w-3/5'],
          ['Experience', 'w-4/5'],
          ['Location', 'w-full'],
        ].map(([label, width]) => (
          <div key={label}>
            <span className="text-[11px] text-subtle-foreground">{label}</span>
            <span className="mt-1 block h-1 rounded-full bg-white/10">
              <span className={cn('block h-full rounded-full bg-brand-soft/80', width)} />
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** The sample candidates ranked for one sample job, as the application ranks them. */
function RankingVisual() {
  const ranking = topCandidatesFor(demoJobs[0])
  return (
    <div>
      <p className="mb-2.5 text-[11px] text-subtle-foreground">Top candidates · {demoJobs[0].title}</p>
      <ol className="space-y-2">
        {ranking.map((match, i) => (
          <li key={match.candidate.id} className="flex items-center gap-3 text-xs">
            <span className="w-4 tabular-nums text-subtle-foreground">{i + 1}</span>
            <span className="w-20 truncate text-foreground">{match.candidate.name}</span>
            <span className="h-1.5 flex-1 rounded-full bg-white/10">
              <span className="block h-full rounded-full bg-gradient-to-r from-brand to-brand-blue" style={{ width: `${match.score}%` }} />
            </span>
            <span className="w-12 text-right tabular-nums text-muted-foreground">{formatScore(match.score)}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

interface Tile {
  title: string
  text: string
  href: string
  gradient: string
  visual: ReactNode
}

const tiles: Tile[] = [
  {
    title: 'Discover Opportunities',
    text: 'Every crawled listing becomes a clean, searchable job with its skills extracted.',
    href: hash(SECTION.product),
    gradient: 'bg-[radial-gradient(120%_100%_at_0%_0%,rgb(124_92_255/0.30),transparent_60%),linear-gradient(180deg,#15151f,#101018)]',
    visual: <JobsVisual />,
  },
  {
    title: 'Understand Candidates',
    text: 'Resumes turn into profiles with normalised skills, experience and location.',
    href: hash(SECTION.product),
    gradient: 'bg-[radial-gradient(120%_100%_at_100%_0%,rgb(91_124_255/0.28),transparent_60%),linear-gradient(180deg,#15151f,#101018)]',
    visual: <ResumeVisual />,
  },
  {
    title: 'Compare with Confidence',
    text: 'Four weighted dimensions show where a candidate fits and where the gaps are.',
    href: hash(SECTION.matching),
    gradient: 'bg-[radial-gradient(120%_100%_at_0%_100%,rgb(165_148_255/0.22),transparent_60%),linear-gradient(180deg,#15151f,#101018)]',
    visual: <CompareVisual />,
  },
  {
    title: 'Make Better Decisions',
    text: 'Ranked top-10 lists in both directions, ready to review or export.',
    href: hash(SECTION.showcase),
    gradient: 'bg-[radial-gradient(120%_100%_at_100%_100%,rgb(109_74_255/0.28),transparent_60%),linear-gradient(180deg,#15151f,#101018)]',
    visual: <RankingVisual />,
  },
]

export function GradientFeatureTiles() {
  return (
    <section id={SECTION.solutions} aria-labelledby="solutions-title" className="scroll-mt-20 mx-auto max-w-7xl px-4 py-20 sm:px-6 sm:py-28 lg:px-8">
      <SectionHeading
        id="solutions-title"
        eyebrow="Solutions"
        title="Built around the decisions recruiters make."
        description="From the first listing to the final shortlist, each step gives you something you can act on."
      />
      <div className="mt-12 grid gap-4 md:grid-cols-2">
        {tiles.map((tile, i) => (
          <Reveal key={tile.title} delay={(i % 2) * 0.08}>
            <a
              href={tile.href}
              className={cn(
                'group relative flex h-full flex-col overflow-hidden rounded-2xl border border-white/[0.08] p-6 outline-none transition-[transform,border-color,box-shadow] duration-300 ease-out hover:-translate-y-1 hover:border-white/[0.16] hover:shadow-[0_30px_80px_-30px_rgb(124_92_255/0.55)] focus-visible:ring-2 focus-visible:ring-ring sm:p-8',
                tile.gradient,
              )}
            >
              <div aria-hidden="true" className="rounded-2xl border border-white/[0.06] bg-black/20 p-4 backdrop-blur-sm sm:p-5">
                {tile.visual}
              </div>
              <div className="mt-7 flex items-end justify-between gap-6">
                <div>
                  <h3 className="text-2xl font-semibold tracking-[-0.02em]">{tile.title}</h3>
                  <p className="mt-2 max-w-sm text-sm leading-relaxed text-muted-foreground">{tile.text}</p>
                </div>
                <span className="grid size-10 shrink-0 place-items-center rounded-full border border-white/12 transition-[background-color,transform] duration-300 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:bg-white/[0.1]">
                  <ArrowUpRight className="size-4" aria-hidden="true" />
                </span>
              </div>
            </a>
          </Reveal>
        ))}
      </div>
    </section>
  )
}
