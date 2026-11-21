import { useSyncExternalStore } from 'react'

// One shared clock for every relative time on screen ("2 minutes ago"), ticking every 15 seconds.
let now = Date.now()
const listeners = new Set<() => void>()
let timer: number | undefined

function subscribe(listener: () => void) {
  listeners.add(listener)
  if (timer === undefined) {
    timer = window.setInterval(() => {
      now = Date.now()
      listeners.forEach((l) => l())
    }, 15_000)
  }
  return () => {
    listeners.delete(listener)
    if (listeners.size === 0) {
      window.clearInterval(timer)
      timer = undefined
    }
  }
}

export function useNow(): number {
  return useSyncExternalStore(subscribe, () => now)
}
