import React from 'react'

interface LoadingProps {
  /** Three bouncing dots (inline, used in chat "typing" indicator) */
  variant?: 'dots' | 'spinner' | 'pulse'
  size?: 'sm' | 'md' | 'lg'
  color?: 'yellow' | 'white' | 'navy'
  label?: string
}

const dotSizes = { sm: 'w-1.5 h-1.5', md: 'w-2.5 h-2.5', lg: 'w-4 h-4' }
const spinSizes = { sm: 'w-4 h-4', md: 'w-8 h-8', lg: 'w-12 h-12' }
const colorMap = { yellow: 'border-brand-yellow', white: 'border-white', navy: 'border-brand-navy' }
const dotColorMap = { yellow: 'bg-brand-yellow', white: 'bg-white', navy: 'bg-brand-navy' }

export const Loading: React.FC<LoadingProps> = ({
  variant = 'dots',
  size = 'md',
  color = 'yellow',
  label,
}) => {
  if (variant === 'dots') {
    return (
      <span className="inline-flex items-center gap-1" aria-label={label ?? 'Cargando...'}>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className={[
              'rounded-full',
              dotSizes[size],
              dotColorMap[color],
              'animate-bounce',
            ].join(' ')}
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </span>
    )
  }

  if (variant === 'spinner') {
    return (
      <span
        aria-label={label ?? 'Cargando...'}
        className={[
          'inline-block rounded-full border-4 border-t-transparent animate-spin',
          spinSizes[size],
          colorMap[color],
        ].join(' ')}
      />
    )
  }

  // pulse
  return (
    <span
      aria-label={label ?? 'Cargando...'}
      className={[
        'inline-block rounded-full animate-pulse',
        spinSizes[size],
        dotColorMap[color],
      ].join(' ')}
    />
  )
}

export default Loading
