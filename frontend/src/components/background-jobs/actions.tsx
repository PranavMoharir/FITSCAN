import { CircleStop, Loader2 } from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'

import { ApiError, cancelBackgroundJob, createMatchJob, getMatchWeights } from '@/api/client'
import { ConfirmDialog } from '@/components/app/ConfirmDialog'
import { errorSentence, FormAlert } from '@/components/app/form'
import { jobLabel } from '@/components/app/job-text'
import { describeError } from '@/components/app/states'
import { useToast } from '@/components/app/toaster'
import { checkDraft, draftOf, WEIGHT_PARTS, type WeightDraft, type WeightErrors, WeightsEditor } from '@/components/matches/WeightsEditor'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { toApiError } from '@/hooks/useResource'
import type { BackgroundJobCreated, BackgroundJobSummary, MatchWeightsInfo } from '@/types/api'

interface RecomputeProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (job: BackgroundJobCreated) => void
}

const isAbort = (e: unknown) => e instanceof DOMException && e.name === 'AbortError'

/**
 * "Recompute matches" (POST /background-jobs/match) with the scoring weights (LLD §7.4). It asks
 * first, because it replaces every stored match. The active weights are filled in; the run records
 * the weights it is sent, and they stay active for later runs.
 */
export function RecomputeMatchesDialog({ open, onOpenChange, onCreated }: RecomputeProps) {
  const [info, setInfo] = useState<MatchWeightsInfo>()
  const [loadError, setLoadError] = useState<ApiError>()
  const [attempt, setAttempt] = useState(0)
  const [draft, setDraft] = useState<WeightDraft>()
  const [serverErrors, setServerErrors] = useState<WeightErrors>({})
  const [formError, setFormError] = useState<string>()
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    setInfo(undefined)
    setLoadError(undefined)
    setDraft(undefined)
    setServerErrors({})
    setFormError(undefined)
    getMatchWeights(controller.signal)
      .then((data) => {
        setInfo(data)
        setDraft(draftOf(data.active.weights))
      })
      .catch((e) => {
        if (!isAbort(e)) setLoadError(toApiError(e))
      })
    return () => controller.abort()
  }, [open, attempt])

  const check = draft ? checkDraft(draft) : undefined

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!check?.weights) return
    setPending(true)
    setFormError(undefined)
    setServerErrors({})
    try {
      onCreated(await createMatchJob(check.weights))
    } catch (e) {
      const error = toApiError(e)
      const byField: WeightErrors = {}
      const other: string[] = []
      for (const fe of error.fieldErrors) {
        const key = WEIGHT_PARTS.find((p) => fe.field === `body.weights.${p.key}`)?.key
        if (key) byField[key] = errorSentence(fe.message)
        else if (fe.field === 'body.weights') byField.total = errorSentence(fe.message)
        else other.push(errorSentence(fe.message))
      }
      setServerErrors(byField)
      if (other.length) setFormError(other.join(' '))
      else if (!error.fieldErrors.length) setFormError(describeError(error).message)
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent className="max-w-xl">
        <form onSubmit={(e) => void submit(e)} noValidate className="grid gap-5">
          <DialogHeader>
            <DialogTitle>Recompute all matches?</DialogTitle>
            <DialogDescription>
              Scores every candidate against every job with these weights. The current matches stay in place until the run finishes, and are kept if it fails or is cancelled.
            </DialogDescription>
          </DialogHeader>
          {formError && <FormAlert>{formError}</FormAlert>}
          {loadError ? (
            <div className="grid gap-3">
              <FormAlert>The weights could not be loaded, so the run was not started. {describeError(loadError).message}</FormAlert>
              <div>
                <Button type="button" variant="outline" size="sm" onClick={() => setAttempt((n) => n + 1)}>
                  Try again
                </Button>
              </div>
            </div>
          ) : !info || !draft ? (
            <div className="grid gap-4 sm:grid-cols-2" aria-busy="true" aria-label="Loading the weights">
              {WEIGHT_PARTS.map((p) => (
                <Skeleton key={p.key} className="h-[5.5rem] rounded-lg" />
              ))}
            </div>
          ) : (
            <>
              <WeightsEditor
                draft={draft}
                onChange={(key, value) => {
                  setDraft((d) => d && { ...d, [key]: value })
                  setServerErrors((s) => ({ ...s, [key]: undefined, total: undefined }))
                }}
                defaults={info.default}
                onReset={() => {
                  setDraft(draftOf(info.default))
                  setServerErrors({})
                }}
                serverErrors={serverErrors}
                disabled={pending}
              />
              <p className="text-xs leading-relaxed text-subtle-foreground">
                The active weights are filled in. The weights you run with stay active for later runs until you change them.
              </p>
            </>
          )}
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline" disabled={pending}>
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={pending || !check?.weights} aria-describedby={draft ? 'weights-total' : undefined}>
              {pending && <Loader2 className="animate-spin" aria-hidden="true" />}
              Recompute matches
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

interface CancelProps {
  job: Pick<BackgroundJobSummary, 'background_job_id' | 'type' | 'status'>
  onDone: () => void
  size?: 'sm' | 'xs'
}

/** Cancel on a queued or running job (LLD §5.7): a queued job is cancelled at once, a running one stops after its current item. */
export function CancelJobButton({ job, onDone, size = 'sm' }: CancelProps) {
  const [open, setOpen] = useState(false)
  const toast = useToast()
  const label = jobLabel(job).toLowerCase()
  const running = job.status === 'running'
  return (
    <>
      <Button variant="destructive" size={size} onClick={() => setOpen(true)} aria-label={`${running ? 'Stop' : 'Cancel'} this ${label}`}>
        <CircleStop aria-hidden="true" />
        {running ? 'Stop' : 'Cancel'}
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        destructive
        title={running ? `Stop this ${label}?` : `Cancel this ${label}?`}
        description={
          running
            ? 'The worker stops after the item it is working on. Everything saved so far is kept.'
            : 'It has not started yet, so nothing has been processed. It will not run.'
        }
        confirmLabel={running ? 'Stop the run' : 'Cancel the run'}
        cancelLabel={running ? 'Keep running' : 'Keep it'}
        onConfirm={async () => {
          try {
            const result = await cancelBackgroundJob(job.background_job_id)
            toast(
              result.cancel_requested
                ? { title: 'Stopping after the current item', description: 'The run will show as cancelled in a moment.' }
                : { title: 'Run cancelled' },
            )
          } catch (e) {
            // 409: it finished in the meantime. Say so and show the real state.
            if (e instanceof ApiError && e.status === 409) {
              toast({ title: 'Nothing to cancel', description: e.message, variant: 'error' })
              onDone()
              return
            }
            throw e
          }
          onDone()
        }}
      />
    </>
  )
}
