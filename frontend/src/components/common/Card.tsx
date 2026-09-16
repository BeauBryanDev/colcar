import React from 'react'

interface CardProps {
  children: React.ReactNode
  className?: string
  variant?: 'yellow' | 'navy' | 'blue' | 'transparent'
  bordered?: boolean
  onClick?: () => void
}

const variantClasses: Record<NonNullable<CardProps['variant']>, string> = {
  yellow:      'bg-brand-yellow border-brand-gold',
  navy:        'bg-brand-navy border-brand-blue',
  blue:        'bg-brand-blue border-blue-600',
  transparent: 'bg-white/5 border-white/10',
}

export const Card: React.FC<CardProps> = ({
  children,
  className = '',
  variant = 'yellow',
  bordered = true,
  onClick,
}) => {
  return (
    <div
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={onClick ? (e) => e.key === 'Enter' && onClick() : undefined}
      className={[
        'rounded-xl p-4',
        bordered ? 'border-2' : 'border-0',
        variantClasses[variant],
        onClick ? 'cursor-pointer hover:brightness-105 transition-all' : '',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {children}
    </div>
  )
}

export default Card
