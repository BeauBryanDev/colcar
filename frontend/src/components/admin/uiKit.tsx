/**
 * Small pieces the three admin pages share: status pills, money, dates,
 * an empty state and a confirm dialog.
 *
 */

import React from 'react'
import { FiAlertCircle, FiInbox, FiX } from 'react-icons/fi'
import { Badge } from '@/components/common/Badge'
import { Button } from '@/components/common/Button'
import type { AppointmentStatus } from '@/types/admin'

//  Formatting  

export function formatCop(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat('es-CO', {
    style: 'currency',
    currency: 'COP',
    maximumFractionDigits: 0,
  }).format(value)
}

/**
 * Render an instant in the **workshop's** timezone, not the reader's.
 *
 * The dashboard is a workshop tool: a slot is "10:00 at the shop" regardless of
 * where the person reading it happens to be. Bookings carry `scheduledLocal`
 * for exactly this, and it should be preferred when present.
 */
export function formatDateTime(
  iso: string | null | undefined,
  timeZone = 'America/Bogota',
): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('es-CO', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone,
  }).format(date)
}

export function formatDate(
  iso: string | null | undefined,
  timeZone = 'America/Bogota',
): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('es-CO', {
    dateStyle: 'medium',
    timeZone,
  }).format(date)
}

/** `YYYY-MM-DD` for a date input — the shape the backend reads as local. */
export function toDateInput(date: Date): string {
  return date.toISOString().slice(0, 10)
}

// Status 

const STATUS_VARIANT: Record<
  AppointmentStatus,
  'blue' | 'green' | 'red' | 'yellow'
> = {
  programada: 'blue',
  confirmada: 'yellow',
  atendida: 'green',
  cancelada: 'red',
}

const STATUS_LABEL: Record<AppointmentStatus, string> = {
  programada: 'Programada',
  confirmada: 'Confirmada',
  atendida: 'Atendida',
  cancelada: 'Cancelada',
}

export const StatusBadge: React.FC<{ status: AppointmentStatus }> = ({
  status,
}) => <Badge variant={STATUS_VARIANT[status]}>{STATUS_LABEL[status]}</Badge>

/**
 * Legal moves, mirroring `_ALLOWED_TRANSITIONS` in app/routers/admin.py.
 *
 * `atendida` and `cancelada` are **terminal**: a booking that was served or
 * cancelled must not quietly reopen, or the history stops meaning anything.
 * The backend answers 409 either way — this only decides which buttons render.
 */
export const ALLOWED_TRANSITIONS: Record<
  AppointmentStatus,
  AppointmentStatus[]
> = {
  programada: ['confirmada', 'cancelada'],
  confirmada: ['atendida', 'cancelada'],
  atendida: [],
  cancelada: [],
}

/** RTM is pass/fail — one rejection cause means No Cumple, never a percentage. */
export const RtmBadge: React.FC<{ rejected: boolean | null | undefined }> = ({
  rejected,
}) => {
  if (rejected === null || rejected === undefined) {
    return <Badge variant="gray">Sin verdicto</Badge>
  }
  return rejected ? (
    <Badge variant="red">No cumple</Badge>
  ) : (
    <Badge variant="green">Cumple</Badge>
  )
}

//  States  
export const EmptyState: React.FC<{ message: string; hint?: string }> = ({
  message,
  hint,
}) => (
  <div className="flex flex-col items-center justify-center py-16 text-center">
    <FiInbox className="w-12 h-12 text-brand-navy/30 mb-3" />
    <p className="text-brand-navy font-semibold">{message}</p>
    {hint && <p className="text-brand-navy/60 text-sm mt-1">{hint}</p>}
  </div>
)

export const ErrorState: React.FC<{ message: string; onRetry?: () => void }> = ({
  message,
  onRetry,
}) => (
  <div
    role="alert"
    className="flex items-start gap-3 bg-brand-red/15 border-2 border-brand-red/50 rounded-xl px-4 py-3"
  >
    <FiAlertCircle className="w-5 h-5 text-brand-red flex-shrink-0 mt-0.5" />
    <div className="flex-1">
      <p className="text-brand-navy font-semibold text-sm">{message}</p>
    </div>
    {onRetry && (
      <Button variant="secondary" size="sm" onClick={onRetry}>
        Reintentar
      </Button>
    )}
  </div>
)

