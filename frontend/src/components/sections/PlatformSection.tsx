import { Briefcase, FileScan, Radar } from 'lucide-react'

import { BrandMark } from '@/components/landing/BrandMark'
import { Cta } from '@/components/landing/Cta'
import { Reveal } from '@/components/landing/Reveal'
import { HeadingMuted, SectionHeading } from '@/components/landing/SectionHeading'
import { APP_PATH, SECTION } from '@/lib/landing'

// Coordinates in a 500 × 400 box; HTML nodes are placed with the same numbers as percentages.
const HUB = { x: 250, y: 200 }
const candidates = [
  { x: 72, y: 92, initials: 'AR', label: 'Backend' },
  { x: 52, y: 200, initials: 'RM', label: 'Data' },
  { x: 72, y: 308, initials: 'ST', label: 'Frontend' },
]
const jobs = [
  { x: 428, y: 92, label: 'Python Developer' },
  { x: 448, y: 200, label: 'Data Engineer' },
  { x: 428, y: 308, label: 'Frontend Dev' },
]
const skills = [
  { x: 250, y: 64, label: 'Python' },
  { x: 168, y: 318, label: 'SQL' },
  { x: 332, y: 318, label: 'React' },
]

const curve = (x1: number, y1: number, x2: number, y2: number) => `M${x1} ${y1} C${x1 + (x2 - x1) * 0.5} ${y1}, ${x1 + (x2 - x1) * 0.5} ${y2}, ${x2} ${y2}`
const at = (x: number, y: number) => ({ left: `${x / 5}%`, top: `${y / 4}%` })

const paths = [
  ...candidates.map((c) => curve(c.x + 34, c.y, HUB.x, HUB.y)),
  ...jobs.map((j) => curve(HUB.x, HUB.y, j.x - 52, j.y)),
  ...skills.map((s) => `M${HUB.x} ${HUB.y} L${s.x} ${s.y}`),
]

function EcosystemVisual() {
  return (
    <div className="relative mx-auto aspect-[5/4] w-full max-w-xl" role="img" aria-label="Illustration: candidates and jobs connected through shared skills to the FITSCAN matching engine">
      <div aria-hidden="true" className="absolute inset-[18%] rounded-full bg-[radial-gradient(closest-side,rgb(124_92_255/0.30),transparent)] blur-xl" />
      <svg aria-hidden="true" className="absolute inset-0 h-full w-full" viewBox="0 0 500 400" fill="none">
        <defs>
          <linearGradient id="eco-line" x1="0" y1="0" x2="500" y2="0" gradientUnits="userSpaceOnUse">
            <stop stopColor="#a594ff" />
            <stop offset="1" stopColor="#5b7cff" />
          </linearGradient>
        </defs>
        <circle cx={HUB.x} cy={HUB.y} r="120" stroke="rgb(255 255 255 / 0.05)" />
        <circle cx={HUB.x} cy={HUB.y} r="175" stroke="rgb(255 255 255 / 0.035)" strokeDasharray="2 6" />
        {paths.map((d, i) => (
          <g key={d}>
            <path d={d} stroke="rgb(255 255 255 / 0.09)" strokeWidth="1.25" />
            <path
              d={d}
              stroke="url(#eco-line)"
              strokeWidth="1.75"
              strokeLinecap="round"
              pathLength={100}
              strokeDasharray="12 88"
              className="animate-dash-flow"
              style={{ animationDelay: `-${(i * 0.37) % 3}s` }}
            />
          </g>
        ))}
      </svg>

      <div aria-hidden="true">
        {candidates.map((c) => (
          <span key={c.initials} className="absolute flex -translate-x-1/2 -translate-y-1/2 items-center gap-2 rounded-full border border-white/10 bg-card/95 py-1 pl-1 pr-3 text-xs shadow-lg" style={at(c.x, c.y)}>
            <span className="grid size-6 place-items-center rounded-full bg-gradient-to-br from-brand/50 to-brand-blue/40 text-[10px] font-semibold">{c.initials}</span>
            {c.label}
          </span>
        ))}
        {jobs.map((j) => (
          <span key={j.label} className="absolute flex -translate-x-1/2 -translate-y-1/2 items-center gap-1.5 whitespace-nowrap rounded-full border border-white/10 bg-card/95 px-3 py-1.5 text-xs shadow-lg" style={at(j.x, j.y)}>
            <Briefcase className="size-3.5 text-brand-soft" />
            {j.label}
          </span>
        ))}
        {skills.map((s) => (
          <span key={s.label} className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full border border-brand/30 bg-brand/15 px-2.5 py-1 text-[11px] font-medium text-brand-soft" style={at(s.x, s.y)}>
            {s.label}
          </span>
        ))}
        <span className="absolute grid size-20 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border border-brand/35 bg-[#0d0d15] shadow-[0_0_60px_-8px_rgb(124_92_255/0.8)] sm:size-24" style={at(HUB.x, HUB.y)}>
          <BrandMark className="size-10 sm:size-11" />
        </span>

        <span className="absolute left-[2%] top-[-4%] hidden animate-float rounded-xl border border-white/10 bg-card/95 px-3 py-2 text-[11px] shadow-xl sm:block">
          <span className="block text-subtle-foreground">Resume parsed</span>
          <span className="font-medium text-foreground">9 skills extracted</span>
        </span>
        <span className="absolute bottom-[-4%] right-[2%] hidden animate-float rounded-xl border border-white/10 bg-card/95 px-3 py-2 text-[11px] shadow-xl [animation-delay:-3.5s] sm:block">
          <span className="block text-subtle-foreground">Match computed</span>
          <span className="font-medium tabular-nums text-foreground">Top 10 ranked</span>
        </span>
      </div>
    </div>
  )
}

const capabilities = [
  {
    icon: Radar,
    title: 'Job Discovery',
    text: 'A polite, rate-limited crawler collects openings and turns each listing into a normalised job with required and nice-to-have skills.',
  },
  {
    icon: FileScan,
    title: 'Resume Intelligence',
    text: 'Bulk PDF upload becomes structured profiles, with skills normalised against one shared taxonomy and unreadable files flagged.',
  },
]

export function PlatformSection() {
  return (
    <section id={SECTION.platform} aria-labelledby="platform-title" className="scroll-mt-20 border-t border-white/[0.06] bg-surface/50">
      <div className="mx-auto grid max-w-7xl items-center gap-16 px-4 py-20 sm:px-6 sm:py-28 lg:grid-cols-[1fr_1.05fr] lg:px-8">
        <div>
          <SectionHeading
            id="platform-title"
            eyebrow="Platform"
            title={
              <>
                One Platform.
                <HeadingMuted>The Entire Matching Workflow.</HeadingMuted>
              </>
            }
            description="Job discovery, resume processing and candidate matching share one data model, so a new crawl or a new batch of resumes flows straight into ranked, explainable matches."
          />
          <div className="mt-10 grid gap-4 sm:grid-cols-2">
            {capabilities.map((capability, i) => (
              <Reveal key={capability.title} delay={i * 0.08} className="rounded-2xl border border-white/[0.08] bg-card p-6">
                <capability.icon className="size-6 text-brand-soft" aria-hidden="true" />
                <h3 className="mt-5 text-xl font-semibold tracking-tight">{capability.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{capability.text}</p>
              </Reveal>
            ))}
          </div>
          <Reveal delay={0.16} className="mt-10">
            <Cta to={APP_PATH} arrow>
              Explore the Platform
            </Cta>
          </Reveal>
        </div>
        <Reveal y={24}>
          <EcosystemVisual />
        </Reveal>
      </div>
    </section>
  )
}
