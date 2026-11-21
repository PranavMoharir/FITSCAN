import * as React from "react"
import { cn } from "cn"
import { Progress as ProgressPrimitive } from "radix-ui"

/**
 * A thin progress meter. The empty track is a light step of the fill's own colour, so the bar reads
 * as one meter. `value` null means the total is not known yet (indeterminate).
 */
function Progress({
  className,
  indicatorClassName,
  value,
  ...props
}: React.ComponentProps<typeof ProgressPrimitive.Root> & { indicatorClassName?: string }) {
  return (
    <ProgressPrimitive.Root
      data-slot="progress"
      value={value}
      className={cn("relative h-1.5 w-full overflow-hidden rounded-full bg-primary/[0.13]", className)}
      {...props}
    >
      <ProgressPrimitive.Indicator
        data-slot="progress-indicator"
        className={cn("h-full w-full rounded-full bg-primary transition-transform duration-500 ease-out", indicatorClassName)}
        style={{ transform: `translateX(-${100 - Math.max(0, Math.min(100, value ?? 0))}%)` }}
      />
    </ProgressPrimitive.Root>
  )
}

export { Progress }
