import { useEffect, useRef } from 'react'

/**
 * Calls `callback` every `intervalMs` while `active` is true. The next call is scheduled only after
 * the previous one finished, so slow answers never pile up. Pauses while the browser tab is hidden
 * and refreshes at once when it becomes visible again (LLD §8.5).
 */
export function usePolling(callback: () => unknown, intervalMs: number, active: boolean) {
  const callbackRef = useRef(callback)
  callbackRef.current = callback

  useEffect(() => {
    if (!active) return
    let stopped = false
    let timer: number | undefined

    const schedule = () => {
      if (!stopped) timer = window.setTimeout(tick, intervalMs)
    }
    const tick = async () => {
      if (document.hidden) return schedule()
      try {
        await callbackRef.current()
      } finally {
        schedule()
      }
    }
    const onVisibility = () => {
      if (document.hidden || stopped) return
      window.clearTimeout(timer)
      void tick()
    }

    schedule()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      stopped = true
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [active, intervalMs])
}
