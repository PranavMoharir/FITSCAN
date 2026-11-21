import { ArrowUpRight } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { formatBytes, formatNumber, plural, shortId } from '@/lib/format'
import type { BackgroundJobDetail } from '@/types/api'

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[8.5rem_minmax(0,1fr)] gap-3 py-2.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-foreground">{children}</dd>
    </div>
  )
}

const asString = (v: unknown) => (typeof v === 'string' ? v : null)
const asNumber = (v: unknown) => (typeof v === 'number' ? v : null)

/** A run's parameters, per job type. Resume files show only their upload ID and size, never a name. */
export function JobParams({ job }: { job: BackgroundJobDetail }) {
  const p = job.params ?? {}
  if (job.type === 'match') {
    return <p className="text-sm leading-relaxed text-muted-foreground">A match run has no parameters: it scores every candidate against every job.</p>
  }
  if (job.type === 'crawl') {
    const seed = asString(p.seed_url)
    const domains = Array.isArray(p.allowed_domains) ? (p.allowed_domains as unknown[]).map(String) : []
    return (
      <dl className="divide-y divide-border">
        <Row label="Seed URL">
          {seed ? (
            <a href={seed} target="_blank" rel="noreferrer" className="inline-flex max-w-full items-center gap-1 break-all text-accent-ink underline-offset-4 hover:underline">
              {seed}
              <ArrowUpRight className="size-3.5 shrink-0" aria-hidden="true" />
              <span className="sr-only">(opens in a new tab)</span>
            </a>
          ) : (
            '—'
          )}
        </Row>
        <Row label="Max depth">{asNumber(p.max_depth) ?? '—'}</Row>
        <Row label="Max pages">{asNumber(p.max_pages) !== null ? formatNumber(asNumber(p.max_pages)!) : '—'}</Row>
        <Row label="Allowed domains">
          {domains.length ? (
            <span className="flex flex-wrap gap-1.5">
              {domains.map((d) => (
                <Badge key={d} variant="outline" className="h-6 rounded-full border-border px-2.5 font-mono text-[12px] text-foreground">
                  {d}
                </Badge>
              ))}
            </span>
          ) : (
            "The seed URL's host"
          )}
        </Row>
        {asString(p.extractor) && <Row label="Extractor">{asString(p.extractor)}</Row>}
      </dl>
    )
  }
  const files = Array.isArray(p.files) ? (p.files as { upload_id?: string; size_bytes?: number }[]) : []
  return (
    <div>
      <p className="text-sm text-muted-foreground">{plural(files.length, 'file')} in this upload. Files are listed by upload ID; original names are not shown.</p>
      {files.length > 0 && (
        <ul className="mt-3 max-h-64 divide-y divide-border overflow-y-auto rounded-lg border border-border">
          {files.map((f, i) => (
            <li key={f.upload_id ?? i} className="flex items-center justify-between gap-3 px-3.5 py-2 text-[13px]">
              <span className="font-mono text-foreground" title={f.upload_id}>
                {f.upload_id ? shortId(f.upload_id) : `File ${i + 1}`}
              </span>
              <span className="tabular-nums text-subtle-foreground">{typeof f.size_bytes === 'number' ? formatBytes(f.size_bytes) : '—'}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
