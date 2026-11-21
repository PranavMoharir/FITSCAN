import { ToggleGroup } from 'radix-ui'

import { cn } from '@/lib/utils'

interface SegmentedProps<T extends string> {
  label: string
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
  className?: string
}

/**
 * One choice from a few, as a pill group (the landing page's product-tour controls). Arrow keys move
 * between options, as in a radio group.
 */
export function Segmented<T extends string>({ label, value, options, onChange, className }: SegmentedProps<T>) {
  return (
    <ToggleGroup.Root
      type="single"
      value={value}
      onValueChange={(v) => v && onChange(v as T)}
      aria-label={label}
      className={cn('inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-full border border-border bg-card p-1', className)}
    >
      {options.map((option) => (
        <ToggleGroup.Item
          key={option.value}
          value={option.value}
          className="h-7 shrink-0 rounded-full px-3 text-[13px] font-medium text-muted-foreground outline-none transition-colors duration-200 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring data-[state=on]:bg-primary data-[state=on]:text-primary-foreground"
        >
          {option.label}
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  )
}
