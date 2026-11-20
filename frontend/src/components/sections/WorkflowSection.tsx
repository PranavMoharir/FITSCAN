import { motion } from 'framer-motion'
import { FileScan, ListOrdered, Radar, Target } from 'lucide-react'

import { EASE_OUT, Reveal } from '@/components/landing/Reveal'
import { SectionHeading } from '@/components/landing/SectionHeading'
import { SECTION } from '@/lib/landing'

const steps = [
  { icon: Radar, title: 'Discover Jobs', points: ['Crawl and collect job openings', 'Normalise job information'] },
  { icon: FileScan, title: 'Upload Resumes', points: ['Extract candidate information', 'Parse skills, education and experience'] },
  { icon: Target, title: 'Analyze Compatibility', points: ['Compare profiles with job requirements', 'Calculate explainable scores'] },
  { icon: ListOrdered, title: 'Explore Matches', points: ['View ranked results', 'Understand strengths and gaps'] },
]

export function WorkflowSection() {
  return (
    <section id={SECTION.howItWorks} aria-labelledby="workflow-title" className="scroll-mt-20 border-t border-white/[0.06] bg-surface/50">
      <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6 sm:py-28 lg:px-8">
        <SectionHeading
          id="workflow-title"
          align="center"
          eyebrow="How it works"
          title="From job post to ranked shortlist."
          description="Four steps, each running as a background job you can follow live."
        />
        <ol className="relative mt-16 grid gap-10 lg:grid-cols-4 lg:gap-6">
          {/* Connecting line: horizontal on desktop, vertical on smaller screens. */}
          <motion.span
            aria-hidden="true"
            className="absolute left-[2.25rem] right-[calc(25%-2.25rem)] top-5 hidden h-px origin-left bg-gradient-to-r from-brand via-brand-soft to-brand-blue lg:block"
            initial={{ scaleX: 0 }}
            whileInView={{ scaleX: 1 }}
            viewport={{ once: true, amount: 0.6 }}
            transition={{ duration: 0.9, ease: EASE_OUT, delay: 0.15 }}
          />
          <motion.span
            aria-hidden="true"
            className="absolute bottom-10 left-5 top-5 w-px origin-top bg-gradient-to-b from-brand via-brand-soft to-brand-blue lg:hidden"
            initial={{ scaleY: 0 }}
            whileInView={{ scaleY: 1 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 0.9, ease: EASE_OUT }}
          />
          {steps.map((step, i) => (
            <Reveal key={step.title} as="li" delay={0.1 + i * 0.12} className="relative pl-16 lg:pl-0">
              <span className="absolute left-0 top-0 grid size-10 place-items-center rounded-full border border-brand/40 bg-[#0e0e16] text-sm font-semibold tabular-nums text-brand-soft shadow-[0_0_24px_-6px_rgb(124_92_255/0.7)] lg:relative">
                0{i + 1}
              </span>
              <div className="lg:mt-7 lg:pr-4">
                <step.icon className="size-5 text-muted-foreground" aria-hidden="true" />
                <h3 className="mt-3 text-lg font-semibold tracking-tight">{step.title}</h3>
                <ul className="mt-3 space-y-1.5 text-sm text-muted-foreground">
                  {step.points.map((point) => (
                    <li key={point} className="flex gap-2">
                      <span aria-hidden="true" className="mt-2 size-1 shrink-0 rounded-full bg-brand-soft/70" />
                      {point}
                    </li>
                  ))}
                </ul>
              </div>
            </Reveal>
          ))}
        </ol>
      </div>
    </section>
  )
}
