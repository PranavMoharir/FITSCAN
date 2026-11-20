import { Check, Minus } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type Kind = 'matched' | 'missing' | 'neutral'

const STYLES: Record<Kind, string> = {
  matched: 'border-emerald-400/20 bg-emerald-400/10 text-emerald-300',
  missing: 'border-rose-400/25 bg-rose-400/10 text-rose-300',
  neutral: 'border-white/10 bg-white/[0.04] text-muted-foreground',
}

/** A skill badge. Matched and missing chips carry an icon and hidden text, not colour alone. */
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
