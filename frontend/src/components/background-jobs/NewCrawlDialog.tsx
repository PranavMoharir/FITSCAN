import { Loader2 } from 'lucide-react'
import { type FormEvent, useState } from 'react'

import { createCrawlJob } from '@/api/client'
import { errorSentence as sentence, Field, FormAlert } from '@/components/app/form'
import { describeError } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select'
import { toApiError } from '@/hooks/useResource'
import { useSources } from '@/hooks/useSources'
import type { BackgroundJobCreated, SourceInfo } from '@/types/api'

type FieldName = 'seed_url' | 'board' | 'max_depth' | 'max_pages' | 'allowed_domains'
/** "Another site": the original form; the crawler picks the extractor from each page's address. */
const OTHER = 'other'
const INITIAL = { source: OTHER, seed_url: '', board: '', max_depth: '2', max_pages: '50', allowed_domains: '' }
const BOARD_KEY = /^[A-Za-z0-9][A-Za-z0-9._-]*$/

/** "body.max_pages" or "body.allowed_domains.0" from the API, as one of the form's fields. */
function fieldOf(apiField: string, board: boolean): FieldName | null {
  const name = apiField.replace(/^body\./, '').split('.')[0]
  if (name === 'seed_url' && board) return 'board' // the seed URL was built from the board name
  return (['seed_url', 'max_depth', 'max_pages', 'allowed_domains'] as const).find((f) => f === name) ?? null
}

/** The seed URL of a job-board API, e.g. https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true. */
const boardSeed = (source: SourceInfo, key: string) => source.seed_template!.replace('{key}', encodeURIComponent(key.trim()))

/** Checks the browser can do before sending; the server checks everything again (LLD §5.9). */
function validate(values: typeof INITIAL, source: SourceInfo | undefined): Partial<Record<FieldName, string>> {
  const errors: Partial<Record<FieldName, string>> = {}
  if (source?.seed_template) {
    const key = values.board.trim()
    if (!key) errors.board = `Enter the ${source.seed_key_label?.toLowerCase() ?? 'board name'}.`
    else if (!BOARD_KEY.test(key)) errors.board = 'Use the name as it appears in the board’s address: letters, digits, dots, dashes or underscores.'
    return errors
  }
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

/**
 * "New crawl" (LLD §8.2): choose a supported source (GET /sources), then the seed URL, max_depth, max_pages
 * and allowed domains. A job board (Greenhouse, Lever) needs only its board name: its API lists every open job
 * in one request. The source only fills in the seed URL; the server still picks each page's extractor from
 * its address and applies robots.txt, the allow-list and the private-address guard (LLD §5.9, §5.16).
 */
export function NewCrawlDialog({ open, onOpenChange, onCreated }: NewCrawlDialogProps) {
  const sources = useSources()
  const [values, setValues] = useState(INITIAL)
  const [errors, setErrors] = useState<Partial<Record<FieldName, string>>>({})
  const [formError, setFormError] = useState<string>()
  const [pending, setPending] = useState(false)
  const source = sources.find((s) => s.name === values.source)
  const board = Boolean(source?.seed_template)

  const set = (name: FieldName) => (event: { target: { value: string } }) => {
    setValues((v) => ({ ...v, [name]: event.target.value }))
    setErrors((e) => ({ ...e, [name]: undefined }))
  }

  const choose = (name: string) => {
    const previous = sources.find((s) => s.name === values.source)
    const next = sources.find((s) => s.name === name)
    setValues((v) => {
      // A demo site starts at its known address; that address is cleared again when another source is chosen.
      const leavingDemoAddress = previous?.kind === 'demo' && v.seed_url === previous.example_seed
      const seed_url = next?.kind === 'demo' && next.example_seed ? next.example_seed : leavingDemoAddress ? '' : v.seed_url
      return { ...v, source: name, seed_url }
    })
    setErrors({})
    setFormError(undefined)
  }

  const reset = () => {
    setValues(INITIAL)
    setErrors({})
    setFormError(undefined)
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setFormError(undefined)
    const found = validate(values, source)
    setErrors(found)
    if (Object.keys(found).length) {
      document.getElementById(`crawl-${Object.keys(found)[0]}`)?.focus()
      return
    }
    setPending(true)
    try {
      const hosts = splitHosts(values.allowed_domains)
      const job = await createCrawlJob(
        board && source
          ? { seed_url: boardSeed(source, values.board), max_depth: 1, max_pages: 1, allowed_domains: null }
          : {
              seed_url: values.seed_url.trim(),
              max_depth: Number(values.max_depth),
              max_pages: Number(values.max_pages),
              allowed_domains: hosts.length ? hosts : null,
            },
      )
      reset()
      onCreated(job)
    } catch (e) {
      const error = toApiError(e)
      const byField: Partial<Record<FieldName, string>> = {}
      const other: string[] = []
      for (const fe of error.fieldErrors) {
        const name = fieldOf(fe.field, board)
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

  const real = sources.filter((s) => s.kind === 'real')
  const demo = sources.filter((s) => s.kind === 'demo')

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
            <DialogDescription>
              Collect job postings from a supported source. Crawl only sites you may crawl: FITSCAN follows robots.txt, stays on the allowed hosts, and never logs in or gets around access controls.
            </DialogDescription>
          </DialogHeader>
          {formError && <FormAlert>{formError}</FormAlert>}
          <div className="grid gap-2">
            <Label htmlFor="crawl-source">Source</Label>
            <Select value={values.source} onValueChange={choose}>
              <SelectTrigger id="crawl-source" className="w-full" aria-describedby="crawl-source-hint">
                <SelectValue>{source?.label ?? 'Another site'}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {real.length > 0 && (
                  <SelectGroup>
                    <SelectLabel>Real job sources</SelectLabel>
                    {real.map((s) => (
                      <SelectItem key={s.name} value={s.name}>
                        {s.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                )}
                {demo.length > 0 && (
                  <SelectGroup>
                    <SelectLabel>Demo sites (invented jobs)</SelectLabel>
                    {demo.map((s) => (
                      <SelectItem key={s.name} value={s.name}>
                        {s.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                )}
                <SelectGroup>
                  <SelectLabel>Other</SelectLabel>
                  <SelectItem value={OTHER}>Another site</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
            <p id="crawl-source-hint" className="text-[13px] leading-relaxed text-muted-foreground">
              {source
                ? source.kind === 'demo'
                  ? `${source.description} Its jobs are always labelled demo.`
                  : source.description
                : 'Any careers site you may crawl. The crawler picks the right extractor for each page.'}
            </p>
          </div>

          {board && source ? (
            <Field
              label={source.seed_key_label ?? 'Board name'}
              hint={values.board.trim() && BOARD_KEY.test(values.board.trim()) ? `One request to ${boardSeed(source, values.board)}` : 'The name in the board’s address, for example acme in …/acme.'}
              error={errors.board}
            >
              <Input id="crawl-board" autoComplete="off" spellCheck={false} placeholder="acme" value={values.board} onChange={set('board')} />
            </Field>
          ) : (
            <>
              <Field label="Seed URL" hint="The crawler starts here and follows links on the allowed hosts." error={errors.seed_url}>
                <Input
                  id="crawl-seed_url"
                  type="url"
                  inputMode="url"
                  autoComplete="url"
                  placeholder={source?.example_seed ?? 'https://example.com/careers'}
                  value={values.seed_url}
                  onChange={set('seed_url')}
                />
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
            </>
          )}
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
