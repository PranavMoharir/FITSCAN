import { Reveal } from '@/components/landing/Reveal'
import { Eyebrow } from '@/components/landing/SectionHeading'
import { specs } from '@/lib/landing'

/** Product specifications of the matching design. These are capabilities, not customer results. */
export function StatsBand() {
  return (
    <section aria-labelledby="specs-title" className="surface-cream">
      <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6 sm:py-24 lg:px-8">
        <Reveal className="text-center">
          <Eyebrow>By design</Eyebrow>
          <h2 id="specs-title" className="sr-only">
            Platform specifications
          </h2>
        </Reveal>
        <dl className="mt-12 grid grid-cols-1 gap-y-12 sm:grid-cols-2 lg:grid-cols-4 lg:gap-y-0 lg:divide-x lg:divide-border">
          {specs.map((spec, i) => (
            <Reveal key={spec.label} delay={i * 0.06} className="flex flex-col items-center px-6 text-center">
              <dt className="order-2 mt-4 text-[11px] font-semibold uppercase tracking-[0.2em] text-accent-ink">{spec.label}</dt>
              <dd className="order-1 font-display text-6xl font-normal leading-none tabular-nums sm:text-7xl">{spec.value}</dd>
              <dd className="order-3 mt-2 max-w-[16rem] text-[13px] leading-relaxed text-muted-foreground">{spec.note}</dd>
            </Reveal>
          ))}
        </dl>
        <p className="mt-12 text-center text-xs text-subtle-foreground">Specifications of how FITSCAN matches, not measured customer outcomes.</p>
      </div>
    </section>
  )
}
