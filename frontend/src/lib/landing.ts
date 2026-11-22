// Content and link targets for the public landing page ("/").
// Every link points at something that exists: a section of this page, the application route,
// or the API's own documentation pages. Nothing here is live data.

import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  BookOpen,
  Braces,
  FileText,
  ListChecks,
  MonitorPlay,
  Radar,
  Sigma,
  Target,
  Workflow,
} from 'lucide-react'

import { API_BASE_URL, API_DOCS_ENABLED, API_DOCS_URL } from '@/api/client'

/** The application entry: the dashboard. */
export const APP_PATH = '/app'
/** FastAPI's interactive API reference and the raw OpenAPI document; null when the API does not serve them. */
export { API_DOCS_URL }
export const OPENAPI_URL: string | null = API_DOCS_ENABLED ? `${API_BASE_URL}/openapi.json` : null

/** Section ids, used by the navigation, the footer and the sections themselves. */
export const SECTION = {
  product: 'product',
  matching: 'matching',
  platform: 'platform',
  showcase: 'product-tour',
  howItWorks: 'how-it-works',
  solutions: 'solutions',
  why: 'why-fitscan',
  getStarted: 'get-started',
} as const

export const hash = (id: string) => `#${id}`

export interface MenuLink {
  title: string
  description: string
  icon: LucideIcon
  href: string
  /** Router link inside the app, as opposed to a section anchor or an external page. */
  internal?: boolean
  external?: boolean
}

export interface MenuGroup {
  label: string
  links: MenuLink[]
}

export interface MenuFeature {
  eyebrow: string
  title: string
  text: string
  href: string
  linkLabel: string
}

export const productMenu: { groups: MenuGroup[]; feature: MenuFeature } = {
  groups: [
    {
      label: 'Capabilities',
      links: [
        { title: 'Resume parsing', description: 'PDF text, OCR fallback and skill extraction', icon: FileText, href: hash(SECTION.product) },
        { title: 'Job discovery', description: 'A polite crawler that normalises every listing', icon: Radar, href: hash(SECTION.product) },
        { title: 'Platform workflow', description: 'From crawl and upload to ranked matches', icon: Workflow, href: hash(SECTION.howItWorks) },
      ],
    },
    {
      label: 'Matching',
      links: [
        { title: 'Scoring engine', description: 'Every pair, four weighted dimensions', icon: Target, href: hash(SECTION.matching) },
        { title: 'Explainable results', description: 'Matched and missing skills, with reasons', icon: ListChecks, href: hash(SECTION.matching) },
        { title: 'Product tour', description: 'An interactive preview of the match view', icon: MonitorPlay, href: hash(SECTION.showcase) },
      ],
    },
  ],
  feature: {
    eyebrow: 'Scoring model',
    title: 'One transparent formula',
    text: 'Required skills, nice-to-have skills, experience and location, weighted 70 · 15 · 10 · 5.',
    href: hash(SECTION.matching),
    linkLabel: 'See how a score is built',
  },
}

export const resourcesMenu: { groups: MenuGroup[]; feature: MenuFeature } = {
  groups: [
    // The Developers links point at the API documentation, so the group exists only when the API serves it.
    ...(API_DOCS_URL && OPENAPI_URL
      ? [
          {
            label: 'Developers',
            links: [
              { title: 'API reference', description: 'Interactive documentation for every endpoint', icon: BookOpen, href: API_DOCS_URL, external: true },
              { title: 'OpenAPI schema', description: 'The machine-readable API contract', icon: Braces, href: OPENAPI_URL, external: true },
            ],
          },
        ]
      : []),
    {
      label: 'Platform',
      links: [
        { title: 'System status', description: 'Check that the API, database and queue are up', icon: Activity, href: APP_PATH, internal: true },
        { title: 'How scoring works', description: 'The four dimensions behind every match', icon: Sigma, href: hash(SECTION.matching) },
      ],
    },
  ],
  feature: {
    eyebrow: 'Open the app',
    title: 'Go from overview to operations',
    text: 'Run crawls, upload resumes and review ranked matches in the FITSCAN application.',
    href: APP_PATH,
    linkLabel: 'Open FITSCAN',
  },
}

/** Plain navigation links (no menu). */
export const navLinks = [
  { label: 'Solutions', href: hash(SECTION.solutions) },
  { label: 'Platform', href: hash(SECTION.platform) },
  { label: 'About', href: hash(SECTION.why) },
]

/** Neutral labels for the marquee: who the workflow is for, not customers. */
export const marqueeLabels = [
  'Software & IT services',
  'Staffing agencies',
  'Fintech',
  'Healthcare',
  'Retail & e-commerce',
  'Consulting',
  'Startups',
  'Campus hiring',
  'Shared services',
  'Logistics',
]

/** Product specifications (from the approved design), not customer results. */
export const specs = [
  { value: '100%', label: 'Job–candidate pair coverage', note: 'Every candidate is scored against every job' },
  { value: '10', label: 'Top matches per profile', note: 'Ranked in both directions' },
  { value: '4', label: 'Core matching dimensions', note: 'Required, nice-to-have, experience, location' },
  { value: '0–100', label: 'Explainable match score', note: 'Each point traced to a rule' },
]

export interface Principle {
  label: string
  statement: string
  text: string
}

export const principles: Principle[] = [
  {
    label: 'Transparent matching',
    statement: 'Every score shows its working.',
    text: 'Each match lists the skills that matched, the requirements that are missing, and how experience and location counted. No opaque rankings.',
  },
  {
    label: 'Structured candidate insights',
    statement: 'From a PDF to a profile you can search.',
    text: 'Resumes become structured records with skills, experience, education and location. Scanned files fall back to OCR and are flagged for review.',
  },
  {
    label: 'Consistent evaluation',
    statement: 'The same rules for every candidate.',
    text: 'One documented weighted formula scores every job–candidate pair at full precision. Text similarity is used only to break exact score ties; it never changes a score.',
  },
  {
    label: 'Efficient recruitment workflows',
    statement: 'Crawl, parse and match in the background.',
    text: 'Long-running work runs as background jobs with live progress, logs and cancellation, and results export to CSV or JSON.',
  },
]
