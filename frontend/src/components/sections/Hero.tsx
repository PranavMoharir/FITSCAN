import { motion } from 'framer-motion'
import { Briefcase, FileText, MapPin } from 'lucide-react'

import { Cta } from '@/components/landing/Cta'
import { EASE_OUT } from '@/components/landing/Reveal'
import { ScoreBar } from '@/components/landing/ScoreBar'
import { Eyebrow } from '@/components/landing/SectionHeading'
import { SkillChip } from '@/components/landing/SkillChip'
import { useCountUp } from '@/hooks/useCountUp'
import { demoMatch, heroCandidate, heroJob } from '@/lib/demo-matches'
import { APP_PATH, hash, SECTION } from '@/lib/landing'

const match = demoMatch(heroCandidate, heroJob)

// Fixed positions so the particles look the same on every render.
const PARTICLES = [
  [8, 22, 0], [16, 64, 2.4], [24, 38, 1.1], [33, 78, 3.2], [42, 16, 0.6], [55, 70, 2.0],
  [63, 30, 3.8], [71, 58, 1.4], [79, 20, 2.8], [86, 72, 0.3], [92, 42, 1.8], [48, 50, 4.2],
] as const

function HeroBackground() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute left-1/2 top-[-22rem] h-[46rem] w-[min(80rem,140vw)] -translate-x-1/2 animate-drift rounded-full bg-[radial-gradient(closest-side,rgb(124_92_255/0.30),transparent)]" />
      <div className="absolute right-[-12rem] top-[18rem] h-[34rem] w-[34rem] animate-drift rounded-full bg-[radial-gradient(closest-side,rgb(91_124_255/0.16),transparent)] [animation-delay:-9s]" />
      <div className="absolute left-[-14rem] top-[26rem] h-[30rem] w-[30rem] animate-drift rounded-full bg-[radial-gradient(closest-side,rgb(165_148_255/0.10),transparent)] [animation-delay:-15s]" />
      <div className="absolute inset-0 bg-[linear-gradient(to_right,rgb(255_255_255/0.035)_1px,transparent_1px),linear-gradient(to_bottom,rgb(255_255_255/0.035)_1px,transparent_1px)] bg-[size:64px_64px] [mask-image:radial-gradient(ellipse_at_50%_28%,black,transparent_68%)]" />
      {PARTICLES.map(([left, top, delay], i) => (
        <span
          key={i}
          className="absolute size-1 animate-float rounded-full bg-brand-soft/60 shadow-[0_0_10px_2px_rgb(165_148_255/0.35)]"
          style={{ left: `${left}%`, top: `${top}%`, animationDelay: `-${delay}s`, opacity: 0.35 + (i % 3) * 0.2 }}
        />
      ))}
    </div>
  )
}

/** A dashed line with a pulse travelling along it; vertical on narrow screens. */
function Connector({ reverse = false }: { reverse?: boolean }) {
  return (
    <div aria-hidden="true" className="flex items-center justify-center lg:h-full">
      <svg className="h-12 w-6 lg:hidden" viewBox="0 0 24 48" fill="none" preserveAspectRatio="none">
        <path d="M12 0V48" stroke="rgb(255 255 255 / 0.2)" strokeDasharray="3 5" />
        <path d="M12 0V48" stroke="var(--brand-soft)" strokeWidth="2" strokeLinecap="round" pathLength={100} strokeDasharray="14 86" className="animate-dash-flow" />
      </svg>
      <svg className="hidden h-6 w-full lg:block" viewBox="0 0 120 24" fill="none" preserveAspectRatio="none">
        <path d="M0 12H120" stroke="rgb(255 255 255 / 0.2)" strokeDasharray="3 5" />
        <path
          d="M0 12H120"
          stroke="var(--brand-soft)"
          strokeWidth="2"
          strokeLinecap="round"
          pathLength={100}
          strokeDasharray="14 86"
          className="animate-dash-flow"
          style={reverse ? { animationDirection: 'reverse' } : undefined}
        />
      </svg>
    </div>
  )
}

function ScoreOrb() {
  const [ref, value] = useCountUp<HTMLParagraphElement>(match.score)
  return (
    <div className="relative mx-auto grid size-36 place-items-center">
      <span aria-hidden="true" className="absolute inset-0 animate-pulse-ring rounded-full border border-brand/40" />
      <span aria-hidden="true" className="absolute inset-0 animate-pulse-ring rounded-full border border-brand/30 [animation-delay:-1.8s]" />
      <div className="relative grid size-36 place-items-center rounded-full border border-brand/35 bg-[#0d0d15] shadow-[0_0_90px_-12px_rgb(124_92_255/0.75),inset_0_0_30px_rgb(124_92_255/0.15)]">
        <div className="text-center">
          <p ref={ref} aria-hidden="true" className="text-5xl font-semibold tracking-tight tabular-nums">
            {Math.round(value)}
          </p>
          <p aria-hidden="true" className="mt-0.5 text-[11px] font-medium uppercase tracking-[0.16em] text-subtle-foreground">match score</p>
          <p className="sr-only">Sample match score: {Math.round(match.score)} out of 100</p>
        </div>
      </div>
    </div>
  )
}

