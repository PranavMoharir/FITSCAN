import { type DependencyList, useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from '@/api/client'

export interface Resource<T> {
  data?: T
  error?: ApiError
  /** True until the first answer (or error) arrives. */
  loading: boolean
  /** True while a later request runs; the previous data stays on screen meanwhile. */
  refreshing: boolean
  /** Load again, keeping the current data visible. */
  reload: () => Promise<void>
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  return new ApiError(0, { code: 'CLIENT_ERROR', message: error instanceof Error ? error.message : 'Unknown error.' })
}

const isAbort = (error: unknown) => error instanceof DOMException && error.name === 'AbortError'

/**
 * Loads data with `load` whenever `deps` change. Old answers never overwrite newer ones: each
 * request aborts the previous one. Data from the last success stays visible while reloading.
 */
export function useResource<T>(load: (signal: AbortSignal) => Promise<T>, deps: DependencyList): Resource<T> {
  const [state, setState] = useState<{ data?: T; error?: ApiError; loading: boolean; refreshing: boolean }>({
    loading: true,
    refreshing: false,
  })
  const loadRef = useRef(load)
  loadRef.current = load
  const controllerRef = useRef<AbortController | null>(null)

  const run = useCallback(async () => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setState((s) => (s.data === undefined && !s.error ? s : { ...s, refreshing: true }))
    try {
      const data = await loadRef.current(controller.signal)
      if (!controller.signal.aborted) setState({ data, error: undefined, loading: false, refreshing: false })
    } catch (error) {
      if (isAbort(error) || controller.signal.aborted) return
      setState((s) => ({ ...s, error: toApiError(error), loading: false, refreshing: false }))
    }
  }, [])

  useEffect(() => {
    void run()
    return () => controllerRef.current?.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the caller lists what `load` depends on
  }, deps)

  return { ...state, reload: run }
}
