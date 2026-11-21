// Application navigation and settings (the pages beside /app; LLD §8.2).

import type { LucideIcon } from 'lucide-react'
import { Briefcase, Download, LayoutDashboard, Tags, Target, Users, Workflow } from 'lucide-react'

export interface NavItem {
  label: string
  to: string
  icon: LucideIcon
  /** One line on what the page is for (also the "coming soon" text while the page is not built). */
  summary: string
}

/** The sidebar, in order. Icons follow the landing page where it shows the same idea. */
export const NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard', to: '/app', icon: LayoutDashboard, summary: 'Live overview of jobs, candidates and background work.' },
  { label: 'Jobs', to: '/jobs', icon: Briefcase, summary: 'Search crawled job postings, open one to see its top candidates, and export.' },
  { label: 'Candidates', to: '/candidates', icon: Users, summary: 'Search parsed resumes, open one to see its top jobs, and export the match table.' },
  { label: 'Matching', to: '/matching', icon: Target, summary: 'How scores are computed, the last match run, and recomputing matches.' },
  { label: 'Background jobs', to: '/background-jobs', icon: Workflow, summary: 'Start crawls, upload resumes and recompute matches, then follow each run live.' },
  { label: 'Skills', to: '/skills', icon: Tags, summary: 'The canonical skill list that job and candidate skills are normalised to.' },
  { label: 'Exports', to: '/exports', icon: Download, summary: 'Download jobs, candidates and the match table as CSV or JSON.' },
]

/** The navigation item a path belongs to: /jobs/123 belongs to Jobs. */
export function navItemFor(pathname: string): NavItem | undefined {
  return NAV_ITEMS.find((item) => pathname === item.to || pathname.startsWith(`${item.to}/`))
}

/** How often live views refresh while a background job is queued or running (HLD §8.1, LLD §8.5). */
export const POLL_INTERVAL_MS = Math.max(500, Number(import.meta.env.VITE_POLL_INTERVAL_MS) || 2000)

/** How often the header re-checks GET /health. */
export const HEALTH_INTERVAL_MS = 30_000
