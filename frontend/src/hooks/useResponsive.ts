import { useState, useEffect } from 'react'

const BREAKPOINTS = {
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  '2xl': 1536,
} as const

type Breakpoint = keyof typeof BREAKPOINTS

export function useResponsive() {
  const [width, setWidth] = useState<number>(
    typeof window !== 'undefined' ? window.innerWidth : 1280,
  )

  useEffect(() => {
    const onResize = () => setWidth(window.innerWidth)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const isMobile  = width < BREAKPOINTS.md
  const isTablet  = width >= BREAKPOINTS.md && width < BREAKPOINTS.lg
  const isDesktop = width >= BREAKPOINTS.lg

  function isBelow(bp: Breakpoint) {
    return width < BREAKPOINTS[bp]
  }

  function isAbove(bp: Breakpoint) {
    return width >= BREAKPOINTS[bp]
  }

  return { width, isMobile, isTablet, isDesktop, isBelow, isAbove }
}
