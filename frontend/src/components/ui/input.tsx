import * as React from "react"
import { cn } from "cn"

/** Text input. 16px text on small screens, so phones do not zoom in when it gets focus. */
const inputClass =
  "w-full min-w-0 rounded-lg border border-input bg-card text-base text-foreground outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-subtle-foreground hover:border-foreground/25 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/15 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/15 md:text-sm"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return <input type={type} data-slot="input" className={cn(inputClass, "h-9 px-3", className)} {...props} />
}

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return <textarea data-slot="textarea" className={cn(inputClass, "min-h-20 resize-y px-3 py-2 leading-relaxed", className)} {...props} />
}

export { Input, inputClass, Textarea }
