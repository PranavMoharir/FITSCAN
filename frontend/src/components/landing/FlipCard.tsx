import { motion } from 'framer-motion'
import type { LucideIcon } from 'lucide-react'
import { Check, Plus, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { EASE_OUT } from '@/components/landing/Reveal'

export interface Feature {
  icon: LucideIcon
  title: string
  description: string
  output: string
  details: string[]
}

/**
 * A card that turns over (rotateY) to show more detail. Both sides have a real button, so it
 * works with keyboard, touch and screen readers; the hidden side is `inert`, and focus moves to
 * the button on the side that is turned up.
 */
export function FlipCard({ feature, index }: { feature: Feature; index: number }) {
  const [flipped, setFlipped] = useState(false)
  const openButton = useRef<HTMLButtonElement>(null)
  const closeButton = useRef<HTMLButtonElement>(null)
  const userFlipped = useRef(false)
  const backId = `feature-back-${index}`

  useEffect(() => {
    if (!userFlipped.current) return
    ;(flipped ? closeButton : openButton).current?.focus({ preventScroll: true })
  }, [flipped])

  const toggle = () => {
    userFlipped.current = true
    setFlipped((value) => !value)
  }

  const Icon = feature.icon
  return (
    <div className="h-[19rem] perspective-distant">
      <motion.div
        className="relative h-full w-full transform-3d"
        animate={{ rotateY: flipped ? 180 : 0 }}
        transition={{ duration: 0.5, ease: EASE_OUT }}
      >
        {/* Front */}
        <article
          inert={flipped}
          className="group absolute inset-0 flex flex-col rounded-xl border border-border bg-card p-6 backface-hidden transition-[border-color,box-shadow] duration-300 hover:border-foreground/[0.14] hover:shadow-[0_18px_40px_-26px_rgb(11_11_11/0.35)]"
        >
          <div className="flex items-start justify-between">
            <span className="grid size-11 place-items-center rounded-xl border border-accent-solid/15 bg-accent-solid/[0.07] text-accent-ink">
              <Icon className="size-5" aria-hidden="true" />
            </span>
            <span className="text-xs font-medium tabular-nums text-subtle-foreground">0{index + 1}</span>
          </div>
          <h3 className="mt-7 text-lg font-semibold tracking-tight">{feature.title}</h3>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{feature.description}</p>
          <div className="mt-auto flex items-end justify-between gap-3 pt-4">
            <p className="text-xs text-subtle-foreground">
              Output: <span className="text-muted-foreground">{feature.output}</span>
            </p>
            <button
              ref={openButton}
              type="button"
              onClick={toggle}
              aria-expanded={flipped}
              aria-controls={backId}
              aria-label={`Show details: ${feature.title}`}
              className="grid size-9 shrink-0 place-items-center rounded-full border border-foreground/12 text-foreground outline-none transition-[background-color,transform] duration-300 hover:rotate-90 hover:bg-foreground/[0.08] focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Plus className="size-4" aria-hidden="true" />
            </button>
          </div>
        </article>

        {/* Back */}
        <article
          id={backId}
          inert={!flipped}
          className="absolute inset-0 flex rotate-y-180 flex-col rounded-xl surface-wine border border-accent-solid/20 p-6 backface-hidden"
        >
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent-ink">{feature.title}</p>
          <ul className="mt-4 space-y-2.5">
            {feature.details.map((detail) => (
              <li key={detail} className="flex gap-2.5 text-sm leading-snug text-muted-foreground">
                <Check className="mt-0.5 size-4 shrink-0 text-accent-ink" aria-hidden="true" />
                <span>{detail}</span>
              </li>
            ))}
          </ul>
          <button
            ref={closeButton}
            type="button"
            onClick={toggle}
            aria-label={`Hide details: ${feature.title}`}
            className="mt-auto ml-auto grid size-9 place-items-center rounded-full bg-foreground/10 text-foreground outline-none transition-colors duration-300 hover:bg-foreground/[0.16] focus-visible:ring-2 focus-visible:ring-ring"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </article>
      </motion.div>
    </div>
  )
}
