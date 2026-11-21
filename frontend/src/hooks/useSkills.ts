import { useEffect, useState } from 'react'

import { listSkills } from '@/api/client'
import type { SkillItem } from '@/types/api'

// GET /skills changes only when the taxonomy is synced, so one request serves every page in a visit.
let cache: Promise<SkillItem[]> | null = null

/** The canonical skills (for the skill filter's suggestions); empty while loading or if it fails. */
export function useSkills(): SkillItem[] {
  const [skills, setSkills] = useState<SkillItem[]>([])
  useEffect(() => {
    let alive = true
    cache ??= listSkills().then((list) => list.items)
    cache.then(
      (items) => alive && setSkills(items),
      () => {
        cache = null // try again on the next page that needs it
      },
    )
    return () => {
      alive = false
    }
  }, [])
  return skills
}
