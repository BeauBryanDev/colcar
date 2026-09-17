import React from 'react'
import { Header } from '@/layouts/Header'
import { Sections } from '@/layouts/Sections'
import { Footer } from '@/layouts/Footer'

/**
 * Home — the single-page Car-Inspector application.
 * Renders: Header → Sections (3-column grid) → Footer
 */
const Home: React.FC = () => (
  <div className="w-full min-h-screen flex flex-col bg-brand-red/20">
    <Header />
    <Sections />
    <Footer />
  </div>
)

export default Home
