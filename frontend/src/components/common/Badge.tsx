import React from 'react'

type BadgeVariant = 'navy' | 'red' | 'yellow' | 'green' | 'blue' | 'gray'

interface BadgeProps {
  children: React.ReactNode
  variant?: BadgeVariant
  className?: string
  dot?: boolean
}

const variantClasses: Record<BadgeVariant, string> = {
  navy:   'bg-brand-navy  text-white',
  red:    'bg-brand-red   text-white',
  yellow: 'bg-brand-yellow text-brand-navy font-bold',
  green:  'bg-emerald-500 text-white',
  blue:   'bg-brand-blue  text-white',
  gray:   'bg-gray-500    text-white',
}

const dotClasses: Record<BadgeVariant, string> = {
  navy:   'bg-white',
  red:    'bg-white',
  yellow: 'bg-brand-navy',
  green:  'bg-white',
  blue:   'bg-white',
  gray:   'bg-white',
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'navy',
  className = '',
  dot = false,
}) => (
  <span
    className={[
      'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-semibold',
      variantClasses[variant],
      className,
    ]
      .filter(Boolean)
      .join(' ')}
  >
    {dot && (
      <span className={`w-2 h-2 rounded-full ${dotClasses[variant]} animate-pulse`} />
    )}
    {children}
  </span>
)

export default Badge
