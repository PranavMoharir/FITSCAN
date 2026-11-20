import { AnimatePresence, motion, useInView, useReducedMotion, type PanInfo } from 'framer-motion'
import { ChevronLeft, ChevronRight, Pause, Play } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { EASE_OUT } from '@/components/landing/Reveal'
import { SectionHeading } from '@/components/landing/SectionHeading'
import { principles, SECTION } from '@/lib/landing'
import { cn } from '@/lib/utils'

const AUTO_ADVANCE_MS = 6500
const SWIPE_DISTANCE = 60

/**
 * "Why FITSCAN?": product principles, not customer testimonials.
 * Auto-advances, pauses on hover or keyboard focus, has a pause button, arrows, dots and swipe.
 */
export function TestimonialCarousel() {
  const reduceMotion = useReducedMotion()
  const regionRef = useRef<HTMLDivElement>(null)
  const inView = useInView(regionRef, { amount: 0.4 })
  const [index, setIndex] = useState(0)
  const [direction, setDirection] = useState(1)
  const [hovered, setHovered] = useState(false)
  const [focused, setFocused] = useState(false)
  const [playing, setPlaying] = useState(true)

  const count = principles.length
  const go = useCallback(
    (delta: number) => {
      setDirection(delta >= 0 ? 1 : -1)
      setIndex((i) => (i + delta + count) % count)
    },
    [count],
  )
  const goTo = (target: number) => {
    setDirection(target >= index ? 1 : -1)
    setIndex(target)
  }

  // Rotates only while visible, so a visitor arrives at the first slide.
  const autoAdvance = playing && inView && !hovered && !focused && !reduceMotion
  useEffect(() => {
    if (!autoAdvance) return
    const timer = window.setTimeout(() => go(1), AUTO_ADVANCE_MS)
    return () => window.clearTimeout(timer)
  }, [autoAdvance, index, go])

  const onDragEnd = (_: unknown, info: PanInfo) => {
    if (info.offset.x < -SWIPE_DISTANCE) go(1)
    else if (info.offset.x > SWIPE_DISTANCE) go(-1)
  }

  const slide = principles[index]
  return (
    <section id={SECTION.why} aria-labelledby="why-title" className="scroll-mt-20 border-t border-white/[0.06]">
      <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6 sm:py-28 lg:px-8">
        <SectionHeading id="why-title" align="center" eyebrow="Product principles" title="Why FITSCAN?" />

        <div
          ref={regionRef}
          role="region"
          aria-roledescription="carousel"
          aria-label="FITSCAN product principles"
          className="relative mx-auto mt-12 max-w-4xl"
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          onFocus={() => setFocused(true)}
          onBlur={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setFocused(false)
          }}
        >
          <div className="relative overflow-hidden rounded-3xl border border-white/[0.08] bg-[radial-gradient(90%_120%_at_50%_0%,rgb(124_92_255/0.16),transparent_60%),#12121a] px-6 py-12 sm:px-14 sm:py-16">
            <span aria-hidden="true" className="pointer-events-none absolute left-6 top-2 select-none font-serif text-[9rem] leading-none text-brand/15 sm:left-10">
              “
            </span>
            <div aria-live={autoAdvance ? 'off' : 'polite'} className="relative min-h-[15rem] sm:min-h-[13rem]">
              <AnimatePresence mode="wait" initial={false} custom={direction}>
                <motion.div
                  key={index}
                  role="group"
                  aria-roledescription="slide"
                  aria-label={`${index + 1} of ${count}: ${slide.label}`}
                  custom={direction}
                  initial={{ opacity: 0, x: direction * 32 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: direction * -32 }}
                  transition={{ duration: 0.35, ease: EASE_OUT }}
                  drag="x"
                  dragConstraints={{ left: 0, right: 0 }}
                  dragElastic={0.18}
                  onDragEnd={onDragEnd}
                  className="cursor-grab touch-pan-y text-center active:cursor-grabbing"
                >
                  <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-brand-soft">{slide.label}</p>
                  <blockquote className="mx-auto mt-5 max-w-2xl text-2xl font-medium leading-snug tracking-[-0.02em] text-balance sm:text-4xl">
                    “{slide.statement}”
                  </blockquote>
                  <p className="mx-auto mt-5 max-w-xl text-sm leading-relaxed text-muted-foreground sm:text-base">{slide.text}</p>
                </motion.div>
              </AnimatePresence>
            </div>
          </div>

          <div className="mt-6 flex items-center justify-between gap-4">
            <button
              type="button"
              onClick={() => setPlaying((p) => !p)}
              aria-label={playing ? 'Pause automatic slide changes' : 'Resume automatic slide changes'}
              className="grid size-10 place-items-center rounded-full border border-white/10 text-muted-foreground outline-none transition-colors hover:bg-white/[0.06] hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
            >
              {playing ? <Pause className="size-4" aria-hidden="true" /> : <Play className="size-4" aria-hidden="true" />}
            </button>
            <div className="flex items-center gap-1">
              {principles.map((p, i) => (
                <button
                  key={p.label}
                  type="button"
                  onClick={() => goTo(i)}
                  aria-label={`Show slide ${i + 1}: ${p.label}`}
                  aria-current={i === index || undefined}
                  className="grid h-8 min-w-6 place-items-center rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span className={cn('block h-1.5 rounded-full transition-all duration-300', i === index ? 'w-6 bg-brand' : 'w-1.5 bg-white/25')} />
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <button type="button" onClick={() => go(-1)} aria-label="Previous slide" className="grid size-10 place-items-center rounded-full border border-white/10 outline-none transition-colors hover:bg-white/[0.06] focus-visible:ring-2 focus-visible:ring-ring">
                <ChevronLeft className="size-4" aria-hidden="true" />
              </button>
              <button type="button" onClick={() => go(1)} aria-label="Next slide" className="grid size-10 place-items-center rounded-full border border-white/10 outline-none transition-colors hover:bg-white/[0.06] focus-visible:ring-2 focus-visible:ring-ring">
                <ChevronRight className="size-4" aria-hidden="true" />
              </button>
            </div>
          </div>
          <p className="mt-4 text-center text-xs text-subtle-foreground">These are FITSCAN’s design principles, not customer testimonials.</p>
        </div>
      </div>
    </section>
  )
}
