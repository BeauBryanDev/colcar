import React from 'react'
import { FiChevronDown } from 'react-icons/fi'

export interface SelectOption {
  value: string
  label: string
}

interface SelectListProps {
  label: string
  value: string
  options: SelectOption[]
  onChange: (value: string) => void
  /** Shown as the empty first option. */
  placeholder?: string
  disabled?: boolean
  /** Explains *why* the select is disabled, e.g. "Elige una marca primero". */
  disabledHint?: string
  id?: string
  className?: string
}

export const SelectList: React.FC<SelectListProps> = ({
  label,
  value,
  options,
  onChange,
  placeholder = 'Seleccionar…',
  disabled = false,
  disabledHint,
  id,
  className = '',
}) => {
  const selectId = id ?? `select-${label.toLowerCase().replace(/\s+/g, '-')}`

  return (
    <div className={`flex flex-col gap-1 min-w-0 ${className}`}>
      <label
        htmlFor={selectId}
        className="font-extrabold text-brand-navy uppercase text-xs tracking-wide"
      >
        {label}
      </label>

      <div className="relative">
        <select
          id={selectId}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className={[
            'w-full appearance-none rounded-xl border-2 border-brand-gold',
            'bg-white text-brand-navy text-sm font-semibold',
            'pl-3 pr-9 py-2 cursor-pointer',
            'focus:outline-none focus:ring-2 focus:ring-brand-yellow',
            'disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-brand-navy/5',
          ].join(' ')}
        >
          <option value="">{placeholder}</option>
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        <FiChevronDown
          className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-brand-navy/60"
          aria-hidden="true"
        />
      </div>

      {disabled && disabledHint && (
        <span className="text-brand-navy/60 text-xs leading-tight">{disabledHint}</span>
      )}
    </div>
  )
}

export default SelectList
