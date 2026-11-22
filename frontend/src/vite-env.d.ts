/// <reference types="vite/client" />

// Build-time variables (read from the repository-root .env, or from Docker build args).
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_POLL_INTERVAL_MS?: string
  /** "false" hides every link to the API documentation (production, where the API does not serve it). */
  readonly VITE_API_DOCS_ENABLED?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
