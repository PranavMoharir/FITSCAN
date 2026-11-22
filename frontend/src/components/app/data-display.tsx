// Small shared pieces for detail pages and tables: facts, skill lists and export links.

import { Download } from 'lucide-react'
import type { ReactNode } from 'react'

import { SkillChip } from '@/components/landing/SkillChip'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** A demo listing is an invented job from a demo site: always marked, never shown as a real opening. */
export function DemoBadge({ className }: { className?: string }) {
  return (
    <Badge
      variant="outline"
      className={cn('h-5 shrink-0 rounded-full border-dashed border-foreground/30 px-2 text-[11px] font-medium text-muted-foreground', className)}
      title="An invented job from a demo site, not a real opening"
    >
      Demo
    </Badge>
  )
}

/** A definition list of label and value rows. */
export function Facts({ items, className }: { items: [string, ReactNode][]; className?: string }) {
  return (
    <dl className={cn('divide-y divide-border', className)}>
      {items.map(([label, value]) => (
        <div key={label} className="grid grid-cols-[8rem_minmax(0,1fr)] gap-3 py-2.5 text-sm">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="min-w-0 break-words text-foreground">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Skill chips; with `limit`, the rest are summarised as "+3 more" (the full list is in the label). */
export function SkillList({ skills, limit, empty = 'None listed', className }: { skills: string[]; limit?: number; empty?: string; className?: string }) {
  if (!skills.length) return <span className="text-[13px] text-subtle-foreground">{empty}</span>
  const shown = limit ? skills.slice(0, limit) : skills
  const rest = skills.length - shown.length
  return (
    <ul className={cn('flex flex-wrap gap-1.5', className)} aria-label={limit && rest > 0 ? `Skills: ${skills.join(', ')}` : undefined}>
      {shown.map((skill) => (
        <li key={skill}>
          <SkillChip name={skill} />
        </li>
      ))}
      {rest > 0 && (
        <li className="self-center text-xs text-subtle-foreground" aria-hidden="true">
          +{rest} more
        </li>
      )}
    </ul>
  )
}

interface ExportButtonsProps {
  /** Short visible label, e.g. "Export" or "Match table". */
  label: string
  /** What the group exports, for screen readers, e.g. "Export these jobs". */
  name: string
  csv: string
  json: string
  className?: string
}

/** CSV and JSON download links for an export with the current filters (LLD §8.4: plain links). */
export function ExportButtons({ label, name, csv, json, className }: ExportButtonsProps) {
  return (
    <div className={cn('flex items-center gap-1.5', className)} role="group" aria-label={name}>
      <span className="mr-0.5 text-[13px] text-muted-foreground" aria-hidden="true">
        {label}
      </span>
      {(['csv', 'json'] as const).map((format) => (
        <Button key={format} asChild variant="outline" size="sm">
          <a href={format === 'csv' ? csv : json} download>
            <Download aria-hidden="true" />
            {format.toUpperCase()}
            <span className="sr-only"> ({name}, with the current filters)</span>
          </a>
        </Button>
      ))}
    </div>
  )
}
