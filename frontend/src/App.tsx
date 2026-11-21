// Routes (React Router, HLD §8.1, LLD §8.2).
//   /                      public landing page
//   /app                   the application entry: the dashboard
//   /background-jobs[/:id] background jobs and one run's detail
//   /jobs[/:id]            jobs and one job with its top candidates
//   /candidates[/:id]      candidates and one candidate with its top jobs
//   /matching, /skills, /exports
// The application pages share one frame (AppShell). Unknown paths go back to the landing page.

import { lazy, Suspense, useEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router'

import { APP_PATH } from '@/lib/landing'

// Each page is its own chunk: the landing page does not download the application, and back.
const LandingPage = lazy(() => import('@/pages/LandingPage'))
const AppShell = lazy(() => import('@/components/app/AppShell'))
const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const BackgroundJobsPage = lazy(() => import('@/pages/BackgroundJobsPage'))
const BackgroundJobDetailPage = lazy(() => import('@/pages/BackgroundJobDetailPage'))
const JobsPage = lazy(() => import('@/pages/JobsPage'))
const JobDetailPage = lazy(() => import('@/pages/JobDetailPage'))
const CandidatesPage = lazy(() => import('@/pages/CandidatesPage'))
const CandidateDetailPage = lazy(() => import('@/pages/CandidateDetailPage'))
const MatchingPage = lazy(() => import('@/pages/MatchingPage'))
const SkillsPage = lazy(() => import('@/pages/SkillsPage'))
const ExportsPage = lazy(() => import('@/pages/ExportsPage'))

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
          <Route element={<AppShell />}>
            <Route path={APP_PATH} element={<DashboardPage />} />
            <Route path="/background-jobs" element={<BackgroundJobsPage />} />
            <Route path="/background-jobs/:id" element={<BackgroundJobDetailPage />} />
            <Route path="/jobs" element={<JobsPage />} />
            <Route path="/jobs/:id" element={<JobDetailPage />} />
            <Route path="/candidates" element={<CandidatesPage />} />
            <Route path="/candidates/:id" element={<CandidateDetailPage />} />
            <Route path="/matching" element={<MatchingPage />} />
            <Route path="/skills" element={<SkillsPage />} />
            <Route path="/exports" element={<ExportsPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </>
  )
}
