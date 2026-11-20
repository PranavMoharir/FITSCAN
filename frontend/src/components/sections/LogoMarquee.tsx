import { marqueeLabels } from '@/lib/landing'

/**
 * An endless row of neutral industry labels (not customer logos) on a black band. The list is
 * rendered twice and moved by half its width, so the loop has no seam. Hover pauses it;
 * reduced motion stops it.
 */
export function LogoMarquee() {
  return (
    <section aria-labelledby="marquee-title" className="surface-ink border-y border-border py-10">
      <h2 id="marquee-title" className="px-4 text-center text-[11px] font-semibold uppercase tracking-[0.24em] text-subtle-foreground">
        Built for modern recruitment workflows
      </h2>
      <div className="group relative mt-6 overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_12%,black_88%,transparent)]">
        <ul className="flex w-max animate-marquee group-hover:[animation-play-state:paused]">
          {[...marqueeLabels, ...marqueeLabels].map((label, i) => (
            <li
              key={`${label}-${i}`}
              aria-hidden={i >= marqueeLabels.length || undefined}
              className="flex items-center whitespace-nowrap px-7 font-display text-xl text-foreground/60 transition-colors duration-300 hover:text-foreground sm:text-2xl"
            >
              <span aria-hidden="true" className="mr-7 size-1 rounded-full bg-accent-solid/70" />
              {label}
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
