import { FileScan, ListChecks, Radar, Target } from 'lucide-react'

import { FlipCard, type Feature } from '@/components/landing/FlipCard'
import { Reveal } from '@/components/landing/Reveal'
import { SectionHeading } from '@/components/landing/SectionHeading'
import { SECTION } from '@/lib/landing'

const features: Feature[] = [
  {
    icon: FileScan,
    title: 'Intelligent Resume Parsing',
    description: 'Turn PDF resumes into structured, searchable candidate profiles.',
    output: 'candidate profile',
    details: [
      'Upload several PDF resumes at once',
      'Reads text layers, including two-column layouts',
      'Falls back to OCR for scanned files and flags them',
      'Extracts contact details, experience, education and skills',
    ],
  },
  {
    icon: Radar,
    title: 'Smart Job Discovery',
    description: 'Crawl job listings and turn them into consistent, comparable records.',
    output: 'normalised job',
    details: [
      'Breadth-first crawler with depth and page limits',
      'Respects robots.txt and per-site rate limits',
      'Normalises locations and job types, removes duplicates',
      'Separates required from nice-to-have skills',
    ],
  },
  {
    icon: Target,
    title: 'Weighted Matching',
    description: 'Score every candidate against every job with one weighted formula, then rank the strongest fits.',
    output: 'ranked matches',
    details: [
      'Scores every job–candidate pair',
      'Weights: required skills 70, nice-to-have 15, experience 10, location 5',
      'Keeps the top 10 in both directions',
      'Text similarity is used only to break exact score ties',
    ],
  },
  {
    icon: ListChecks,
    title: 'Explainable Results',
    description: 'See why a candidate fits a role, and exactly where the gaps are.',
    output: 'match explanation',
    details: [
      'Matched skills, labelled required or nice-to-have',
      'Missing requirements, clearly flagged',
      'Experience and location compatibility for each match',
      'A plain-language explanation of every score',
    ],
  },
]

export function FeaturesSection() {
  return (
    <section id={SECTION.product} aria-labelledby="features-title" className="surface-warm scroll-mt-20">
      <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6 sm:py-28 lg:px-8">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <SectionHeading
          id="features-title"
          eyebrow="Capabilities"
          title="From raw documents to ranked, explained matches."
          description="Four capabilities work together, from the first crawl or upload to a shortlist you can justify."
        />
        <p className="text-sm text-subtle-foreground lg:pb-2">Select + on a card for details.</p>
      </div>
      <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {features.map((feature, i) => (
          <Reveal key={feature.title} delay={i * 0.06}>
            <FlipCard feature={feature} index={i} />
          </Reveal>
        ))}
      </div>
      </div>
    </section>
  )
}
