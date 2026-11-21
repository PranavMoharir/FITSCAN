// Display formatting for the application pages. Values are shown as the API sends them; these
// helpers only choose units and words.

import type { BackgroundJobStatus, BackgroundJobType, JobType, Salary } from '@/types/api'

const numberFormat = new Intl.NumberFormat(undefined)
const dateFormat = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
const dateTimeFormat = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
const timeFormat = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
const relativeFormat = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })

export const formatNumber = (value: number) => numberFormat.format(value)

/** A calendar date from the API ("2026-11-03"), read as a local date so it never shifts a day. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const [y, m, d] = value.slice(0, 10).split('-').map(Number)
  if (!y || !m || !d) return value
  return dateFormat.format(new Date(y, m - 1, d))
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : dateTimeFormat.format(date)
}

export function formatTime(value: string | Date): string {
  const date = typeof value === 'string' ? new Date(value) : value
  return Number.isNaN(date.getTime()) ? String(value) : timeFormat.format(date)
}

/** "just now", "5 minutes ago", "yesterday"; the full date beyond a month. */
export function formatRelative(value: string | null | undefined, now = Date.now()): string {
  if (!value) return '—'
  const time = new Date(value).getTime()
  if (Number.isNaN(time)) return value
  const seconds = Math.round((time - now) / 1000)
  const abs = Math.abs(seconds)
  if (abs < 45) return 'just now'
  if (abs < 3600) return relativeFormat.format(Math.round(seconds / 60), 'minute')
  if (abs < 86_400) return relativeFormat.format(Math.round(seconds / 3600), 'hour')
  if (abs < 30 * 86_400) return relativeFormat.format(Math.round(seconds / 86_400), 'day')
  return formatDate(value)
}

/** "42 s", "3 min 12 s", "1 h 5 min". */
export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return '—'
  const total = Math.round(ms / 1000)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h) return `${h} h ${m} min`
  if (m) return s ? `${m} min ${s} s` : `${m} min`
  return `${s} s`
}

/** The time a background job ran: finished minus started, or until now while it runs. */
export function jobDuration(startedAt: string | null, finishedAt: string | null, now = Date.now()): string | null {
  if (!startedAt) return null
  const end = finishedAt ? new Date(finishedAt).getTime() : now
  return formatDuration(end - new Date(startedAt).getTime())
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${formatNumber(count)} ${count === 1 ? one : many}`
}

export function formatYears(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${formatNumber(value)} ${value === 1 ? 'yr' : 'yrs'}`
}

/** The first 8 characters of an ID, enough to tell runs apart. */
export const shortId = (id: string) => id.slice(0, 8)

export const JOB_TYPE_LABEL: Record<JobType, string> = {
  full_time: 'Full-time',
  part_time: 'Part-time',
  contract: 'Contract',
  internship: 'Internship',
  temporary: 'Temporary',
  unknown: 'Not stated',
}

/** The job type where no "Job type" label stands next to it (list lines, page subtitles, the filter). */
export const jobTypeText = (type: JobType) => (type === 'unknown' ? 'Type not stated' : JOB_TYPE_LABEL[type])

export const BACKGROUND_TYPE_LABEL: Record<BackgroundJobType, string> = {
  crawl: 'Crawl',
  resume: 'Resume upload',
  match: 'Match run',
}

export const STATUS_LABEL: Record<BackgroundJobStatus, string> = {
  queued: 'Queued',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

/** What one counted item is, per background job type. */
export const ITEM_NOUN: Record<BackgroundJobType, [string, string]> = {
  crawl: ['page', 'pages'],
  resume: ['file', 'files'],
  match: ['candidate', 'candidates'],
}

export const isActive = (status: BackgroundJobStatus) => status === 'queued' || status === 'running'

const PERIOD: Record<string, string> = { year: 'a year', month: 'a month', week: 'a week', day: 'a day', hour: 'an hour' }

/** "INR 9,00,000 – 14,00,000 a year", the posting's own text, or null. */
export function formatSalary(salary: Salary | null, text?: string | null): string | null {
  if (salary && (salary.min !== null || salary.max !== null)) {
    const amount = (n: number) => new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(n)
    const range =
      salary.min !== null && salary.max !== null && salary.min !== salary.max
        ? `${amount(salary.min)} – ${amount(salary.max)}`
        : amount((salary.min ?? salary.max) as number)
    return [salary.currency, range, salary.period ? PERIOD[salary.period] ?? `per ${salary.period}` : null].filter(Boolean).join(' ')
  }
  return text || null
}
