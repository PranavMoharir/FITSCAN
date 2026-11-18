// TypeScript types that mirror the API's Pydantic schemas (backend/app/schemas).

/** Error envelope returned by every failed request (HLD §12.1). */
export interface ApiErrorBody {
  code: string
  message: string
  details?: Record<string, unknown>
}

export interface ApiErrorEnvelope {
  error: ApiErrorBody
}

/** GET /health (backend/app/schemas/health.py). */
export type CheckStatus = 'ok' | 'down'

export interface HealthResponse {
  status: 'ok'
  database: CheckStatus
  redis: CheckStatus
}
