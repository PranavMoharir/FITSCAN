import { Loader2 } from 'lucide-react'
import { type ReactNode, useState } from 'react'

import { ApiError } from '@/api/client'
import { describeError } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { toApiError } from '@/hooks/useResource'

interface ConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: ReactNode
  confirmLabel: string
  cancelLabel?: string
  destructive?: boolean
  /** Runs when confirmed; the dialog closes when it resolves and shows the error when it throws. */
  onConfirm: () => Promise<void>
}

/** Asks before an action that cannot be undone or that replaces data. */
export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel, cancelLabel = 'Cancel', destructive, onConfirm }: ConfirmDialogProps) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<ApiError>()

  const confirm = async () => {
    setPending(true)
    setError(undefined)
    try {
      await onConfirm()
      onOpenChange(false)
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (pending) return
        if (!next) setError(undefined)
        onOpenChange(next)
      }}
    >
      <DialogContent className="max-w-md" showClose={!pending}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {error && (
          <p role="alert" className="rounded-lg border border-destructive/25 bg-destructive/[0.06] px-3.5 py-2.5 text-[13px] leading-relaxed text-destructive">
            {describeError(error).message}
          </p>
        )}
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" disabled={pending}>
              {cancelLabel}
            </Button>
          </DialogClose>
          <Button variant={destructive ? 'destructive' : 'default'} onClick={() => void confirm()} disabled={pending}>
            {pending && <Loader2 className="animate-spin" aria-hidden="true" />}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