function HeroMatchVisual() {
  const { candidate, job } = match
  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: EASE_OUT, delay: 0.35 }}
      className="relative mx-auto mt-16 max-w-md text-left sm:mt-20 lg:max-w-5xl"
    >
      <div className="grid items-center lg:grid-cols-[minmax(0,1fr)_minmax(2.5rem,7rem)_auto_minmax(2.5rem,7rem)_minmax(0,1fr)]">
        <article className="animate-float rounded-2xl border border-white/[0.09] bg-card/90 p-5 shadow-[0_30px_80px_-30px_rgb(0_0_0/0.9)] backdrop-blur [animation-delay:-2s]" aria-label="Sample candidate">
          <p className="flex items-center gap-1.5 text-xs font-medium text-subtle-foreground">
            <FileText className="size-3.5" aria-hidden="true" /> Candidate · parsed from PDF
          </p>
          <div className="mt-4 flex items-center gap-3">
            <span className="grid size-11 place-items-center rounded-full bg-gradient-to-br from-brand/40 to-brand-blue/30 text-sm font-semibold">{candidate.initials}</span>
            <div>
              <p className="font-semibold">{candidate.name}</p>
              <p className="text-sm text-muted-foreground">
                {candidate.title} · {candidate.years} yrs · {candidate.city}
              </p>
            </div>
          </div>
          <ul className="mt-4 flex flex-wrap gap-1.5" aria-label="Skills">
            {candidate.skills.slice(0, 6).map((skill) => (
              <li key={skill}>
                <SkillChip name={skill} kind={job.required.includes(skill) || job.niceToHave.includes(skill) ? 'matched' : 'neutral'} />
              </li>
            ))}
          </ul>
        </article>

        <Connector />
        <ScoreOrb />
        <Connector reverse />

        <article className="animate-float rounded-2xl border border-white/[0.09] bg-card/90 p-5 shadow-[0_30px_80px_-30px_rgb(0_0_0/0.9)] backdrop-blur" aria-label="Sample job">
          <p className="flex items-center gap-1.5 text-xs font-medium text-subtle-foreground">
            <Briefcase className="size-3.5" aria-hidden="true" /> Job · crawled listing
          </p>
          <p className="mt-4 font-semibold">{job.title}</p>
          <p className="mt-0.5 flex items-center gap-1 text-sm text-muted-foreground">
            <MapPin className="size-3.5" aria-hidden="true" /> Remote · {job.jobType} · {job.minYears}+ yrs
          </p>
          <ScoreBar match={match} className="mt-5" />
          <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-lg bg-white/[0.04] px-2.5 py-2">
              <dt className="text-subtle-foreground">Required</dt>
              <dd className="mt-0.5 font-medium tabular-nums">
                {match.required.matched.length} of {job.required.length} skills
              </dd>
            </div>
            <div className="rounded-lg bg-white/[0.04] px-2.5 py-2">
              <dt className="text-subtle-foreground">Nice-to-have</dt>
              <dd className="mt-0.5 font-medium tabular-nums">
                {match.nice.matched.length} of {job.niceToHave.length} skills
              </dd>
            </div>
          </dl>
        </article>
      </div>
      <p className="mt-8 text-center text-xs text-subtle-foreground">Illustrative example with sample data, not a live record.</p>
    </motion.div>
  )
}

export function Hero() {
  return (
    <section className="relative overflow-hidden" aria-labelledby="hero-title">
      <HeroBackground />
      <div className="relative mx-auto max-w-7xl px-4 pb-20 pt-20 text-center sm:px-6 sm:pb-28 sm:pt-28 lg:px-8">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: EASE_OUT }}>
          <Eyebrow>Intelligent Job–Candidate Matching</Eyebrow>
        </motion.div>
        <motion.h1
          id="hero-title"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: EASE_OUT, delay: 0.08 }}
          className="mx-auto mt-6 max-w-4xl text-[2.6rem] font-semibold leading-[1.04] tracking-[-0.04em] text-balance sm:text-6xl lg:text-[4.75rem]"
        >
          Find the Right Talent.{' '}
          <span className="block bg-gradient-to-r from-brand-soft via-brand to-brand-blue bg-clip-text pb-1 text-transparent">Faster Than Ever.</span>
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: EASE_OUT, delay: 0.16 }}
          className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-muted-foreground sm:text-lg"
        >
          Turn resumes and job requirements into meaningful matches. FITSCAN helps teams discover qualified candidates through intelligent resume
          analysis and explainable matching.
        </motion.p>
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: EASE_OUT, delay: 0.24 }}
          className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row"
        >
          <Cta to={APP_PATH} arrow className="w-full sm:w-auto">
            Explore the Platform
          </Cta>
          <Cta href={hash(SECTION.howItWorks)} variant="secondary" className="w-full sm:w-auto">
            See How It Works
          </Cta>
        </motion.div>
        <HeroMatchVisual />
      </div>
    </section>
  )
}
