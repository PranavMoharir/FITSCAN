import { useEffect, useRef, useState } from 'react'

/**
 * A text filter that updates the screen at once and the address (and so the request) after the
 * user pauses typing. A change to the address from elsewhere (for example "Clear filters") wins.
 */
export function useDebouncedParam(value: string, commit: (value: string) => void, delay = 300): [string, (value: string) => void] {
  const [draft, setDraft] = useState(value)
  const timer = useRef<number | undefined>(undefined)
  const commitRef = useRef(commit)
  commitRef.current = commit

  useEffect(() => {
    window.clearTimeout(timer.current)
    setDraft(value)
  }, [value])

  useEffect(() => () => window.clearTimeout(timer.current), [])

  const update = (next: string) => {
    setDraft(next)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => commitRef.current(next.trim()), delay)
  }
  return [draft, update]
}
