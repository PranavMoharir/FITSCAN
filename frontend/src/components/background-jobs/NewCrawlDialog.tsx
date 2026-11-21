import { Loader2 } from 'lucide-react'
import { type FormEvent, useState } from 'react'

import { createCrawlJob } from '@/api/client'
import { errorSentence as sentence, Field, FormAlert } from '@/components/app/form'
import { describeError } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input, Textarea } from '@/components/ui/input'
import { toApiError } from '@/hooks/useResource'
import type { BackgroundJobCreated } from '@/types/api'

type FieldName = 'seed_url' | 'max_depth' | 'max_pages' | 'allowed_domains'
const INITIAL = { seed_url: '', max_depth: '2', max_pages: '50', allowed_domains: '' }

/** "body.max_pages" or "body.allowed_domains.0" from the API, as one of the form's fields. */
function fieldOf(apiField: string): FieldName | null {
  const name = apiField.replace(/^body\./, '').split('.')[0]
  return (['seed_url', 'max_depth', 'max_pages', 'allowed_domains'] as const).find((f) => f === name) ?? null
}

/** Checks the browser can do before sending; the server checks everything again (LLD §5.9). */
function validate(values: typeof INITIAL): Partial<Record<FieldName, string>> {
  const errors: Partial<Record<FieldName, string>> = {}
  try {
    const url = new URL(values.seed_url.trim())
    if (url.protocol !== 'http:' && url.protocol !== 'https:') errors.seed_url = 'Use an http:// or https:// address.'
  } catch {
    errors.seed_url = values.seed_url.trim() ? 'Enter a full address, for example https://example.com/careers.' : 'Enter the address to start from.'
  }
  const depth = Number(values.max_depth)
  if (!Number.isInteger(depth) || depth < 1 || depth > 10) errors.max_depth = 'Enter a whole number from 1 to 10.'
  const pages = Number(values.max_pages)
  if (!Number.isInteger(pages) || pages < 1) errors.max_pages = 'Enter a whole number of at least 1.'
  return errors
}

const splitHosts = (text: string) => text.split(/[\s,]+/).map((h) => h.trim()).filter(Boolean)

interface NewCrawlDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (job: BackgroundJobCreated) => void
}

/** "New crawl" (LLD §8.2): seed URL, max_depth, max_pages and allowed domains. */
export function NewCrawlDialog({ open, onOpenChange, onCreated }: NewCrawlDialogProps) {
  const [values, setValues] = useState(INITIAL)
  const [errors, setErrors] = useState<Partial<Record<FieldName, string>>>({})
  const [formError, setFormError] = useState<string>()
  const [pending, setPending] = useState(false)

  const set = (name: FieldName) => (event: { target: { value: string } }) => {
    setValues((v) => ({ ...v, [name]: event.target.value }))
    setErrors((e) => ({ ...e, [name]: undefined }))
  }

  const reset = () => {
    setValues(INITIAL)
    setErrors({})
    setFormError(undefined)
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setFormError(undefined)
    const found = validate(values)
    setErrors(found)
    if (Object.keys(found).length) {
      document.getElementById(`crawl-${Object.keys(found)[0]}`)?.focus()
      return
    }
    setPending(true)
    try {
      const hosts = splitHosts(values.allowed_domains)
      const job = await createCrawlJob({
        seed_url: values.seed_url.trim(),
        max_depth: Number(values.max_depth),
        max_pages: Number(values.max_pages),
        allowed_domains: hosts.length ? hosts : null,
      })
      reset()
      onCreated(job)
    } catch (e) {
      const error = toApiError(e)
      const byField: Partial<Record<FieldName, string>> = {}
      const other: string[] = []
      for (const fe of error.fieldErrors) {
        const name = fieldOf(fe.field)
        if (name && !byField[name]) byField[name] = sentence(fe.message)
        else if (!name) other.push(sentence(fe.message))
      }
      setErrors(byField)
      if (other.length) setFormError(other.join(' '))
      else if (!error.fieldErrors.length) setFormError(describeError(error).message)
      const first = Object.keys(byField)[0]
      if (first) document.getElementById(`crawl-${first}`)?.focus()
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (pending) return
        if (!next) setFormError(undefined)
        onOpenChange(next)
      }}
    >
      <DialogContent className="max-w-xl">
        <form onSubmit={(e) => void submit(e)} noValidate className="grid gap-5">
          <DialogHeader>
            <DialogTitle>New crawl</DialogTitle>
            <DialogDescription>Collect job postings from a site. The crawl runs as a background job you can follow live.</DialogDescription>
          </DialogHeader>
          {formError && <FormAlert>{formError}</FormAlert>}
          <Field label="Seed URL" hint="The crawler starts here and follows links on the allowed hosts." error={errors.seed_url}>
            <Input id="crawl-seed_url" type="url" inputMode="url" autoComplete="url" placeholder="https://example.com/careers" value={values.seed_url} onChange={set('seed_url')} />
          </Field>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Max depth" hint="How far to follow links from the seed URL: 1 to 10." error={errors.max_depth}>
              <Input id="crawl-max_depth" type="number" inputMode="numeric" min={1} max={10} step={1} value={values.max_depth} onChange={set('max_depth')} />
            </Field>
            <Field label="Max pages" hint="Stops after this many pages; the server sets the maximum." error={errors.max_pages}>
              <Input id="crawl-max_pages" type="number" inputMode="numeric" min={1} step={1} value={values.max_pages} onChange={set('max_pages')} />
            </Field>
          </div>
          <Field
            label="Allowed domains"
            optional
            hint="One host per line or separated by commas. Leave empty to stay on the seed URL's host; if you list hosts, include it."
            error={errors.allowed_domains}
          >
            <Textarea id="crawl-allowed_domains" rows={2} placeholder={'example.com\njobs.example.com'} value={values.allowed_domains} onChange={set('allowed_domains')} spellCheck={false} />
          </Field>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline" disabled={pending}>
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={pending}>
              {pending && <Loader2 className="animate-spin" aria-hidden="true" />}
              Start crawl
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
