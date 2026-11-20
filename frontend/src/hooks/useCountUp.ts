import { animate, useInView, useReducedMotion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'

/**
 * Counts from 0 to `target` the first time the returned ref scrolls into view.
 * With reduced motion the final value is shown at once.
 */
export function useCountUp<T extends Element>(target: number, duration = 0.7) {
  const ref = useRef<T>(null)
  const inView = useInView(ref, { once: true, margin: '-40px' })
  const reduceMotion = useReducedMotion()
  const [value, setValue] = useState(0)

  useEffect(() => {
    if (!inView) return
    if (reduceMotion) {
      setValue(target)
      return
    }
    const controls = animate(0, target, { duration, ease: [0.22, 1, 0.36, 1], onUpdate: setValue })
    return () => controls.stop()
  }, [inView, reduceMotion, target, duration])

  return [ref, value] as const
}
