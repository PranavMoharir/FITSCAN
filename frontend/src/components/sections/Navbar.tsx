import { ArrowUpRight, ChevronDown, Menu, X } from 'lucide-react'
import { useEffect, useRef, useState, type MouseEvent, type ReactNode } from 'react'
import { Dialog, NavigationMenu } from 'radix-ui'
import { Link } from 'react-router'

import { BrandLogo } from '@/components/landing/BrandMark'
import { Cta } from '@/components/landing/Cta'
import {
  API_DOCS_URL,
  APP_PATH,
  navLinks,
  productMenu,
  resourcesMenu,
  type MenuFeature,
  type MenuGroup,
  type MenuLink,
} from '@/lib/landing'
import { cn } from '@/lib/utils'

/** Renders a menu destination as a router link, an external link or a section anchor. */
function Destination({ link, className, children, onNavigate }: { link: Pick<MenuLink, 'href' | 'internal' | 'external'>; className?: string; children: ReactNode; onNavigate?: (event: MouseEvent<HTMLAnchorElement>) => void }) {
  if (link.internal) {
    return (
      <Link to={link.href} className={className} onClick={onNavigate}>
        {children}
      </Link>
    )
  }
  return (
    <a
      href={link.href}
      className={className}
      onClick={onNavigate}
      {...(link.external ? { target: '_blank', rel: 'noreferrer' } : {})}
    >
      {children}
    </a>
  )
}

const triggerClass =
  'group inline-flex h-9 items-center gap-1 rounded-full px-3.5 text-sm font-medium text-muted-foreground outline-none transition-colors duration-200 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring data-[state=open]:bg-white/[0.06] data-[state=open]:text-foreground'

