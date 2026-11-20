// Public landing page at "/". It explains FITSCAN and links into the application at /app.
// Every visual uses sample data; nothing on this page calls the API.

import { MotionConfig } from 'framer-motion'
import { useEffect } from 'react'

import { CTASection } from '@/components/sections/CTASection'
import { FeaturesSection } from '@/components/sections/FeaturesSection'
import { Footer } from '@/components/sections/Footer'
import { GradientFeatureTiles } from '@/components/sections/GradientFeatureTiles'
import { Hero } from '@/components/sections/Hero'
import { LogoMarquee } from '@/components/sections/LogoMarquee'
import { MatchingSection } from '@/components/sections/MatchingSection'
import { Navbar } from '@/components/sections/Navbar'
import { PlatformSection } from '@/components/sections/PlatformSection'
import { ProductShowcase } from '@/components/sections/ProductShowcase'
import { StatsBand } from '@/components/sections/StatsBand'
import { TestimonialCarousel } from '@/components/sections/TestimonialCarousel'
import { WorkflowSection } from '@/components/sections/WorkflowSection'

export default function LandingPage() {
  useEffect(() => {
    const previous = document.title
    document.title = 'FITSCAN · Intelligent Job–Candidate Matching'
    return () => {
      document.title = previous
    }
  }, [])

  return (
    // reducedMotion="user": with "reduce motion" switched on, Framer Motion skips movement.
    <MotionConfig reducedMotion="user">
      <div id="top" className="landing min-h-screen overflow-x-clip">
        <a
          href="#main"
          className="sr-only rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50"
        >
          Skip to content
        </a>
        <Navbar />
        <main id="main">
          <Hero />
          <LogoMarquee />
          <StatsBand />
          <FeaturesSection />
          <MatchingSection />
          <PlatformSection />
          <ProductShowcase />
          <WorkflowSection />
          <GradientFeatureTiles />
          <TestimonialCarousel />
          <CTASection />
        </main>
        <Footer />
      </div>
    </MotionConfig>
  )
}
