// Typed API client (LLD §8.4): wraps fetch, holds the base URL, exposes one function per
// endpoint and turns the API's error envelope into an ApiError, so every page shows errors
// the same way. Endpoints are added here as the backend implements them.

import type { ApiErrorBody, ApiErrorEnvelope, HealthResponse } from '@/types/api'

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
}

function isErrorEnvelope(data: unknown): data is ApiErrorEnvelope {
  if (typeof data !== 'object' || data === null || !('error' in data)) return false
  const error = (data as { error: unknown }).error
  return typeof error === 'object' && error !== null && 'code' in error && 'message' in error
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init)
  } catch {
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

/** GET /health: database and Redis reachability. Throws ApiError (503) if either is down. */
export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health')
}
