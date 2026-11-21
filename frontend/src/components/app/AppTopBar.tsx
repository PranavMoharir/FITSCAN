import { ChevronRight, Menu } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router'

import { SidebarContent } from '@/components/app/AppSidebar'
import { SystemStatusPill } from '@/components/app/system-status'
import { BrandLogo } from '@/components/landing/BrandMark'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { navItemFor } from '@/lib/app'

const DETAIL_LABEL: Record<string, string> = {
  '/jobs': 'Job',
  '/candidates': 'Candidate',
  '/background-jobs': 'Run',
}

/** "Jobs › Job" on detail pages, the section name elsewhere. */
function Breadcrumb() {
  const { pathname } = useLocation()
  const item = navItemFor(pathname)
  if (!item) return null
  const isDetail = pathname !== item.to
  return (
    <nav aria-label="Breadcrumb" className="hidden min-w-0 md:block">
      <ol className="flex items-center gap-1.5 text-[13px]">
        <li className="min-w-0">
          {isDetail ? (
            <Link to={item.to} className="rounded font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50">
              {item.label}
            </Link>
          ) : (
            <span aria-current="page" className="font-medium text-foreground">
              {item.label}
            </span>
          )}
        </li>
        {isDetail && (
          <>
            <ChevronRight className="size-3.5 shrink-0 text-subtle-foreground" aria-hidden="true" />
            <li aria-current="page" className="truncate font-medium text-foreground">
              {DETAIL_LABEL[item.to] ?? 'Detail'}
            </li>
          </>
        )}
      </ol>
    </nav>
  )
}

/** Phones: a menu button that opens the black sidebar as a drawer; it closes after navigating. */
function MobileNav() {
  const [open, setOpen] = useState(false)
  const navigated = useRef(false)
  const { pathname } = useLocation()
  useEffect(() => setOpen(false), [pathname])

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="-ml-2 text-foreground md:hidden" aria-label="Open navigation">
          <Menu aria-hidden="true" />
        </Button>
      </SheetTrigger>
      <SheetContent
        className="surface-ink bg-background"
        closeLabel="Close navigation"
        onCloseAutoFocus={(event) => {
          // After choosing a page, focus goes to the new page's heading, not back to the menu button.
          if (navigated.current) event.preventDefault()
          navigated.current = false
        }}
      >
        <SheetTitle className="sr-only">Navigation</SheetTitle>
        <SheetDescription className="sr-only">Pages of the FITSCAN application</SheetDescription>
        <SidebarContent onNavigate={() => (navigated.current = true)} />
      </SheetContent>
    </Sheet>
  )
}

export function AppTopBar() {
  return (
    <header className="sticky top-0 z-20 border-b border-border bg-background/85 backdrop-blur-md supports-[backdrop-filter]:bg-background/75">
      <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-3 px-4 sm:px-6 lg:px-10">
        <MobileNav />
        <Link to="/app" aria-label="FITSCAN dashboard" className="rounded-lg outline-none focus-visible:ring-3 focus-visible:ring-ring/50 md:hidden">
          <BrandLogo className="text-[13px] [&_svg]:size-6" />
        </Link>
        <Breadcrumb />
        <div className="ml-auto flex items-center gap-2">
          <SystemStatusPill />
        </div>
      </div>
    </header>
  )
}
