import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"
import { XIcon } from "lucide-react"
import { Toast as ToastPrimitive } from "radix-ui"

const ToastProvider = ToastPrimitive.Provider

function ToastViewport({ className, ...props }: React.ComponentProps<typeof ToastPrimitive.Viewport>) {
  return (
    <ToastPrimitive.Viewport
      data-slot="toast-viewport"
      className={cn(
        "fixed bottom-0 right-0 z-[100] flex max-h-screen w-full flex-col-reverse gap-2 p-4 outline-none sm:max-w-[26rem]",
        className
      )}
      {...props}
    />
  )
}

const toastVariants = cva(
  "group pointer-events-auto relative flex w-full items-start gap-3 overflow-hidden rounded-xl border bg-popover p-4 pr-11 text-popover-foreground shadow-[0_20px_50px_-24px_rgb(11_11_11/0.45)] data-[swipe=cancel]:translate-x-0 data-[swipe=end]:translate-x-(--radix-toast-swipe-end-x) data-[swipe=move]:translate-x-(--radix-toast-swipe-move-x) data-[swipe=move]:transition-none data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:slide-in-from-bottom-3 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[swipe=end]:animate-out",
  {
    variants: {
      variant: {
        default: "border-border",
        error: "border-destructive/30",
      },
    },
    defaultVariants: { variant: "default" },
  }
)

function Toast({ className, variant, ...props }: React.ComponentProps<typeof ToastPrimitive.Root> & VariantProps<typeof toastVariants>) {
  return <ToastPrimitive.Root data-slot="toast" className={cn(toastVariants({ variant }), className)} {...props} />
}

function ToastTitle({ className, ...props }: React.ComponentProps<typeof ToastPrimitive.Title>) {
  return <ToastPrimitive.Title data-slot="toast-title" className={cn("text-sm font-semibold", className)} {...props} />
}

function ToastDescription({ className, ...props }: React.ComponentProps<typeof ToastPrimitive.Description>) {
  return (
    <ToastPrimitive.Description data-slot="toast-description" className={cn("text-[13px] leading-relaxed text-muted-foreground", className)} {...props} />
  )
}

function ToastClose({ className, ...props }: React.ComponentProps<typeof ToastPrimitive.Close>) {
  return (
    <ToastPrimitive.Close
      data-slot="toast-close"
      className={cn(
        "absolute right-2.5 top-2.5 grid size-7 place-items-center rounded-full text-muted-foreground outline-none transition-colors hover:bg-foreground/[0.06] hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50",
        className
      )}
      aria-label="Dismiss notification"
      {...props}
    >
      <XIcon className="size-3.5" aria-hidden="true" />
    </ToastPrimitive.Close>
  )
}

const ToastAction = ToastPrimitive.Action

export { Toast, ToastAction, ToastClose, ToastDescription, ToastProvider, ToastTitle, ToastViewport }
