// What the dashboard loads, and from where (every number comes from an existing endpoint).

import { listBackgroundJobs, listSkills, searchCandidates, searchJobs } from '@/api/client'
import type { BackgroundJobStatus, BackgroundJobSummary, BackgroundJobType } from '@/types/api'

export interface DashboardTotals {
  /** null when that request failed (shown as a dash, never as 0). */
  jobs: number | null
  candidates: number | null
  skills: number | null
  categories: number | null
}

/** GET /jobs?page_size=1, GET /candidates?page_size=1 (their `total`) and GET /skills. */
export async function loadTotals(signal: AbortSignal): Promise<DashboardTotals> {
  const [jobs, candidates, skills] = await Promise.allSettled([
    searchJobs({ page_size: 1 }, signal),
    searchCandidates({ page_size: 1 }, signal),
    listSkills(signal),
  ])
  const all = [jobs, candidates, skills]
  if (all.every((r) => r.status === 'rejected')) throw (jobs as PromiseRejectedResult).reason
  const skillItems = skills.status === 'fulfilled' ? skills.value.items : null
  return {
    jobs: jobs.status === 'fulfilled' ? jobs.value.total : null,
    candidates: candidates.status === 'fulfilled' ? candidates.value.total : null,
    skills: skills.status === 'fulfilled' ? skills.value.total : null,
    categories: skillItems ? new Set(skillItems.map((s) => s.category ?? 'Other')).size : null,
  }
}

export const STATUSES: BackgroundJobStatus[] = ['running', 'queued', 'completed', 'failed', 'cancelled']
export const TYPES: BackgroundJobType[] = ['crawl', 'resume', 'match']

export interface DashboardActivity {
  counts: Record<BackgroundJobStatus, number>
  total: number
  /** Running jobs first, then queued ones (at most five of each). */
  active: BackgroundJobSummary[]
  recent: BackgroundJobSummary[]
  lastCompleted: Record<BackgroundJobType, BackgroundJobSummary | null>
}

/** GET /background-jobs with filters: counts per status (`total`), the active runs, the newest runs. */
export async function loadActivity(signal: AbortSignal): Promise<DashboardActivity> {
  const [running, queued, completed, failed, cancelled, recent, crawl, resume, match] = await Promise.all([
    listBackgroundJobs({ status: 'running', page_size: 5 }, signal),
    listBackgroundJobs({ status: 'queued', page_size: 5 }, signal),
    listBackgroundJobs({ status: 'completed', page_size: 1 }, signal),
    listBackgroundJobs({ status: 'failed', page_size: 1 }, signal),
    listBackgroundJobs({ status: 'cancelled', page_size: 1 }, signal),
    listBackgroundJobs({ page_size: 8 }, signal),
    listBackgroundJobs({ type: 'crawl', status: 'completed', page_size: 1 }, signal),
    listBackgroundJobs({ type: 'resume', status: 'completed', page_size: 1 }, signal),
    listBackgroundJobs({ type: 'match', status: 'completed', page_size: 1 }, signal),
  ])
  return {
    counts: { running: running.total, queued: queued.total, completed: completed.total, failed: failed.total, cancelled: cancelled.total },
    total: recent.total,
    active: [...running.items, ...queued.items],
    recent: recent.items,
    lastCompleted: { crawl: crawl.items[0] ?? null, resume: resume.items[0] ?? null, match: match.items[0] ?? null },
  }
}
