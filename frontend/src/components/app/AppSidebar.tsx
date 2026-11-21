import { ArrowLeft, ArrowUpRight, BookOpen, type LucideIcon } from 'lucide-react'
import { Link, NavLink } from 'react-router'

import { API_DOCS_URL } from '@/api/client'
import { BrandLogo, BrandMark } from '@/components/landing/BrandMark'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { NAV_ITEMS, type NavItem } from '@/lib/app'
import { cn } from '@/lib/utils'

const itemBase =
  'group relative flex h-10 items-center gap-3 rounded-lg text-sm font-medium outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-ring'

/** Collapsed items show only the icon; the label moves into a tooltip and stays readable by screen readers. */
function WithTooltip({ label, collapsed, children }: { label: string; collapsed: boolean; children: React.ReactElement }) {
  if (!collapsed) return children
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  )
}

function SidebarLink({ item, collapsed, onNavigate }: { item: NavItem; collapsed: boolean; onNavigate?: () => void }) {
  const Icon = item.icon
  return (
    <WithTooltip label={item.label} collapsed={collapsed}>
      <NavLink
        to={item.to}
        end={item.to === '/app'}
        onClick={onNavigate}
        className={({ isActive }) =>
          cn(
            itemBase,
            collapsed ? 'justify-center px-0' : 'px-3',
            isActive ? 'bg-accent-solid/[0.13] text-foreground' : 'text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground',
          )
        }
      >
        {({ isActive }) => (
          <>
            <span
              aria-hidden="true"
              className={cn(
                'absolute left-0 top-2 bottom-2 w-[3px] rounded-full bg-accent-solid transition-opacity duration-200',
                isActive ? 'opacity-100' : 'opacity-0',
                collapsed && '-left-3',
              )}
            />
            <Icon className={cn('size-[18px] shrink-0 transition-colors duration-150', isActive ? 'text-accent-ink' : 'text-subtle-foreground group-hover:text-foreground')} aria-hidden="true" />
            <span className={cn(collapsed && 'sr-only')}>{item.label}</span>
          </>
        )}
      </NavLink>
    </WithTooltip>
  )
}

function FooterLink({ icon: Icon, label, collapsed, href, to, onNavigate }: { icon: LucideIcon; label: string; collapsed: boolean; href?: string; to?: string; onNavigate?: () => void }) {
  const className = cn(itemBase, 'h-9 text-[13px] text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground', collapsed ? 'justify-center px-0' : 'px-3')
  const content = (
    <>
      <Icon className="size-4 shrink-0 text-subtle-foreground group-hover:text-foreground" aria-hidden="true" />
      <span className={cn(collapsed && 'sr-only')}>{label}</span>
      {href && !collapsed && <ArrowUpRight className="ml-auto size-3.5 text-subtle-foreground" aria-hidden="true" />}
      {href && <span className="sr-only">(opens in a new tab)</span>}
    </>
  )
  return (
    <WithTooltip label={label} collapsed={collapsed}>
      {href ? (
        <a href={href} target="_blank" rel="noreferrer" className={className}>
          {content}
        </a>
      ) : (
        <Link to={to ?? '/'} onClick={onNavigate} className={className}>
          {content}
        </Link>
      )}
    </WithTooltip>
  )
}

/** The black sidebar's content, shared by the desktop sidebar, the tablet rail and the phone drawer. */
export function SidebarContent({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  return (
    <div className="surface-ink flex h-full flex-col bg-background text-foreground">
      <div className={cn('flex h-16 shrink-0 items-center', collapsed ? 'justify-center' : 'px-5')}>
        <Link
          to="/app"
          onClick={onNavigate}
          aria-label="FITSCAN dashboard"
          className="rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {collapsed ? <BrandMark className="size-8" /> : <BrandLogo />}
        </Link>
      </div>
      <nav aria-label="Application" className={cn('flex-1 overflow-y-auto py-3', collapsed ? 'px-3' : 'px-3')}>
        {!collapsed && <p className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-subtle-foreground">Workspace</p>}
        <ul className="space-y-1">
          {NAV_ITEMS.map((item) => (
            <li key={item.to}>
              <SidebarLink item={item} collapsed={collapsed} onNavigate={onNavigate} />
            </li>
          ))}
        </ul>
      </nav>
      <div className="shrink-0 space-y-0.5 border-t border-border px-3 py-3">
        <FooterLink icon={BookOpen} label="API docs" href={API_DOCS_URL} collapsed={collapsed} />
        <FooterLink icon={ArrowLeft} label="Back to website" to="/" collapsed={collapsed} onNavigate={onNavigate} />
      </div>
    </div>
  )
}

/** Fixed on the left: a 76px icon rail on tablets, the full 256px sidebar from 1024px. Hidden on phones. */
export function AppSidebar() {
  return (
    <div className="fixed inset-y-0 left-0 z-30 hidden w-[76px] md:block lg:w-64">
      <div className="h-full lg:hidden">
        <SidebarContent collapsed />
      </div>
      <div className="hidden h-full lg:block">
        <SidebarContent />
      </div>
    </div>
  )
}
