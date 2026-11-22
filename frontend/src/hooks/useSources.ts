import { useEffect, useState } from 'react'

import { listSources } from '@/api/client'
import type { SourceInfo } from '@/types/api'

// GET /sources changes only when the backend's extractors change, so one request serves the whole visit.
let cache: Promise<SourceInfo[]> | null = null

/** The supported job sources, real first (for labels, filters and the crawl form); empty while loading or on failure. */
export function useSources(): SourceInfo[] {
  const [sources, setSources] = useState<SourceInfo[]>([])
  useEffect(() => {
    let alive = true
    cache ??= listSources().then((list) => list.items)
    cache.then(
      (items) => alive && setSources(items),
      () => {
        cache = null // try again on the next page that needs it
      },
    )
    return () => {
      alive = false
    }
  }, [])
  return sources
}

/** A source's label ("Greenhouse job board"), or its name while the list is loading or for an unknown source. */
export const sourceLabel = (sources: SourceInfo[], name: string) => sources.find((s) => s.name === name)?.label ?? name
