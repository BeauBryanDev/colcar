import React from 'react'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'yellow'
type Size = 'sm' | 'md' | 'lg'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
  icon?: React.ReactNode
  iconPosition?: 'left' | 'right'
  fullWidth?: boolean
}

const variantClasses: Record<Variant, string> = {
  primary:
    'bg-brand-red hover:bg-red-700 text-white border-transparent shadow-md hover:shadow-lg',
  secondary:
    'bg-brand-blue hover:bg-blue-700 text-white border-transparent',
  danger:
    'bg-red-600 hover:bg-red-700 text-white border-transparent',
  ghost:
    'bg-transparent hover:bg-white/10 text-white border-white/30 hover:border-white/60',
  yellow:
    'bg-brand-yellow hover:bg-brand-gold text-brand-navy border-transparent font-bold shadow-md',
}

const sizeClasses: Record<Size, string> = {
  sm: 'px-3 py-1.5 text-xs rounded-md',
  md: 'px-4 py-2 text-sm rounded-lg',
  lg: 'px-6 py-3 text-base rounded-xl',
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  loading = false,
  icon,
  iconPosition = 'left',
  fullWidth = false,
  children,
  disabled,
  className = '',
  ...rest
}) => {
  const isDisabled = disabled || loading

  return (
    <button
      {...rest}
      disabled={isDisabled}
      className={[
        'inline-flex items-center justify-center gap-2 border font-semibold',
        'transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-brand-yellow/60',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        variantClasses[variant],
        sizeClasses[size],
        fullWidth ? 'w-full' : '',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {loading ? (
        <span className="inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
      ) : (
        iconPosition === 'left' && icon
      )}
      {children}
      {!loading && iconPosition === 'right' && icon}
    </button>
  )
}

export default Button
