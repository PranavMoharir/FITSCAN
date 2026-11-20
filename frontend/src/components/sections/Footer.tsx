import { ArrowUp, ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router'

import { BrandLogo } from '@/components/landing/BrandMark'
import { API_DOCS_URL, APP_PATH, hash, OPENAPI_URL, SECTION } from '@/lib/landing'

interface FooterLink {
  label: string
  href: string
  internal?: boolean
  external?: boolean
}

const columns: { title: string; links: FooterLink[] }[] = [
  {
    title: 'Product',
    links: [
      { label: 'Capabilities', href: hash(SECTION.product) },
      { label: 'Explainable matching', href: hash(SECTION.matching) },
      { label: 'Product tour', href: hash(SECTION.showcase) },
      { label: 'How it works', href: hash(SECTION.howItWorks) },
    ],
  },
  {
    title: 'Platform',
    links: [
      { label: 'Open the app', href: APP_PATH, internal: true },
      { label: 'Platform overview', href: hash(SECTION.platform) },
      { label: 'Solutions', href: hash(SECTION.solutions) },
    ],
  },
  {
    title: 'Resources',
    links: [
      { label: 'API reference', href: API_DOCS_URL, external: true },
      { label: 'OpenAPI schema', href: OPENAPI_URL, external: true },
      { label: 'How scoring works', href: hash(SECTION.matching) },
    ],
  },
  {
    title: 'About',
    links: [
      { label: 'Why FITSCAN', href: hash(SECTION.why) },
      { label: 'Get started', href: hash(SECTION.getStarted) },
    ],
  },
]

const linkClass = 'inline-flex items-center gap-1 rounded text-muted-foreground outline-none transition-colors duration-200 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring'

export function Footer() {
  return (
    <footer className="relative overflow-hidden border-t border-white/[0.06] bg-surface">
      {/* Decorative: the brand's two circles, very faint. */}
      <svg aria-hidden="true" className="pointer-events-none absolute -bottom-40 -right-24 h-[30rem] w-[42rem] text-white/[0.035]" viewBox="0 0 420 300" fill="none">
        <circle cx="160" cy="150" r="130" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="260" cy="150" r="130" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="210" cy="150" r="60" stroke="currentColor" strokeDasharray="3 7" />
      </svg>

      <div className="relative mx-auto max-w-7xl px-4 pb-10 pt-16 sm:px-6 lg:px-8">
        <div className="grid gap-12 lg:grid-cols-[1.3fr_2fr]">
          <div>
            <BrandLogo />
            <p className="mt-5 max-w-sm text-sm leading-relaxed text-muted-foreground">
              Job discovery, resume intelligence and explainable candidate matching in one platform.
            </p>
            <Link
              to={APP_PATH}
              className="mt-6 inline-flex items-center gap-1.5 rounded-full border border-white/10 px-4 py-2 text-sm font-medium outline-none transition-colors hover:bg-white/[0.06] focus-visible:ring-2 focus-visible:ring-ring"
            >
              Open FITSCAN
              <ArrowUpRight className="size-4" aria-hidden="true" />
            </Link>
          </div>
          <nav aria-label="Footer" className="grid grid-cols-2 gap-10 sm:grid-cols-4">
            {columns.map((column) => (
              <div key={column.title}>
                <h2 className="text-sm font-semibold">{column.title}</h2>
                <ul className="mt-4 space-y-3 text-sm">
                  {column.links.map((link) => (
                    <li key={link.label}>
                      {link.internal ? (
                        <Link to={link.href} className={linkClass}>
                          {link.label}
                        </Link>
                      ) : (
                        <a href={link.href} className={linkClass} {...(link.external ? { target: '_blank', rel: 'noreferrer' } : {})}>
                          {link.label}
                          {link.external && <ArrowUpRight className="size-3.5" aria-hidden="true" />}
                          {link.external && <span className="sr-only">(opens in a new tab)</span>}
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
        </div>

        <div className="mt-14 flex flex-col gap-4 border-t border-white/[0.06] pt-6 text-xs text-subtle-foreground sm:flex-row sm:items-center sm:justify-between">
          <p>© {new Date().getFullYear()} FITSCAN. Names, companies and scores shown on this page are sample data.</p>
          <a href="#top" className={`${linkClass} text-xs`}>
            Back to top
            <ArrowUp className="size-3.5" aria-hidden="true" />
          </a>
        </div>
      </div>
    </footer>
  )
}