export const TableSkeleton: React.FC<{ rows?: number }> = ({ rows = 5 }) => (
  <div className="space-y-2 py-4" aria-busy="true" aria-label="Cargando">
    {Array.from({ length: rows }).map((_, i) => (
      <div
        key={i}
        className="h-12 bg-brand-navy/5 rounded-lg animate-pulse"
        style={{ animationDelay: `${i * 80}ms` }}
      />
    ))}
  </div>
)

//  Modal 

export const Modal: React.FC<{
  title: string
  onClose: () => void
  children: React.ReactNode
  wide?: boolean
}> = ({ title, onClose, children, wide = false }) => (
  <div
    className="fixed inset-0 z-50 bg-brand-navy/70 flex items-start justify-center p-4 overflow-y-auto"
    role="dialog"
    aria-modal="true"
    aria-label={title}
    onClick={onClose}
  >
    <div
      className={`bg-white rounded-2xl border-4 border-brand-yellow shadow-2xl w-full my-8 ${
        wide ? 'max-w-3xl' : 'max-w-lg'
      }`}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex items-center justify-between bg-brand-navy rounded-t-xl px-5 py-3">
        <h2 className="font-display text-xl text-white tracking-wider uppercase">
          {title}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Cerrar"
          className="text-white/60 hover:text-brand-red transition-colors"
        >
          <FiX className="w-6 h-6" />
        </button>
      </div>
      <div className="p-5">{children}</div>
    </div>
  </div>
)

export const ConfirmDialog: React.FC<{
  title: string
  message: React.ReactNode
  confirmLabel?: string
  danger?: boolean
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}> = ({
  title,
  message,
  confirmLabel = 'Confirmar',
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}) => (
  <Modal title={title} onClose={onCancel}>
    <div className="text-brand-navy text-sm mb-6">{message}</div>
    <div className="flex justify-end gap-2">
      <Button variant="ghost" onClick={onCancel} className="!text-brand-navy !border-brand-navy/30">
        Cancelar
      </Button>
      <Button
        variant={danger ? 'danger' : 'secondary'}
        loading={busy}
        onClick={onConfirm}
      >
        {confirmLabel}
      </Button>
    </div>
  </Modal>
)

//  Layout helpers  

export const PageHeader: React.FC<{
  title: string
  subtitle?: string
  icon?: React.ReactNode
  actions?: React.ReactNode
}> = ({ title, subtitle, icon, actions }) => (
  <div className="flex items-center gap-3 mb-4">
    {icon && (
      <div className="w-11 h-11 rounded-xl bg-brand-navy flex items-center justify-center text-brand-yellow flex-shrink-0">
        {icon}
      </div>
    )}
    <div className="flex-1 min-w-0">
      <h1 className="font-display text-2xl text-brand-navy tracking-wider uppercase leading-none">
        {title}
      </h1>
      {subtitle && (
        <p className="text-brand-navy/60 text-sm mt-0.5">{subtitle}</p>
      )}
    </div>
    {actions}
  </div>
)

export const StatTile: React.FC<{
  label: string
  value: React.ReactNode
  icon?: React.ReactNode
  tone?: 'navy' | 'yellow' | 'blue' | 'red'
}> = ({ label, value, icon, tone = 'navy' }) => {
  const tones = {
    navy: 'bg-brand-navy text-white',
    yellow: 'bg-brand-yellow text-brand-navy',
    blue: 'bg-brand-blue text-white',
    red: 'bg-brand-red text-white',
  }
  return (
    <div className={`rounded-xl p-4 flex items-center gap-3 ${tones[tone]}`}>
      {icon && <div className="opacity-80 flex-shrink-0">{icon}</div>}
      <div className="min-w-0">
        <div className="text-xs uppercase tracking-wide opacity-70 truncate">
          {label}
        </div>
        <div className="font-display text-2xl leading-none mt-0.5">{value}</div>
      </div>
    </div>
  )
}