function MegaMenu({ groups, feature }: { groups: MenuGroup[]; feature: MenuFeature }) {
  return (
    <div className="grid w-[780px] grid-cols-[1fr_1fr_250px] gap-2 p-3">
      {groups.map((group) => (
        <div key={group.label}>
          <p className="px-3 pb-2 pt-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-subtle-foreground">{group.label}</p>
          <ul className="space-y-0.5">
            {group.links.map((link) => (
              <li key={link.title}>
                <NavigationMenu.Link asChild>
                  <Destination
                    link={link}
                    className="group/item flex gap-3 rounded-xl p-3 outline-none transition-colors duration-200 hover:bg-white/[0.05] focus-visible:bg-white/[0.05] focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <span className="grid size-9 shrink-0 place-items-center rounded-lg border border-white/[0.08] bg-white/[0.03] text-brand-soft transition-colors duration-200 group-hover/item:border-brand/30 group-hover/item:bg-brand/10">
                      <link.icon className="size-4" aria-hidden="true" />
                    </span>
                    <span className="min-w-0">
                      <span className="flex items-center gap-1 text-sm font-medium text-foreground">
                        {link.title}
                        {link.external && <ArrowUpRight className="size-3.5 text-subtle-foreground" aria-hidden="true" />}
                        {link.external && <span className="sr-only">(opens in a new tab)</span>}
                      </span>
                      <span className="mt-0.5 block text-[13px] leading-snug text-muted-foreground">{link.description}</span>
                    </span>
                  </Destination>
                </NavigationMenu.Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <NavigationMenu.Link asChild>
        <Destination
          link={{ href: feature.href, internal: feature.href.startsWith('/') }}
          className="group/feature flex flex-col rounded-xl border border-brand/20 bg-gradient-to-b from-brand/[0.16] to-transparent p-4 outline-none transition-colors duration-200 hover:border-brand/40 focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-brand-soft">{feature.eyebrow}</span>
          <span className="mt-3 text-sm font-semibold text-foreground">{feature.title}</span>
          <span className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">{feature.text}</span>
          <span aria-hidden="true" className="mt-4 flex h-1.5 overflow-hidden rounded-full">
            <i className="w-[70%] bg-brand" />
            <i className="w-[15%] bg-brand-soft" />
            <i className="w-[10%] bg-brand-blue" />
            <i className="w-[5%] bg-white/50" />
          </span>
          <span className="mt-auto flex items-center gap-1 pt-4 text-[13px] font-medium text-brand-soft">
            {feature.linkLabel}
            <ArrowUpRight className="size-3.5 transition-transform duration-200 group-hover/feature:-translate-y-0.5 group-hover/feature:translate-x-0.5" aria-hidden="true" />
          </span>
        </Destination>
      </NavigationMenu.Link>
    </div>
  )
}

function DesktopNav() {
  return (
    <NavigationMenu.Root className="relative hidden lg:block" aria-label="Main">
      <NavigationMenu.List className="flex items-center gap-0.5">
        <NavigationMenu.Item>
          <NavigationMenu.Trigger className={triggerClass}>
            Product
            <ChevronDown className="size-3.5 transition-transform duration-200 group-data-[state=open]:rotate-180" aria-hidden="true" />
          </NavigationMenu.Trigger>
          <NavigationMenu.Content className="absolute left-0 top-0 data-[motion^=from-]:animate-in data-[motion^=from-]:fade-in data-[motion^=to-]:animate-out data-[motion^=to-]:fade-out">
            <MegaMenu {...productMenu} />
          </NavigationMenu.Content>
        </NavigationMenu.Item>
        {navLinks.slice(0, 2).map((item) => (
          <NavigationMenu.Item key={item.label}>
            <NavigationMenu.Link href={item.href} className={triggerClass}>
              {item.label}
            </NavigationMenu.Link>
          </NavigationMenu.Item>
        ))}
        <NavigationMenu.Item>
          <NavigationMenu.Trigger className={triggerClass}>
            Resources
            <ChevronDown className="size-3.5 transition-transform duration-200 group-data-[state=open]:rotate-180" aria-hidden="true" />
          </NavigationMenu.Trigger>
          <NavigationMenu.Content className="absolute left-0 top-0 data-[motion^=from-]:animate-in data-[motion^=from-]:fade-in data-[motion^=to-]:animate-out data-[motion^=to-]:fade-out">
            <MegaMenu {...resourcesMenu} />
          </NavigationMenu.Content>
        </NavigationMenu.Item>
        {navLinks.slice(2).map((item) => (
          <NavigationMenu.Item key={item.label}>
            <NavigationMenu.Link href={item.href} className={triggerClass}>
              {item.label}
            </NavigationMenu.Link>
          </NavigationMenu.Item>
        ))}
      </NavigationMenu.List>
      <div className="absolute left-1/2 top-full flex -translate-x-1/2 justify-center pt-3">
        <NavigationMenu.Viewport className="relative h-[var(--radix-navigation-menu-viewport-height)] w-[var(--radix-navigation-menu-viewport-width)] origin-top overflow-hidden rounded-2xl border border-white/[0.08] bg-[#12121b] shadow-[0_30px_80px_-20px_rgb(0_0_0/0.8)] transition-[width,height] duration-300 ease-out data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95" />
      </div>
    </NavigationMenu.Root>
  )
}

function MobileNav() {
  const [open, setOpen] = useState(false)
  const pendingHash = useRef<string | null>(null)

  // Section links: close the dialog first, then scroll once its scroll lock is released.
  const goToSection = (href: string) => (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault()
    pendingHash.current = href
    setOpen(false)
  }
  const close = () => setOpen(false)

  const linkClass = 'flex items-center gap-3 rounded-xl px-3 py-3 text-[15px] text-foreground outline-none hover:bg-white/[0.05] focus-visible:ring-2 focus-visible:ring-ring'
  const groups = [...productMenu.groups, ...resourcesMenu.groups]

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger
        className="grid size-10 place-items-center rounded-full border border-white/10 text-foreground outline-none hover:bg-white/[0.06] focus-visible:ring-2 focus-visible:ring-ring lg:hidden"
        aria-label="Open menu"
      >
        <Menu className="size-5" aria-hidden="true" />
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="landing fixed inset-0 z-50 bg-black/60 backdrop-blur-sm data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <Dialog.Content
          className="landing fixed inset-x-0 top-0 z-50 max-h-dvh overflow-y-auto border-b border-white/[0.08] bg-[#0d0d14] px-4 pb-8 pt-4 shadow-2xl data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:slide-out-to-top-4 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:slide-in-from-top-4 sm:px-6"
          onCloseAutoFocus={(event) => {
            const target = pendingHash.current
            pendingHash.current = null
            if (target) {
              event.preventDefault()
              const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
              document.getElementById(target.slice(1))?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
              window.history.replaceState(null, '', target)
            }
          }}
        >
          <div className="flex h-12 items-center justify-between">
            <BrandLogo />
            <Dialog.Close className="grid size-10 place-items-center rounded-full border border-white/10 outline-none hover:bg-white/[0.06] focus-visible:ring-2 focus-visible:ring-ring" aria-label="Close menu">
              <X className="size-5" aria-hidden="true" />
            </Dialog.Close>
          </div>
          <Dialog.Title className="sr-only">Site navigation</Dialog.Title>
          <Dialog.Description className="sr-only">Links to the sections of this page, the API documentation and the FITSCAN application.</Dialog.Description>

          <nav aria-label="Mobile" className="mt-4 space-y-6">
            {groups.map((group) => (
              <div key={group.label}>
                <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-subtle-foreground">{group.label}</p>
                <ul>
                  {group.links.map((link) => (
                    <li key={link.title}>
                      <Destination
                        link={link}
                        className={linkClass}
                        onNavigate={link.internal || link.external ? close : goToSection(link.href)}
                      >
                        <link.icon className="size-4 text-brand-soft" aria-hidden="true" />
                        {link.title}
                        {link.external && <ArrowUpRight className="ml-auto size-4 text-subtle-foreground" aria-hidden="true" />}
                        {link.external && <span className="sr-only">(opens in a new tab)</span>}
                      </Destination>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            <ul className="border-t border-white/[0.08] pt-4">
              {navLinks.map((item) => (
                <li key={item.label}>
                  <a href={item.href} className={linkClass} onClick={goToSection(item.href)}>
                    {item.label}
                  </a>
                </li>
              ))}
            </ul>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Cta to={APP_PATH} arrow className="w-full sm:w-auto">
                Get started
              </Cta>
              <Cta href={API_DOCS_URL} variant="secondary" className="w-full sm:w-auto">
                API docs
              </Cta>
            </div>
          </nav>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export function Navbar() {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header
      className={cn(
        'sticky top-0 z-40 border-b backdrop-blur-xl transition-colors duration-300',
        scrolled ? 'border-white/[0.07] bg-[#0a0a0f]/75' : 'border-transparent bg-[#0a0a0f]/30',
      )}
    >
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <a href="#top" className="rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="FITSCAN, back to top">
          <BrandLogo />
        </a>
        <DesktopNav />
        <div className="flex items-center gap-2">
          <a
            href={API_DOCS_URL}
            target="_blank"
            rel="noreferrer"
            className="hidden items-center gap-1 rounded-full px-3 py-2 text-sm font-medium text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring sm:inline-flex"
          >
            API docs
            <ArrowUpRight className="size-3.5" aria-hidden="true" />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
          <Cta to={APP_PATH} size="sm" arrow className="hidden sm:inline-flex">
            Get started
          </Cta>
          <MobileNav />
        </div>
      </div>
    </header>
  )
}
