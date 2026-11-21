import * as React from "react"
import { cn } from "cn"
import { XIcon } from "lucide-react"
import { Dialog as SheetPrimitive } from "radix-ui"

/** A panel that slides in from the left edge (the application's mobile navigation). */
function Sheet(props: React.ComponentProps<typeof SheetPrimitive.Root>) {
  return <SheetPrimitive.Root data-slot="sheet" {...props} />
}

function SheetTrigger(props: React.ComponentProps<typeof SheetPrimitive.Trigger>) {
  return <SheetPrimitive.Trigger data-slot="sheet-trigger" {...props} />
}

function SheetContent({
  className,
  children,
  closeLabel = "Close",
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Content> & { closeLabel?: string }) {
  return (
    <SheetPrimitive.Portal>
      <SheetPrimitive.Overlay
        data-slot="sheet-overlay"
        className="fixed inset-0 z-50 bg-ink/50 backdrop-blur-[2px] duration-300 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0"
      />
      <SheetPrimitive.Content
        data-slot="sheet-content"
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex h-full w-[min(18rem,86vw)] flex-col shadow-[24px_0_60px_-30px_rgb(11_11_11/0.6)] outline-none",
          "duration-300 ease-out data-[state=open]:animate-in data-[state=open]:slide-in-from-left data-[state=closed]:animate-out data-[state=closed]:slide-out-to-left",
          className
        )}
        {...props}
      >
        {children}
        <SheetPrimitive.Close className="absolute right-3 top-3.5 grid size-9 place-items-center rounded-full text-muted-foreground outline-none transition-colors duration-150 hover:bg-foreground/[0.08] hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50">
          <XIcon className="size-4" aria-hidden="true" />
          <span className="sr-only">{closeLabel}</span>
        </SheetPrimitive.Close>
      </SheetPrimitive.Content>
    </SheetPrimitive.Portal>
  )
}

function SheetTitle(props: React.ComponentProps<typeof SheetPrimitive.Title>) {
  return <SheetPrimitive.Title data-slot="sheet-title" {...props} />
}

function SheetDescription(props: React.ComponentProps<typeof SheetPrimitive.Description>) {
  return <SheetPrimitive.Description data-slot="sheet-description" {...props} />
}

export { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger }
