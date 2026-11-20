import { Check, Minus } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type Kind = 'matched' | 'missing' | 'neutral'

// Palette only: matched chips are tinted with the accent and carry a check; missing chips are
// dashed and carry a minus. Hidden text names the state, so colour is never the only signal.
const STYLES: Record<Kind, string> = {
  matched: 'border-accent-solid/25 bg-accent-solid/10 text-accent-ink',
  missing: 'border-dashed border-foreground/35 bg-transparent text-muted-foreground',
  neutral: 'border-border bg-foreground/[0.04] text-muted-foreground',
}

export function SkillChip({ name, kind = 'neutral', className }: { name: string; kind?: Kind; className?: string }) {
  return (
    <Badge variant="outline" className={cn('h-6 gap-1 rounded-full px-2.5 text-xs font-medium', STYLES[kind], className)}>
      {kind === 'matched' && <Check aria-hidden="true" />}
      {kind === 'missing' && <Minus aria-hidden="true" />}
      {name}
      {kind !== 'neutral' && <span className="sr-only">({kind})</span>}
    </Badge>
  )
}
