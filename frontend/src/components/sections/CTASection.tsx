import { Cta } from '@/components/landing/Cta'
import { Reveal } from '@/components/landing/Reveal'
import { APP_PATH, SECTION } from '@/lib/landing'

export function CTASection() {
  return (
    <section id={SECTION.getStarted} aria-labelledby="cta-title" className="scroll-mt-20 mx-auto max-w-7xl px-4 pb-24 pt-8 sm:px-6 lg:px-8">
      <Reveal>
        <div className="relative isolate overflow-hidden rounded-3xl border border-white/[0.09] bg-[radial-gradient(80%_110%_at_50%_0%,rgb(124_92_255/0.34),transparent_65%),linear-gradient(180deg,#13131c,#0c0c12)] px-6 py-20 text-center sm:py-24">
          {/* Concentric rings echo the score orb in the hero. */}
          <div aria-hidden="true" className="pointer-events-none absolute left-1/2 top-[-9rem] -z-10 -translate-x-1/2">
            {[18, 28, 38, 48].map((size, i) => (
              <span
                key={size}
                className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/[0.06]"
                style={{ width: `${size}rem`, height: `${size}rem` }}
              >
                <span className="absolute inset-0 animate-pulse-ring rounded-full border border-brand/20" style={{ animationDelay: `-${i * 0.9}s` }} />
              </span>
            ))}
          </div>
          <div aria-hidden="true" className="mx-auto mb-10 flex h-1.5 w-40 overflow-hidden rounded-full">
            <i className="w-[70%] bg-brand" />
            <i className="w-[15%] bg-brand-soft" />
            <i className="w-[10%] bg-brand-blue" />
            <i className="w-[5%] bg-white/60" />
          </div>
          <h2 id="cta-title" className="text-4xl font-semibold tracking-[-0.04em] text-balance sm:text-6xl">
            Make Every Match Count.
          </h2>
          <p className="mx-auto mt-5 max-w-xl text-base leading-relaxed text-muted-foreground sm:text-lg">
            Bring job discovery, resume intelligence and candidate matching together with FITSCAN.
          </p>
          <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Cta to={APP_PATH} arrow className="w-full sm:w-auto">
              Get Started
            </Cta>
            <Cta to={APP_PATH} variant="secondary" className="w-full sm:w-auto">
              Explore the Platform
            </Cta>
          </div>
        </div>
      </Reveal>
    </section>
  )
}
