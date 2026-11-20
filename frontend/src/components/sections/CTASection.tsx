import { Cta } from '@/components/landing/Cta'
import { Reveal } from '@/components/landing/Reveal'
import { APP_PATH, SECTION } from '@/lib/landing'

export function CTASection() {
  return (
    <section id={SECTION.getStarted} aria-labelledby="cta-title" className="surface-cream scroll-mt-20">
      <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6 sm:py-24 lg:px-8">
        <Reveal>
          {/* A burgundy panel with a soft, satin-like light: a highlight top left, shade bottom right. */}
          <div className="surface-wine relative isolate overflow-hidden rounded-2xl bg-[radial-gradient(110%_80%_at_15%_0%,rgb(255_255_255/0.09),transparent_55%),radial-gradient(90%_70%_at_100%_100%,rgb(0_0_0/0.28),transparent_60%)] px-6 py-20 text-center sm:py-24">
            <div aria-hidden="true" className="pointer-events-none absolute left-1/2 top-[-9rem] -z-10 -translate-x-1/2">
              {[18, 28, 38, 48].map((size, i) => (
                <span
                  key={size}
                  className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border border-foreground/[0.08]"
                  style={{ width: `${size}rem`, height: `${size}rem` }}
                >
                  <span className="absolute inset-0 animate-pulse-ring rounded-full border border-foreground/15" style={{ animationDelay: `-${i * 0.9}s` }} />
                </span>
              ))}
            </div>
            <div aria-hidden="true" className="mx-auto mb-10 flex h-1 w-40 gap-px overflow-hidden rounded-full">
              <i className="w-[70%] bg-viz-1" />
              <i className="w-[15%] bg-viz-2" />
              <i className="w-[10%] bg-viz-3" />
              <i className="w-[5%] bg-viz-4" />
            </div>
            <h2 id="cta-title" className="font-display text-5xl font-normal leading-[1.02] text-balance sm:text-7xl">
              Turn Better Matches Into Better Decisions.
            </h2>
            <p className="mx-auto mt-5 max-w-xl text-base leading-relaxed text-muted-foreground sm:text-lg">
              Discover relevant candidates, understand compatibility and make more informed recruitment decisions with FITSCAN.
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
      </div>
    </section>
  )
}
