import { motion } from 'framer-motion'
import type { ReactNode } from 'react'

/** Ease-out curve shared by every landing animation. */
export const EASE_OUT = [0.22, 1, 0.36, 1] as const

interface RevealProps {
  children: ReactNode
  className?: string
  delay?: number
  /** Distance to slide up from, in pixels. */
  y?: number
  /** Render as a list item when the parent is a list. */
  as?: 'div' | 'li'
}

/** Fades and slides its content in the first time it scrolls into view. */
export function Reveal({ children, className, delay = 0, y = 16, as = 'div' }: RevealProps) {
  const Component = as === 'li' ? motion.li : motion.div
  return (
    <Component
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.15 }}
      transition={{ duration: 0.45, ease: EASE_OUT, delay }}
    >
      {children}
    </Component>
  )
}
