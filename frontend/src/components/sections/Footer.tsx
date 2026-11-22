import { ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router'

import { BrandLogo } from '@/components/landing/BrandMark'
import { API_DOCS_URL, APP_PATH, hash, SECTION } from '@/lib/landing'

const linkClass =
  'inline-flex items-center gap-1 rounded text-muted-foreground underline-offset-4 outline-none transition-colors duration-200 hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring'

/** Minimal footer: logo, one line, the essential links and the copyright. */
export function Footer() {
  return (
    <footer className="surface-ink">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-8 md:flex-row md:items-end md:justify-between">
          <div>
            <BrandLogo />
            <p className="mt-3 max-w-sm text-sm text-muted-foreground">Job discovery, resume intelligence and explainable candidate matching.</p>
          </div>
          <nav aria-label="Footer">
            <ul className="flex flex-wrap gap-x-7 gap-y-3 text-sm">
              <li>
                <a href={hash(SECTION.showcase)} className={linkClass}>
                  Product tour
                </a>
              </li>
              <li>
                <a href={hash(SECTION.howItWorks)} className={linkClass}>
                  How it works
                </a>
              </li>
              {API_DOCS_URL && (
                <li>
                  <a href={API_DOCS_URL} target="_blank" rel="noreferrer" className={linkClass}>
                    API docs
                    <ArrowUpRight className="size-3.5" aria-hidden="true" />
                    <span className="sr-only">(opens in a new tab)</span>
                  </a>
                </li>
              )}
              <li>
                <Link to={APP_PATH} className={linkClass}>
                  Open the app
                </Link>
              </li>
            </ul>
          </nav>
        </div>
        <div className="mt-10 flex flex-col gap-2 border-t border-border pt-6 text-xs text-subtle-foreground sm:flex-row sm:items-center sm:justify-between">
          <p>© {new Date().getFullYear()} FITSCAN</p>
          <p>Names, companies and scores on this page are sample data.</p>
        </div>
      </div>
    </footer>
  )
}
