// The application frame for /app and the pages beside it (LLD §8.2): the black sidebar, the top
// bar and the page area. The landing page ("/") does not use it.

import { MotionConfig, motion, useReducedMotion } from 'framer-motion'
import { Suspense, useEffect, useRef, useState } from 'react'
import { Outlet, useLocation } from 'react-router'

import { AppSidebar } from '@/components/app/AppSidebar'
import { AppTopBar } from '@/components/app/AppTopBar'
import { PageSkeleton } from '@/components/app/states'
import { SystemStatusProvider } from '@/components/app/system-status'
import { ToasterProvider } from '@/components/app/toaster'
import { EASE_OUT } from '@/components/landing/Reveal'
import { TooltipProvider } from '@/components/ui/tooltip'

/**
 * After a page change, move keyboard focus to the new page's heading and announce it, the way a
 * full page load would. The heading may appear a moment later (code-split pages), hence the retries.
 */
function useRouteFocus(pathname: string) {
  const first = useRef(true)
  const [announcement, setAnnouncement] = useState('')
  useEffect(() => {
    if (first.current) {
      first.current = false
      return
    }
    let tries = 0
    const timer = window.setInterval(() => {
      const heading = document.querySelector<HTMLElement>('#main h1')
      if (heading || ++tries > 20) {
        window.clearInterval(timer)
        heading?.focus({ preventScroll: true })
        setAnnouncement(document.title)
      }
    }, 50)
    return () => window.clearInterval(timer)
  }, [pathname])
  return announcement
}

export default function AppShell() {
  const { pathname } = useLocation()
  const reduceMotion = useReducedMotion()
  const announcement = useRouteFocus(pathname)

  return (
    <MotionConfig reducedMotion="user">
      <TooltipProvider>
        <ToasterProvider>
          <SystemStatusProvider>
            <div className="app-shell min-h-dvh bg-background text-foreground">
              <a
                href="#main"
                className="sr-only rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-50"
              >
                Skip to content
              </a>
              <AppSidebar />
              <div className="flex min-h-dvh min-w-0 flex-col md:pl-[76px] lg:pl-64">
                <AppTopBar />
                <main id="main" tabIndex={-1} className="flex-1 outline-none">
                  <Suspense fallback={<div className="mx-auto w-full max-w-[1400px] px-4 pb-16 pt-6 sm:px-6 lg:px-10 lg:pt-9"><PageSkeleton /></div>}>
                    <motion.div
                      key={pathname}
                      initial={reduceMotion ? false : { opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.28, ease: EASE_OUT }}
                      className="mx-auto w-full max-w-[1400px] px-4 pb-16 pt-6 sm:px-6 lg:px-10 lg:pt-9"
                    >
                      <Outlet />
                    </motion.div>
                  </Suspense>
                </main>
              </div>
              <p className="sr-only" aria-live="polite" aria-atomic="true">
                {announcement}
              </p>
            </div>
          </SystemStatusProvider>
        </ToasterProvider>
      </TooltipProvider>
    </MotionConfig>
  )
}
