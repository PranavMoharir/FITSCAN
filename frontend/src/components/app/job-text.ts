// Sentences about a background job's progress, shared by the dashboard and the Background jobs pages.

import { BACKGROUND_TYPE_LABEL, ITEM_NOUN, jobDuration, plural } from '@/lib/format'
import type { BackgroundJobSummary } from '@/types/api'

export const noun = (job: Pick<BackgroundJobSummary, 'type'>, count: number) => {
  const [one, many] = ITEM_NOUN[job.type]
  return plural(count, one, many)
}

/** "7 of 10 files · 70%", "42 pages so far" or "Waiting for a worker". */
export function progressText(job: BackgroundJobSummary): string {
  if (job.status === 'queued') return 'Waiting for a worker'
  const { current, total, percent } = job.progress
  if (total) return `${current} of ${noun(job, total)} · ${percent}%`
  return `${noun(job, current)} so far`
}

/** One line on what happened, for lists of runs. */
export function outcomeText(job: BackgroundJobSummary, now = Date.now()): string {
  const duration = jobDuration(job.started_at, job.finished_at, now)
  switch (job.status) {
    case 'queued':
      return 'Waiting for a worker'
    case 'running':
      return progressText(job)
    case 'completed':
      return [`${noun(job, job.items_succeeded)} succeeded`, job.items_failed ? `${job.items_failed} failed` : null, duration ? `took ${duration}` : null]
        .filter(Boolean)
        .join(' · ')
    case 'failed':
      return [`${job.items_succeeded} succeeded`, `${job.items_failed} failed`, duration ? `after ${duration}` : null].filter(Boolean).join(' · ')
    case 'cancelled':
      return job.started_at ? `Cancelled after ${noun(job, job.progress.current)}` : 'Cancelled before it started'
  }
}

/** The moment that best describes a run: when it finished, else started, else was created. */
export const lastTime = (job: BackgroundJobSummary) => job.finished_at ?? job.started_at ?? job.created_at

export const jobLabel = (job: Pick<BackgroundJobSummary, 'type'>) => BACKGROUND_TYPE_LABEL[job.type]
