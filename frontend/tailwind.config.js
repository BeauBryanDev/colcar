/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontSize: {
        // Shift all sizes up slightly for better readability
        'xs':   ['0.8rem',  { lineHeight: '1.2rem' }],
        'sm':   ['0.925rem',{ lineHeight: '1.4rem' }],
        'base': ['1.05rem', { lineHeight: '1.6rem' }],
        'lg':   ['1.2rem',  { lineHeight: '1.75rem' }],
        'xl':   ['1.35rem', { lineHeight: '1.9rem' }],
        '2xl':  ['1.6rem',  { lineHeight: '2rem' }],
        '3xl':  ['2rem',    { lineHeight: '2.25rem' }],
      },
      colors: {
        brand: {
          navy:   '#0a1628',
          blue:   '#1a3a6e',
          red:    '#cc1f1f',
          yellow: '#c99a00',
          gold:   '#9c7400',
          light:  '#fef3c7',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['Bebas Neue', 'Impact', 'sans-serif'],
      },
      keyframes: {
        // Sweeping scan line: travels the full height, pausing subtly at each end.
        'scan-sweep': {
          '0%':   { transform: 'translateY(-8%)',  opacity: '0' },
          '10%':  { opacity: '1' },
          '90%':  { opacity: '1' },
          '100%': { transform: 'translateY(108%)', opacity: '0' },
        },
        // Reticle corners breathing while the pass runs.
        'reticle-pulse': {
          '0%, 100%': { opacity: '0.35' },
          '50%':      { opacity: '1' },
        },
        // Horizontal shimmer for the indeterminate progress bar.
        'scan-progress': {
          '0%':   { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(300%)' },
        },
      },
      animation: {
        'pulse-dot': 'pulse 1.4s ease-in-out infinite',
        'bounce-slow': 'bounce 2s infinite',
        'scan-sweep': 'scan-sweep 2.2s ease-in-out infinite',
        'reticle-pulse': 'reticle-pulse 1.6s ease-in-out infinite',
        'scan-progress': 'scan-progress 1.6s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
