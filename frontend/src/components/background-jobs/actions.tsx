import { CircleStop } from 'lucide-react'
import { useState } from 'react'

import { ApiError, cancelBackgroundJob, createMatchJob } from '@/api/client'
import { ConfirmDialog } from '@/components/app/ConfirmDialog'
import { jobLabel } from '@/components/app/job-text'
import { useToast } from '@/components/app/toaster'
import { Button } from '@/components/ui/button'
import type { BackgroundJobCreated, BackgroundJobSummary } from '@/types/api'

interface RecomputeProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (job: BackgroundJobCreated) => void
}

/** "Recompute matches" (POST /background-jobs/match): asks first, because it replaces every stored match. */
export function RecomputeMatchesDialog({ open, onOpenChange, onCreated }: RecomputeProps) {
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Recompute all matches?"
      description="Scores every candidate against every job. The current matches stay in place until the run finishes, and are kept if it fails or is cancelled."
      confirmLabel="Recompute matches"
      onConfirm={async () => onCreated(await createMatchJob())}
    />
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
