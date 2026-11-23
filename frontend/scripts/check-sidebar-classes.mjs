// Regression check for the application sidebar (components/app/AppSidebar.tsx), full and collapsed.
//
// The collapsed sidebar (the tablet icon rail) wraps each link in a tooltip trigger with `asChild`. Radix's
// Slot joins `className` values as strings, so a class *function* given to NavLink there once reached the
// DOM as the function's source text, and none of the link's classes (layout, active state, focus ring)
// applied. This renders both variants on the server and checks the classes each link really gets.
//
//   npm run check:sidebar      (Vite loads the TSX; no browser, no network, no build output)

import { realpathSync } from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createServer } from 'vite'

// The real, correctly cased path: Vite resolves packages from it, and so does this script, so both load the
// same React files. (On Windows, `c:\users\...` and `C:\Users\...` would otherwise load two copies of React.)
const root = realpathSync.native(fileURLToPath(new URL('..', import.meta.url)))
const fromRoot = createRequire(`${root}/package.json`)
const load = (name) => import(pathToFileURL(fromRoot.resolve(name)).href)
const server = await createServer({ root, appType: 'custom', logLevel: 'error', server: { middlewareMode: true, hmr: false } })
let failures = 0
const check = (ok, message) => {
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${message}`)
  if (!ok) failures += 1
}

try {
  const { createElement } = await load('react')
  const { renderToStaticMarkup } = await load('react-dom/server')
  const { MemoryRouter } = await load('react-router')
  const { SidebarContent } = await server.ssrLoadModule('/src/components/app/AppSidebar.tsx')
  const { TooltipProvider } = await server.ssrLoadModule('/src/components/ui/tooltip.tsx')
  const { NAV_ITEMS } = await server.ssrLoadModule('/src/lib/app.ts')
  const current = '/jobs'

  for (const collapsed of [true, false]) {
    const variant = collapsed ? 'collapsed rail' : 'full sidebar'
    const html = renderToStaticMarkup(
      createElement(MemoryRouter, { initialEntries: [current] }, createElement(TooltipProvider, null, createElement(SidebarContent, { collapsed }))),
    )
    const nav = html.slice(html.indexOf('<nav'), html.indexOf('</nav>'))
    const links = [...nav.matchAll(/<a\b[^>]*>/g)].map(([tag]) => ({
      href: /href="([^"]*)"/.exec(tag)?.[1],
      classes: (/class="([^"]*)"/.exec(tag)?.[1] ?? '').split(/\s+/),
      active: tag.includes('aria-current="page"'),
    }))

    const withCode = [...html.matchAll(/class="([^"]*)"/g)].filter(([, value]) => value.includes('=&gt;') || value.includes('=>'))
    check(withCode.length === 0, `${variant}: no class attribute contains code (${withCode.length} found)`)
    check(links.length === NAV_ITEMS.length, `${variant}: ${links.length} links for ${NAV_ITEMS.length} navigation items`)
    const unstyled = links.filter((link) => !['flex', 'h-10', 'rounded-lg', 'focus-visible:ring-2'].every((c) => link.classes.includes(c)))
    check(unstyled.length === 0, `${variant}: every link has its layout and focus classes (missing on ${unstyled.map((l) => l.href).join(', ') || 'none'})`)
    const active = links.filter((link) => link.active)
    check(active.length === 1 && active[0].href === current, `${variant}: exactly one active link, ${current} (${active.map((l) => l.href).join(', ') || 'none'})`)
    check(active[0]?.classes.includes('bg-accent-solid/[0.13]') ?? false, `${variant}: the active link has the active background`)
    const spacing = collapsed ? ['justify-center', 'px-0'] : ['px-3']
    check(links.every((link) => spacing.every((c) => link.classes.includes(c))), `${variant}: every link has ${spacing.join(' ')}`)
  }
} finally {
  await server.close()
}

console.log(failures ? `\n${failures} check(s) failed` : '\nAll sidebar checks passed')
process.exit(failures ? 1 : 0)
