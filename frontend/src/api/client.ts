// Typed API client (LLD §8.4): wraps fetch, holds the base URL, exposes one function per
// endpoint and turns the API's error envelope into an ApiError, so every page shows errors
// the same way. Only endpoints the backend implements are listed here.

import type {
  ApiErrorBody,
  ApiErrorEnvelope,
  BackgroundJobCreated,
  BackgroundJobDetail,
  BackgroundJobList,
  BackgroundJobStatus,
  BackgroundJobType,
  CancelResult,
  CandidateDetail,
  CandidateFilters,
  CandidateList,
  CandidateMatches,
  CrawlRequest,
  ExportFormat,
  FieldError,
  HealthResponse,
  JobFilters,
  JobList,
  JobView,
  JobMatches,
  LogLevel,
  LogList,
  MatchWeights,
  MatchWeightsInfo,
  ResumeJobCreated,
  SkillList,
  SourceList,
} from '@/types/api'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '')

export class ApiError extends Error {
  /** HTTP status, or 0 when the API could not be reached at all. */
  readonly status: number
  readonly code: string
  readonly details?: Record<string, unknown>

  constructor(status: number, body: ApiErrorBody) {
    super(body.message)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.details = body.details
  }

  /** The per-field reasons of a 422 VALIDATION_ERROR, if any. */
  get fieldErrors(): FieldError[] {
    const errors = this.details?.errors
    return Array.isArray(errors) ? (errors as FieldError[]) : []
  }
}

function isErrorEnvelope(data: unknown): data is ApiErrorEnvelope {
  if (typeof data !== 'object' || data === null || !('error' in data)) return false
  const error = (data as { error: unknown }).error
  return typeof error === 'object' && error !== null && 'code' in error && 'message' in error
}

type Query = Record<string, string | number | boolean | null | undefined>

/** `?a=1&b=x` from the defined, non-empty values; '' when there are none. */
export function queryString(params: object = {}): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params as Query)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, { code: 'NETWORK_ERROR', message: `Cannot reach the API at ${API_BASE_URL}.` })
  }

  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const body = isErrorEnvelope(data)
      ? data.error
      : { code: `HTTP_${response.status}`, message: response.statusText || 'Request failed.' }
    throw new ApiError(response.status, body)
  }
  return data as T
}

const get = <T>(path: string, signal?: AbortSignal) => request<T>(path, { signal })
const postJson = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: 'POST',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

// --- Health -----------------------------------------------------------------------------------

/** GET /health: database and Redis reachability. Throws ApiError (503) if either is down. */
export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return get<HealthResponse>('/health', signal)
}

// --- Background jobs (LLD §4.5) ---------------------------------------------------------------

export interface BackgroundJobQuery {
  type?: BackgroundJobType
  status?: BackgroundJobStatus
  page?: number
  page_size?: number
}

/** GET /background-jobs: newest first. */
export function listBackgroundJobs(query: BackgroundJobQuery = {}, signal?: AbortSignal): Promise<BackgroundJobList> {
  return get<BackgroundJobList>(`/background-jobs${queryString({ ...query })}`, signal)
}

export function getBackgroundJob(id: string, signal?: AbortSignal): Promise<BackgroundJobDetail> {
  return get<BackgroundJobDetail>(`/background-jobs/${encodeURIComponent(id)}`, signal)
}

/** GET /background-jobs/{id}/logs: up to 500 lines after `afterId`, oldest first. */
export function getBackgroundJobLogs(id: string, afterId = 0, level?: LogLevel, signal?: AbortSignal): Promise<LogList> {
  return get<LogList>(`/background-jobs/${encodeURIComponent(id)}/logs${queryString({ after_id: afterId, level })}`, signal)
}

/** POST /background-jobs/{id}/cancel: 200 cancelled, 202 asked to stop, 409 already finished. */
export function cancelBackgroundJob(id: string): Promise<CancelResult> {
  return postJson<CancelResult>(`/background-jobs/${encodeURIComponent(id)}/cancel`)
}

export function createCrawlJob(body: CrawlRequest): Promise<BackgroundJobCreated> {
  return postJson<BackgroundJobCreated>('/background-jobs/crawl', body)
}

/** POST /background-jobs/resume as multipart/form-data, field `files`, one entry per file. */
export function createResumeJob(files: File[]): Promise<ResumeJobCreated> {
  const form = new FormData()
  for (const file of files) form.append('files', file, file.name)
  return request<ResumeJobCreated>('/background-jobs/resume', { method: 'POST', body: form })
}

/** POST /background-jobs/match. Without weights the run uses the active weights (LLD §7.4). */
export function createMatchJob(weights?: MatchWeights): Promise<BackgroundJobCreated> {
  return postJson<BackgroundJobCreated>('/background-jobs/match', weights ? { weights } : undefined)
}

/** GET /matching/weights: the default, active and current-results weights. */
export function getMatchWeights(signal?: AbortSignal): Promise<MatchWeightsInfo> {
  return get<MatchWeightsInfo>('/matching/weights', signal)
}

// --- Jobs and candidates (LLD §4.5-4.6) -------------------------------------------------------

export interface Paging {
  page?: number
  page_size?: number
}

export function searchJobs(query: JobFilters & Paging = {}, signal?: AbortSignal): Promise<JobList> {
  return get<JobList>(`/jobs${queryString({ ...query })}`, signal)
}

export function getJob(id: string, signal?: AbortSignal): Promise<JobView> {
  return get<JobView>(`/jobs/${encodeURIComponent(id)}`, signal)
}

export function getJobMatches(id: string, signal?: AbortSignal): Promise<JobMatches> {
  return get<JobMatches>(`/jobs/${encodeURIComponent(id)}/matches`, signal)
}

export function searchCandidates(query: CandidateFilters & Paging = {}, signal?: AbortSignal): Promise<CandidateList> {
  return get<CandidateList>(`/candidates${queryString({ ...query })}`, signal)
}

export function getCandidate(id: string, signal?: AbortSignal): Promise<CandidateDetail> {
  return get<CandidateDetail>(`/candidates/${encodeURIComponent(id)}`, signal)
}

export function getCandidateMatches(id: string, signal?: AbortSignal): Promise<CandidateMatches> {
  return get<CandidateMatches>(`/candidates/${encodeURIComponent(id)}/matches`, signal)
}

export function listSkills(signal?: AbortSignal): Promise<SkillList> {
  return get<SkillList>('/skills', signal)
}

/** GET /sources: the job sources the crawler supports (real first, then demo). */
export function listSources(signal?: AbortSignal): Promise<SourceList> {
  return get<SourceList>('/sources', signal)
}

// --- Exports (plain download links, LLD §8.4) -------------------------------------------------

/** The address of a CSV or JSON export with the same filters as the table it comes from. */
export function exportUrl(entity: 'jobs', format: ExportFormat, filters?: JobFilters): string
export function exportUrl(entity: 'candidates', format: ExportFormat, filters?: CandidateFilters): string
export function exportUrl(entity: 'matches', format: ExportFormat, filters?: CandidateFilters & { top?: number }): string
export function exportUrl(entity: 'jobs' | 'candidates' | 'matches', format: ExportFormat, filters: object = {}): string {
  return `${API_BASE_URL}/exports/${entity}${queryString({ ...filters, format })}`
}

/** The API's interactive reference and its machine-readable contract. */
export const API_DOCS_URL = `${API_BASE_URL}/docs`
