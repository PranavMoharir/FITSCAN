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

function HeroBackground() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute right-[-10rem] top-[-14rem] h-[40rem] w-[40rem] animate-drift rounded-full bg-[radial-gradient(closest-side,rgb(91_15_24/0.12),transparent)]" />
      <div className="absolute left-[-12rem] top-[22rem] h-[30rem] w-[30rem] animate-drift rounded-full bg-[radial-gradient(closest-side,rgb(91_15_24/0.06),transparent)] [animation-delay:-12s]" />
      <div className="absolute inset-0 bg-[linear-gradient(to_right,rgb(11_11_11/0.045)_1px,transparent_1px),linear-gradient(to_bottom,rgb(11_11_11/0.045)_1px,transparent_1px)] bg-[size:72px_72px] [mask-image:radial-gradient(ellipse_at_50%_30%,black,transparent_70%)]" />
    </div>
  )
}

/** A dashed line with a pulse travelling along it; vertical on narrow screens. */
function Connector({ reverse = false }: { reverse?: boolean }) {
  return (
    <div aria-hidden="true" className="flex items-center justify-center lg:h-full">
      <svg className="h-12 w-6 lg:hidden" viewBox="0 0 24 48" fill="none" preserveAspectRatio="none">
        <path d="M12 0V48" stroke="rgb(11 11 11 / 0.22)" strokeDasharray="3 5" />
        <path d="M12 0V48" stroke="#5b0f18" strokeWidth="2" strokeLinecap="round" pathLength={100} strokeDasharray="14 86" className="animate-dash-flow" />
      </svg>
      <svg className="hidden h-6 w-full lg:block" viewBox="0 0 120 24" fill="none" preserveAspectRatio="none">
        <path d="M0 12H120" stroke="rgb(11 11 11 / 0.22)" strokeDasharray="3 5" />
        <path
          d="M0 12H120"
          stroke="#5b0f18"
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
      <span aria-hidden="true" className="absolute inset-0 animate-pulse-ring rounded-full border border-accent-solid/30" />
      <span aria-hidden="true" className="absolute inset-0 animate-pulse-ring rounded-full border border-accent-solid/30 [animation-delay:-1.8s]" />
      <div className="relative grid size-36 place-items-center rounded-full bg-primary text-primary-foreground shadow-[0_24px_50px_-20px_rgb(91_15_24/0.6)]">
        <div className="text-center">
          <p ref={ref} aria-hidden="true" className="font-display text-6xl leading-none tabular-nums">
            {Math.round(value)}
          </p>
          <p aria-hidden="true" className="mt-1 text-[11px] font-medium uppercase tracking-[0.16em] text-primary-foreground/75">match score</p>
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
        <article className="animate-float rounded-xl border border-foreground/[0.09] bg-card p-5 shadow-[0_1px_2px_rgb(11_11_11/0.04),0_24px_50px_-30px_rgb(11_11_11/0.35)] [animation-delay:-2s]" aria-label="Sample candidate">
          <p className="flex items-center gap-1.5 text-xs font-medium text-subtle-foreground">
            <FileText className="size-3.5" aria-hidden="true" /> Candidate · parsed from PDF
          </p>
          <div className="mt-4 flex items-center gap-3">
            <span className="grid size-11 place-items-center rounded-full bg-accent-solid/10 text-sm font-semibold text-accent-ink">{candidate.initials}</span>
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

        <article className="animate-float rounded-xl border border-foreground/[0.09] bg-card p-5 shadow-[0_1px_2px_rgb(11_11_11/0.04),0_24px_50px_-30px_rgb(11_11_11/0.35)]" aria-label="Sample job">
          <p className="flex items-center gap-1.5 text-xs font-medium text-subtle-foreground">
            <Briefcase className="size-3.5" aria-hidden="true" /> Job · crawled listing
          </p>
          <p className="mt-4 font-semibold">{job.title}</p>
          <p className="mt-0.5 flex items-center gap-1 text-sm text-muted-foreground">
            <MapPin className="size-3.5" aria-hidden="true" /> Remote · {job.jobType} · {job.minYears}+ yrs
          </p>
          <ScoreBar match={match} className="mt-5" />
          <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-lg bg-foreground/[0.04] px-2.5 py-2">
              <dt className="text-subtle-foreground">Required</dt>
              <dd className="mt-0.5 font-medium tabular-nums">
                {match.required.matched.length} of {job.required.length} skills
              </dd>
            </div>
            <div className="rounded-lg bg-foreground/[0.04] px-2.5 py-2">
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
    <section className="surface-cream paper-grain relative overflow-hidden" aria-labelledby="hero-title">
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
          className="mx-auto mt-7 max-w-5xl font-display text-[3.1rem] font-normal leading-[0.98] tracking-[-0.015em] text-balance sm:text-7xl lg:text-[6.25rem]"
        >
          Find the Right Talent.{' '}
          <span className="block italic text-accent-ink">Make Every Match Count.</span>
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: EASE_OUT, delay: 0.16 }}
          className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-muted-foreground sm:text-lg"
        >
          Bring job discovery, resume intelligence and explainable candidate matching together with FITSCAN.
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
