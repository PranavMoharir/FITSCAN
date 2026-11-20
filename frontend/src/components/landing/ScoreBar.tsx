import { motion } from 'framer-motion'

import { EASE_OUT } from '@/components/landing/Reveal'
import type { DemoMatch } from '@/lib/demo-matches'
import { cn } from '@/lib/utils'

const DEFAULT_COLORS = ['var(--viz-1)', 'var(--viz-2)', 'var(--viz-3)', 'var(--viz-4)'] as const

interface ScoreBarProps {
  match: DemoMatch
  /** Colours for required, nice-to-have, experience and location. */
  colors?: readonly [string, string, string, string]
  className?: string
}

/**
 * FITSCAN's signature: the score as four segments whose widths are the points each
 * dimension earned (out of 70, 15, 10 and 5), so the bar's filled length is the score.
 */
export function ScoreBar({ match, colors = DEFAULT_COLORS, className }: ScoreBarProps) {
  const parts = [match.required.points, match.nice.points, match.experience.points, match.location.points]
  return (
    <div
      role="img"
      aria-label={`Score ${match.score.toFixed(2)} of 100`}
      className={cn('flex h-1.5 w-full gap-px overflow-hidden rounded-full bg-track', className)}
    >
      {parts.map((points, i) =>
        points > 0 ? (
          <motion.span
            key={i}
            className="block h-full origin-left first:rounded-l-full"
            style={{ width: `${points}%`, backgroundColor: colors[i] }}
            initial={{ scaleX: 0 }}
            whileInView={{ scaleX: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.45, ease: EASE_OUT, delay: 0.1 + i * 0.08 }}
          />
        ) : null,
      )}
    </div>
  )
}

interface ComponentBarProps {
  label: string
  detail: string
  fit: number
  color: string
  delay?: number
}

/** One scoring dimension: a label, its detail, and a bar filled to the dimension's fit (0–1). */
export function ComponentBar({ label, detail, fit, color, delay = 0 }: ComponentBarProps) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="font-medium">{label}</span>
        <span className="text-right text-muted-foreground tabular-nums">{detail}</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-track">
        <motion.div
          className="h-full origin-left rounded-full"
          style={{ width: `${fit * 100}%`, backgroundColor: color }}
          initial={{ scaleX: 0 }}
          whileInView={{ scaleX: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, ease: EASE_OUT, delay }}
        />
      </div>
    </div>
  )
}
