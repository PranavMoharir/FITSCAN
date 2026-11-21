import { useCallback } from 'react'
import { useSearchParams } from 'react-router'

/**
 * Filters kept in the address (?q=python&page=2), so a filtered view can be bookmarked, shared and
 * reloaded, and its export link uses exactly the same filters. Empty values are removed.
 */
export function useQueryState() {
  const [params, setParams] = useSearchParams()

  const get = useCallback((key: string) => params.get(key) ?? '', [params])

  /** Sets several values at once; any change other than `page` itself returns to page 1. */
  const set = useCallback(
    (changes: Record<string, string | number | null | undefined>, options: { replace?: boolean } = {}) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current)
          for (const [key, value] of Object.entries(changes)) {
            if (value === null || value === undefined || value === '') next.delete(key)
            else next.set(key, String(value))
          }
          if (!('page' in changes)) next.delete('page')
          return next
        },
        { replace: options.replace ?? true },
      )
    },
    [setParams],
  )

  return { params, get, set }
}

/** The value if it is one of `allowed`, otherwise undefined (hand-edited addresses stay safe). */
export function oneOf<T extends string>(value: string, allowed: readonly T[]): T | undefined {
  return (allowed as readonly string[]).includes(value) ? (value as T) : undefined
}

export function positiveInt(value: string, fallback: number): number {
  const n = Number(value)
  return Number.isInteger(n) && n >= 1 ? n : fallback
}
