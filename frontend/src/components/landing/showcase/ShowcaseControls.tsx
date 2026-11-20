import { ToggleGroup } from 'radix-ui'
import type { ReactNode } from 'react'

import { ACCENTS, type Accent, type Density, type Display } from '@/components/landing/showcase/ShowcaseViews'
import { cn } from '@/lib/utils'

const itemClass =
  'h-8 rounded-lg px-3 text-[13px] font-medium text-muted-foreground outline-none transition-colors duration-200 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring data-[state=on]:bg-white/[0.1] data-[state=on]:text-foreground'

function Group({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-1.5 rounded-2xl border border-white/[0.08] bg-card/80 p-1.5 pl-3 shadow-[0_20px_50px_-30px_rgb(0_0_0/0.9)] backdrop-blur">
      <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle-foreground">{label}</span>
      {children}
    </div>
  )
}

interface ShowcaseControlsProps {
  accent: Accent
  density: Density
  display: Display
  onAccent: (value: Accent) => void
  onDensity: (value: Density) => void
  onDisplay: (value: Display) => void
}

/** Single-choice toggle groups: arrow keys move between options, as in a radio group. */
export function ShowcaseControls({ accent, density, display, onAccent, onDensity, onDisplay }: ShowcaseControlsProps) {
  return (
    <div className="flex flex-wrap items-center justify-center gap-3">
      <Group label="Theme">
        <ToggleGroup.Root type="single" value={accent} onValueChange={(v) => v && onAccent(v as Accent)} aria-label="Preview accent colour" className="flex gap-1">
          {(Object.keys(ACCENTS) as Accent[]).map((key) => (
            <ToggleGroup.Item
              key={key}
              value={key}
              aria-label={ACCENTS[key].label}
              title={ACCENTS[key].label}
              className="grid size-8 place-items-center rounded-lg outline-none transition-colors hover:bg-white/[0.06] focus-visible:ring-2 focus-visible:ring-ring data-[state=on]:bg-white/[0.1]"
            >
              <span
                className={cn('size-4 rounded-full ring-offset-2 ring-offset-[#14141e] transition-shadow', accent === key && 'ring-2 ring-white/70')}
                style={{ backgroundColor: ACCENTS[key].solid }}
              />
            </ToggleGroup.Item>
          ))}
        </ToggleGroup.Root>
      </Group>
      <Group label="Layout">
        <ToggleGroup.Root type="single" value={density} onValueChange={(v) => v && onDensity(v as Density)} aria-label="Preview layout density" className="flex gap-0.5">
          <ToggleGroup.Item value="compact" className={itemClass}>Compact</ToggleGroup.Item>
          <ToggleGroup.Item value="comfortable" className={itemClass}>Comfortable</ToggleGroup.Item>
          <ToggleGroup.Item value="detailed" className={itemClass}>Detailed</ToggleGroup.Item>
        </ToggleGroup.Root>
      </Group>
      <Group label="Show">
        <ToggleGroup.Root type="single" value={display} onValueChange={(v) => v && onDisplay(v as Display)} aria-label="Preview detail" className="flex gap-0.5">
          <ToggleGroup.Item value="skills" className={itemClass}>Skill breakdown</ToggleGroup.Item>
          <ToggleGroup.Item value="explanation" className={itemClass}>Match explanation</ToggleGroup.Item>
        </ToggleGroup.Root>
      </Group>
    </div>
  )
}
