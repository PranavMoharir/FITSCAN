import { CircleCheck, FileText, FileUp, Loader2, TriangleAlert, X } from 'lucide-react'
import { type DragEvent, useId, useRef, useState } from 'react'

import { createResumeJob } from '@/api/client'
import { FormAlert } from '@/components/app/form'
import { describeError } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { toApiError } from '@/hooks/useResource'
import { formatBytes, plural } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { RejectedFileInfo, ResumeJobCreated } from '@/types/api'

interface Result {
  job?: ResumeJobCreated
  accepted: number
  /** The API identifies files by position only; names come from the files chosen here (LLD §4.5). */
  rejected: { name: string; message: string }[]
}

interface UploadResumesDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (job: ResumeJobCreated) => void
  onViewJob: (id: string) => void
}

const isPdfName = (name: string) => /\.pdf$/i.test(name)

/** "Upload resumes" (LLD §8.2): several PDF files at once; each is accepted or rejected on its own. */
export function UploadResumesDialog({ open, onOpenChange, onCreated, onViewJob }: UploadResumesDialogProps) {
  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const [pending, setPending] = useState(false)
  const [formError, setFormError] = useState<string>()
  const [result, setResult] = useState<Result>()
  const inputRef = useRef<HTMLInputElement>(null)
  const inputId = useId()

  const add = (list: FileList | null) => {
    if (!list?.length) return
    setFormError(undefined)
    setFiles((current) => {
      const seen = new Set(current.map((f) => `${f.name}:${f.size}`))
      return [...current, ...Array.from(list).filter((f) => !seen.has(`${f.name}:${f.size}`))]
    })
  }

  const reset = () => {
    setFiles([])
    setResult(undefined)
    setFormError(undefined)
  }

  const named = (items: RejectedFileInfo[]) => items.map((r) => ({ name: files[r.index]?.name ?? `File ${r.index + 1}`, message: r.message }))

  const submit = async () => {
    setPending(true)
    setFormError(undefined)
    try {
      const job = await createResumeJob(files)
      setResult({ job, accepted: job.accepted_files.length, rejected: named(job.rejected_files) })
      onCreated(job)
    } catch (e) {
      const error = toApiError(e)
      const rejected = error.details?.rejected_files
      if (error.code === 'NO_VALID_FILES' && Array.isArray(rejected)) {
        setResult({ accepted: 0, rejected: named(rejected as RejectedFileInfo[]) })
      } else {
        setFormError(error.fieldErrors[0]?.message ? capitalise(error.fieldErrors[0].message) : describeError(error).message)
      }
    } finally {
      setPending(false)
    }
  }

  const onDrop = (event: DragEvent) => {
    event.preventDefault()
    setDragging(false)
    add(event.dataTransfer.files)
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (pending) return
        if (!next) reset()
        onOpenChange(next)
      }}
    >
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{result ? (result.job ? 'Resumes uploaded' : 'No file was accepted') : 'Upload resumes'}</DialogTitle>
          <DialogDescription>
            {result
              ? result.job
                ? `${plural(result.accepted, 'file')} will be parsed in a background job${result.rejected.length ? `; ${plural(result.rejected.length, 'file was', 'files were')} rejected` : ''}.`
                : 'Nothing was uploaded and no job was created. Each file’s reason is below.'
              : 'PDF resumes, one or many. Scanned files are read with OCR. Each file is checked on its own.'}
          </DialogDescription>
        </DialogHeader>

        {result ? (
          <div className="grid gap-3" role="status">
            {result.accepted > 0 && (
              <p className="flex items-center gap-2 text-sm font-medium">
                <CircleCheck className="size-4 text-accent-ink" aria-hidden="true" />
                {plural(result.accepted, 'file')} accepted
              </p>
            )}
            {result.rejected.length > 0 && (
              <div className="rounded-lg border border-destructive/20 bg-destructive/[0.04] p-3.5">
                <p className="text-[13px] font-semibold text-destructive">Rejected</p>
                <ul className="mt-2 space-y-1.5">
                  {result.rejected.map((r, i) => (
                    <li key={i} className="flex items-start gap-2 text-[13px]">
                      <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-destructive" aria-hidden="true" />
                      <span className="min-w-0">
                        <span className="break-all font-medium text-foreground">{r.name}</span>
                        <span className="text-muted-foreground"> — {r.message}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <div className="grid gap-4">
            {formError && <FormAlert>{formError}</FormAlert>}
            <div
              onDragOver={(e) => {
                e.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={cn(
                'flex flex-col items-center rounded-xl border border-dashed px-6 py-8 text-center transition-colors duration-200',
                dragging ? 'border-primary bg-primary/[0.05]' : 'border-foreground/25 bg-foreground/[0.02]',
              )}
            >
              <span className="grid size-11 place-items-center rounded-full bg-accent-solid/[0.08] text-accent-ink" aria-hidden="true">
                <FileUp className="size-5" />
              </span>
              <p className="mt-3 text-sm font-medium">Drop PDF files here</p>
              <p className="mt-1 text-[13px] text-muted-foreground">or</p>
              <Button type="button" variant="outline" size="sm" className="mt-2" onClick={() => inputRef.current?.click()}>
                Choose files
              </Button>
              <label htmlFor={inputId} className="sr-only">
                Resume files (PDF)
              </label>
              <input
                ref={inputRef}
                id={inputId}
                type="file"
                multiple
                accept=".pdf,application/pdf"
                className="sr-only"
                tabIndex={-1}
                onChange={(e) => {
                  add(e.target.files)
                  e.target.value = ''
                }}
              />
            </div>
            {files.length > 0 && (
              <ul className="max-h-56 divide-y divide-border overflow-y-auto rounded-lg border border-border" aria-label="Chosen files">
                {files.map((file, i) => (
                  <li key={`${file.name}:${file.size}`} className="flex items-center gap-3 px-3.5 py-2.5">
                    <FileText className="size-4 shrink-0 text-subtle-foreground" aria-hidden="true" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium">{file.name}</span>
                      <span className="flex items-center gap-1.5 text-xs text-subtle-foreground">
                        {formatBytes(file.size)}
                        {!isPdfName(file.name) && (
                          <span className="inline-flex items-center gap-1 text-destructive">
                            <TriangleAlert className="size-3" aria-hidden="true" /> Not a .pdf file
                          </span>
                        )}
                      </span>
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      onClick={() => setFiles((current) => current.filter((_, k) => k !== i))}
                      aria-label={`Remove ${file.name}`}
                      disabled={pending}
                    >
                      <X aria-hidden="true" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <DialogFooter>
          {result ? (
            <>
              {result.job ? (
                <>
                  <DialogClose asChild>
                    <Button variant="outline">Done</Button>
                  </DialogClose>
                  <Button
                    onClick={() => {
                      const id = result.job!.background_job_id
                      reset()
                      onViewJob(id)
                    }}
                  >
                    View the run
                  </Button>
                </>
              ) : (
                <Button onClick={reset}>Choose other files</Button>
              )}
            </>
          ) : (
            <>
              <DialogClose asChild>
                <Button variant="outline" disabled={pending}>
                  Cancel
                </Button>
              </DialogClose>
              <Button onClick={() => void submit()} disabled={pending || files.length === 0}>
                {pending && <Loader2 className="animate-spin" aria-hidden="true" />}
                {files.length ? `Upload ${plural(files.length, 'file')}` : 'Upload'}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

const capitalise = (text: string) => (text ? text[0].toUpperCase() + text.slice(1) + (/[.!?]$/.test(text) ? '' : '.') : text)
