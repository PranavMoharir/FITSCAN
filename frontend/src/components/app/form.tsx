import { TriangleAlert } from 'lucide-react'
import { type ReactElement, cloneElement, useId } from 'react'

import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

interface FieldProps {
  label: string
  hint?: string
  error?: string
  optional?: boolean
  className?: string
  /** The control (Input, Textarea, Select trigger); it receives id, aria-invalid and aria-describedby. */
  children: ReactElement<Record<string, unknown>>
}

/** A labelled form control with its hint and, when the value is rejected, the reason under it. */
export function Field({ label, hint, error, optional, className, children }: FieldProps) {
  const generated = useId()
  const id = typeof children.props.id === 'string' ? children.props.id : generated
  const hintId = hint ? `${id}-hint` : undefined
  const errorId = error ? `${id}-error` : undefined
  return (
    <div className={cn('grid gap-2', className)}>
      <Label htmlFor={id} className="flex items-baseline justify-between gap-2">
        {label}
        {optional && <span className="text-xs font-normal text-subtle-foreground">Optional</span>}
      </Label>
      {cloneElement(children, {
        id,
        'aria-invalid': error ? true : undefined,
        'aria-describedby': [errorId, hintId].filter(Boolean).join(' ') || undefined,
      })}
      {error && (
        <p id={errorId} className="flex items-start gap-1.5 text-[13px] leading-snug text-destructive">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          {error}
        </p>
      )}
      {hint && (
        <p id={hintId} className="text-xs leading-relaxed text-subtle-foreground">
          {hint}
        </p>
      )}
    </div>
  )
}

/** A message for the whole form (for example the server could not queue the job). */
export function FormAlert({ children }: { children: React.ReactNode }) {
  return (
    <p role="alert" className="flex items-start gap-2 rounded-lg border border-destructive/25 bg-destructive/[0.06] px-3.5 py-2.5 text-[13px] leading-relaxed text-destructive">
      <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{children}</span>
    </p>
  )
}
