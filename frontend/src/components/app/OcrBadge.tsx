import { ScanText } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

/** Shown when a resume was read with OCR (a scanned PDF): its fields may be less exact. */
export function OcrBadge() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="outline" tabIndex={0} className="h-6 gap-1 border-foreground/20 px-2 text-xs text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <ScanText className="size-3.5!" aria-hidden="true" />
          OCR
          <span className="sr-only">: parsed from a scanned PDF with OCR</span>
        </Badge>
      </TooltipTrigger>
      <TooltipContent>Parsed from a scanned PDF with OCR</TooltipContent>
    </Tooltip>
  )
}
