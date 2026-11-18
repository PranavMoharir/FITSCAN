/// <reference types="vite/client" />

// Build-time variables (read from the repository-root .env, or from Docker build args).
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_POLL_INTERVAL_MS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
