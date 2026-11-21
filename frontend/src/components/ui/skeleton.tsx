import * as React from "react"
import { cn } from "cn"

/** A placeholder block shown while content loads. Decorative: hidden from assistive technology. */
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      aria-hidden="true"
      className={cn("animate-pulse rounded-md bg-foreground/[0.07]", className)}
      {...props}
    />
  )
}

export { Skeleton }
