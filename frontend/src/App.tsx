// Routes (React Router, HLD §8.1).
//   /      public landing page
//   /app   the application entry: today the system status page; the Background jobs page
//          (LLD §8.2) will take over this entry in a later phase.
// Unknown paths go back to the landing page.

import { lazy, Suspense, useEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router'

import { APP_PATH } from '@/lib/landing'

// Each page is its own chunk: the application does not download the landing page's code.
const HomePage = lazy(() => import('@/pages/HomePage'))
const LandingPage = lazy(() => import('@/pages/LandingPage'))

/** Start each new page at the top; in-page anchors (#section) keep their own scrolling. */
function ScrollToTop() {
  const { pathname, hash } = useLocation()
  useEffect(() => {
    if (!hash) window.scrollTo(0, 0)
    // Only a change of page scrolls to the top; `hash` is read here, not watched.
  }, [pathname])
  return null
}

export default function App() {
  return (
    <>
      <ScrollToTop />
      <Suspense fallback={null}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path={APP_PATH} element={<HomePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </>
  )
}
