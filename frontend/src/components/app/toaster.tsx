import { CircleAlert, CircleCheck } from 'lucide-react'
import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from 'react'

import { Toast, ToastAction, ToastClose, ToastDescription, ToastProvider, ToastTitle, ToastViewport } from '@/components/ui/toast'

export interface ToastOptions {
  title: string
  description?: string
  variant?: 'default' | 'error'
  action?: { label: string; onClick: () => void }
}

interface ToastItem extends ToastOptions {
  id: number
}

const ToastContext = createContext<(options: ToastOptions) => void>(() => {})

/** Toasts for results and errors that are not tied to a form field (LLD §8.4). */
export function ToasterProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])

  const toast = useCallback((options: ToastOptions) => {
    setItems((current) => [...current.slice(-3), { ...options, id: Date.now() + Math.random() }])
  }, [])
  const remove = (id: number) => setItems((current) => current.filter((item) => item.id !== id))

  const value = useMemo(() => toast, [toast])

  return (
    <ToastContext.Provider value={value}>
      <ToastProvider swipeDirection="right" label="Notifications">
        {children}
        {items.map((item) => (
          <Toast
            key={item.id}
            variant={item.variant}
            duration={item.variant === 'error' ? 9000 : 5000}
            onOpenChange={(open) => {
              if (!open) window.setTimeout(() => remove(item.id), 300)
            }}
          >
            {item.variant === 'error' ? (
              <CircleAlert className="mt-0.5 size-[18px] shrink-0 text-destructive" aria-hidden="true" />
            ) : (
              <CircleCheck className="mt-0.5 size-[18px] shrink-0 text-accent-ink" aria-hidden="true" />
            )}
            <div className="grid min-w-0 gap-1">
              <ToastTitle>{item.title}</ToastTitle>
              {item.description && <ToastDescription>{item.description}</ToastDescription>}
              {item.action && (
                <ToastAction
                  altText={item.action.label}
                  onClick={item.action.onClick}
                  className="mt-1 w-fit rounded-full text-[13px] font-semibold text-accent-ink underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  {item.action.label}
                </ToastAction>
              )}
            </div>
            <ToastClose />
          </Toast>
        ))}
        <ToastViewport />
      </ToastProvider>
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}
