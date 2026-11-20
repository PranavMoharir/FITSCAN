import { ToggleGroup } from 'radix-ui'
import type { ReactNode } from 'react'

import { THEMES, type Density, type Display, type PreviewTheme } from '@/components/landing/showcase/ShowcaseViews'
import { cn } from '@/lib/utils'

const itemClass =
  'h-8 rounded-full px-3.5 text-[13px] font-medium text-muted-foreground outline-none transition-colors duration-200 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring data-[state=on]:bg-primary data-[state=on]:text-primary-foreground'

function Group({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-1.5 rounded-full border border-border bg-card p-1 pl-4">
      <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-subtle-foreground">{label}</span>
      {children}
    </div>
  )
}

interface ShowcaseControlsProps {
  theme: PreviewTheme
  density: Density
  display: Display
  onTheme: (value: PreviewTheme) => void
  onDensity: (value: Density) => void
  onDisplay: (value: Display) => void
}

/** Single-choice toggle groups: arrow keys move between options, as in a radio group. */
export function ShowcaseControls({ theme, density, display, onTheme, onDensity, onDisplay }: ShowcaseControlsProps) {
  return (
    <div className="flex flex-wrap items-center justify-center gap-3">
      <Group label="Theme">
        <ToggleGroup.Root type="single" value={theme} onValueChange={(v) => v && onTheme(v as PreviewTheme)} aria-label="Preview theme" className="flex gap-1">
          {(Object.keys(THEMES) as PreviewTheme[]).map((key) => (
            <ToggleGroup.Item
              key={key}
              value={key}
              aria-label={THEMES[key].label}
              title={THEMES[key].label}
              className="grid size-8 place-items-center rounded-full outline-none transition-colors hover:bg-foreground/[0.06] focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span
                className={cn(
                  'size-4 rounded-full border border-foreground/25 ring-offset-2 ring-offset-[var(--card)] transition-shadow',
                  theme === key && 'ring-2 ring-primary',
                )}
                style={{ backgroundColor: THEMES[key].swatch }}
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
