// The four scoring weights (LLD §7.4): whole numbers from 0 to 100 that add up to exactly 100.
// The server checks the same rules again; weights are never rescaled.

import { Check, RotateCcw, TriangleAlert } from 'lucide-react'

import { Field } from '@/components/app/form'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { formatNumber } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { MatchWeights } from '@/types/api'

export const WEIGHT_PARTS = [
  { key: 'required', letter: 'R', label: 'Required skills', hint: 'Share of the job’s required skills the candidate has.' },
  { key: 'nice', letter: 'N', label: 'Nice-to-have skills', hint: 'Share of the preferred skills the candidate has.' },
  { key: 'experience', letter: 'E', label: 'Experience', hint: 'Years of experience against the job’s minimum.' },
  { key: 'location', letter: 'L', label: 'Location', hint: 'Same city, or a remote job.' },
] as const

export type WeightKey = (typeof WEIGHT_PARTS)[number]['key']
export type WeightDraft = Record<WeightKey, string>
export type WeightErrors = Partial<Record<WeightKey | 'total', string>>

const WHOLE = /^\d{1,3}$/

export const draftOf = (weights: MatchWeights): WeightDraft => ({
  required: String(weights.required),
  nice: String(weights.nice),
  experience: String(weights.experience),
  location: String(weights.location),
})

/** "70 / 15 / 10 / 5", in the R, N, E, L order. */
export const weightsText = (w: MatchWeights) => WEIGHT_PARTS.map((p) => formatNumber(w[p.key])).join(' / ')

export const sameWeights = (a: MatchWeights, b: MatchWeights) => WEIGHT_PARTS.every((p) => a[p.key] === b[p.key])

/** A run's recorded weights from its params, or null (a run from before weights were recorded). */
export function weightsOf(value: unknown): MatchWeights | null {
  if (!value || typeof value !== 'object') return null
  const v = value as Record<string, unknown>
  return WEIGHT_PARTS.every((p) => typeof v[p.key] === 'number') ? (v as unknown as MatchWeights) : null
}

interface DraftCheck {
  /** Set only when the draft is valid: four whole numbers that add up to 100. */
  weights?: MatchWeights
  errors: WeightErrors
  /** The sum, once every field holds a whole number from 0 to 100. */
  total: number | null
  /** What the total line says. */
  status: string
}

/** The weights if the draft is valid; otherwise the reason for each field and for the total. */
export function checkDraft(draft: WeightDraft): DraftCheck {
  const errors: WeightErrors = {}
  let empty = false
  for (const p of WEIGHT_PARTS) {
    const text = draft[p.key].trim()
    if (text === '') {
      errors[p.key] = 'Enter a whole number from 0 to 100.'
      empty = true
    } else if (!WHOLE.test(text) || Number(text) > 100) errors[p.key] = 'Use a whole number from 0 to 100.'
  }
  if (Object.keys(errors).length) {
    const bad = WEIGHT_PARTS.some((p) => draft[p.key].trim() !== '' && errors[p.key])
    const status = bad ? 'Each weight must be a whole number from 0 to 100.' : empty ? 'Enter all four weights; they must add up to 100.' : ''
    return { errors, total: null, status }
  }
  const weights = Object.fromEntries(WEIGHT_PARTS.map((p) => [p.key, Number(draft[p.key])])) as unknown as MatchWeights
  const total = WEIGHT_PARTS.reduce((sum, p) => sum + weights[p.key], 0)
  if (total === 100) return { weights, errors, total, status: 'Total 100 of 100.' }
  errors.total = `The weights add up to ${total}. Make them add up to exactly 100.`
  const status = total < 100 ? `Total ${total} of 100: ${100 - total} to go.` : `Total ${total} of 100: ${total - 100} too many.`
  return { errors, total, status }
}

interface WeightsEditorProps {
  draft: WeightDraft
  onChange: (key: WeightKey, value: string) => void
  defaults: MatchWeights
  onReset: () => void
  /** Errors from the server, shown in addition to the browser's own checks. */
  serverErrors?: WeightErrors
  disabled?: boolean
}

export function WeightsEditor({ draft, onChange, defaults, onReset, serverErrors = {}, disabled }: WeightsEditorProps) {
  const { weights, errors, status } = checkDraft(draft)
  // An empty field is not flagged while typing; the total line says what is missing.
  const shown = (key: WeightKey) => serverErrors[key] ?? (draft[key].trim() === '' ? undefined : errors[key])
  const isDefault = WEIGHT_PARTS.every((p) => draft[p.key].trim() === String(defaults[p.key]))
  const exact = Boolean(weights) && !serverErrors.total

  return (
    <fieldset disabled={disabled} className="grid gap-4">
      <legend className="sr-only">Scoring weights</legend>
      <div className="grid gap-4 sm:grid-cols-2">
        {WEIGHT_PARTS.map((p) => (
          // content-start: a field beside a taller one (a two-line hint) keeps its input aligned at the top.
          <Field key={p.key} label={`${p.label} (${p.letter})`} hint={p.hint} error={shown(p.key)} className="content-start">
            <Input
              id={`weight-${p.key}`}
              type="number"
              inputMode="numeric"
              min={0}
              max={100}
              step={1}
              value={draft[p.key]}
              onChange={(e) => onChange(p.key, e.target.value)}
            />
          </Field>
        ))}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-lg bg-foreground/[0.03] px-4 py-3">
        <p
          id="weights-total"
          role="status"
          className={cn('flex items-start gap-2 text-[13px] font-medium leading-snug', exact ? 'text-foreground' : 'text-destructive')}
        >
          {exact ? <Check className="mt-0.5 size-4 shrink-0 text-accent-ink" aria-hidden="true" /> : <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />}
          <span className="tabular-nums">{serverErrors.total ?? status}</span>
        </p>
        <Button type="button" variant="ghost" size="sm" onClick={onReset} disabled={disabled || isDefault}>
          <RotateCcw aria-hidden="true" />
          Reset to defaults ({weightsText(defaults)})
        </Button>
      </div>
    </fieldset>
  )
}
