/**
 * Bookings: filter, inspect, and move through the lifecycle.
 *
 * Both roles reach everything here, contact details included — the secretary
 * phones customers to confirm, so a screen without the phone number is
 * useless (owner's decision). Staff may cancel too.
 *
 * **Dates are sent as bare `YYYY-MM-DD`.** The backend reads a naive date as
 * workshop-local and widens `date_to` to the end of that day; sending a UTC
 * instant instead would put five hours of every evening on the wrong date.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  FiCalendar,
  FiDollarSign,
  FiMail,
  FiPhone,
  FiRefreshCw,
  FiSearch,
  FiUser,
} from 'react-icons/fi'
import { Button } from '@/components/common/Button'
import { adminService } from '@/services/adminService'
import {
  ALLOWED_TRANSITIONS,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Modal,
  PageHeader,
  StatTile,
  StatusBadge,
  TableSkeleton,
  formatCop,
  formatDateTime,
} from '@/components/admin/uiKit'
import type {
  AppointmentDetail,
  AppointmentFilters,
  AppointmentStatus,
  AppointmentSummary,
} from '@/types/admin'

const STATUS_OPTIONS: Array<{ value: '' | AppointmentStatus; label: string }> = [
  { value: '', label: 'Todos los estados' },
  { value: 'programada', label: 'Programada' },
  { value: 'confirmada', label: 'Confirmada' },
  { value: 'atendida', label: 'Atendida' },
  { value: 'cancelada', label: 'Cancelada' },
]

const TRANSITION_LABEL: Record<AppointmentStatus, string> = {
  programada: 'Reprogramar',
  confirmada: 'Confirmar',
  atendida: 'Marcar atendida',
  cancelada: 'Cancelar',
}

export const AppointmentsPage: React.FC = () => {
  const [rows, setRows] = useState<AppointmentSummary[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [filters, setFilters] = useState<AppointmentFilters>({})
  const [codigoInput, setCodigoInput] = useState('')

  const [detail, setDetail] = useState<AppointmentDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [pending, setPending] = useState<{
    row: AppointmentSummary
    target: AppointmentStatus
  } | null>(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await adminService.listAppointments(filters)
      setRows(data.appointments)
      setTotal(data.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error cargando citas.')
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => {
    void load()
  }, [load])

  // Derived from the real payload — never a hardcoded figure.
  const stats = useMemo(() => {
    const open = rows.filter(
      (r) => r.status === 'programada' || r.status === 'confirmada',
    )
    const quoted = rows.reduce(
      (sum, r) => sum + (r.estimatedRepairCostCop ?? 0),
      0,
    )
    return { open: open.length, quoted }
  }, [rows])

  const openDetail = async (codigo: string) => {
    setDetailLoading(true)
    try {
      setDetail(await adminService.getAppointment(codigo))
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : 'No se pudo cargar la cita.',
      )
    } finally {
      setDetailLoading(false)
    }
  }

  const applyTransition = async () => {
    if (!pending) return
    setBusy(true)
    setActionError(null)
    try {
      const updated = await adminService.updateAppointmentStatus(
        pending.row.codigo,
        pending.target,
      )
      setRows((prev) =>
        prev.map((r) => (r.codigo === updated.codigo ? updated : r)),
      )
      setPending(null)
    } catch (err) {
      // A 409 here means the backend's transition table disagreed — show it
      // rather than silently leaving the row looking changed.
      setActionError(
        err instanceof Error ? err.message : 'No se pudo cambiar el estado.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-7xl mx-auto">
      <PageHeader
        title="Citas"
        subtitle={`${total} cita(s) según los filtros`}
        icon={<FiCalendar className="w-6 h-6" />}
        actions={
          <Button
            variant="secondary"
            size="sm"
            icon={<FiRefreshCw className="w-4 h-4" />}
            onClick={() => void load()}
          >
            Actualizar
          </Button>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
        <StatTile
          label="Citas listadas"
          value={total}
          tone="navy"
          icon={<FiCalendar className="w-7 h-7" />}
        />
        <StatTile
          label="Abiertas"
          value={stats.open}
          tone="blue"
          icon={<FiUser className="w-7 h-7" />}
        />
        <StatTile
          label="Cotizado (listado)"
          value={formatCop(stats.quoted)}
          tone="yellow"
          icon={<FiDollarSign className="w-7 h-7" />}
        />
      </div>

      {/* ── Filters ─────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border-2 border-brand-navy/10 p-4 mb-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <label className="block">
            <span className="text-brand-navy/70 text-xs uppercase font-semibold">
              Desde
            </span>
            <input
              type="date"
              value={filters.date_from ?? ''}
              onChange={(e) =>
                setFilters((f) => ({
                  ...f,
                  date_from: e.target.value || undefined,
                }))
              }
              className="mt-1 w-full border-2 border-brand-navy/20 focus:border-brand-yellow rounded-lg px-3 py-2 text-brand-navy outline-none"
            />
          </label>
          <label className="block">
            <span className="text-brand-navy/70 text-xs uppercase font-semibold">
              Hasta
            </span>
            <input
              type="date"
              value={filters.date_to ?? ''}
              onChange={(e) =>
                setFilters((f) => ({
                  ...f,
                  date_to: e.target.value || undefined,
                }))
              }
              className="mt-1 w-full border-2 border-brand-navy/20 focus:border-brand-yellow rounded-lg px-3 py-2 text-brand-navy outline-none"
            />
          </label>
          <label className="block">
            <span className="text-brand-navy/70 text-xs uppercase font-semibold">
              Estado
            </span>
            <select
              value={filters.status ?? ''}
              onChange={(e) =>
                setFilters((f) => ({
                  ...f,
                  status: (e.target.value || undefined) as
                    | AppointmentStatus
                    | undefined,
                }))
              }
              className="mt-1 w-full border-2 border-brand-navy/20 focus:border-brand-yellow rounded-lg px-3 py-2 text-brand-navy outline-none bg-white"
            >
              {STATUS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-brand-navy/70 text-xs uppercase font-semibold">
              Código
            </span>
            <div className="mt-1 flex gap-2">
              <input
                type="text"
                value={codigoInput}
                placeholder="ABC123"
                onChange={(e) => setCodigoInput(e.target.value.toUpperCase())}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    setFilters((f) => ({
                      ...f,
                      codigo: codigoInput || undefined,
                    }))
                  }
                }}
                className="flex-1 min-w-0 border-2 border-brand-navy/20 focus:border-brand-yellow rounded-lg px-3 py-2 text-brand-navy outline-none uppercase"
              />
              <Button
                variant="secondary"
                icon={<FiSearch className="w-4 h-4" />}
                onClick={() =>
                  setFilters((f) => ({ ...f, codigo: codigoInput || undefined }))
                }
              >
                <span className="sr-only">Buscar</span>
              </Button>
            </div>
          </label>
        </div>
        {(filters.date_from ||
          filters.date_to ||
          filters.status ||
          filters.codigo) && (
          <button
            type="button"
            className="mt-3 text-brand-blue text-sm font-semibold hover:underline"
            onClick={() => {
              setFilters({})
              setCodigoInput('')
            }}
          >
            Limpiar filtros
          </button>
        )}
      </div>

      {actionError && (
        <div className="mb-4">
          <ErrorState message={actionError} />
        </div>
      )}

      {/* ── Table ───────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border-2 border-brand-navy/10 overflow-hidden">
        {loading ? (
          <div className="px-4">
            <TableSkeleton />
          </div>
        ) : error ? (
          <div className="p-4">
            <ErrorState message={error} onRetry={() => void load()} />
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            message="No hay citas con estos filtros"
            hint="Las citas las crea el agente cuando el cliente confirma."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-brand-navy text-white">
                <tr>
                  <th className="text-left px-4 py-2.5 font-display tracking-wider uppercase">
                    Código
                  </th>
                  <th className="text-left px-4 py-2.5 font-display tracking-wider uppercase">
                    Cliente
                  </th>
                  <th className="text-left px-4 py-2.5 font-display tracking-wider uppercase">
                    Placa
                  </th>
                  <th className="text-left px-4 py-2.5 font-display tracking-wider uppercase">
                    Vehículo
                  </th>
                  <th className="text-left px-4 py-2.5 font-display tracking-wider uppercase">
                    Cita
                  </th>
                  <th className="text-right px-4 py-2.5 font-display tracking-wider uppercase">
                    Estimado
                  </th>
                  <th className="text-left px-4 py-2.5 font-display tracking-wider uppercase">
                    Estado
                  </th>
                  <th className="text-right px-4 py-2.5 font-display tracking-wider uppercase">
                    Acciones
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.appointmentId}
                    className="border-b border-brand-navy/10 hover:bg-brand-yellow/10 transition-colors"
                  >
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => void openDetail(row.codigo)}
                        className="font-mono font-bold text-brand-blue hover:underline"
                      >
                        {row.codigo}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-semibold text-brand-navy">
                        {row.customerName}
                      </div>
                      {/* Contact details are shown to staff too — owner's call. */}
                      <div className="flex flex-col gap-0.5 mt-0.5 text-brand-navy/60 text-xs">
                        <a
                          href={`tel:${row.customerPhone}`}
                          className="flex items-center gap-1 hover:text-brand-blue"
                        >
                          <FiPhone className="w-3 h-3" />
                          {row.customerPhone}
                        </a>
                        <a
                          href={`mailto:${row.customerEmail}`}
                          className="flex items-center gap-1 hover:text-brand-blue"
                        >
                          <FiMail className="w-3 h-3" />
                          {row.customerEmail}
                        </a>
                      </div>
                    </td>
                    {/* The plate is what identifies the car in the yard, so it
                        gets its own column rather than being folded into the
                        vehicle description. Collected by the agent as a
                        required argument, but older bookings predate it — an
                        em dash, never a placeholder plate. */}
                    <td className="px-4 py-3">
                      {row.licensePlate ? (
                        <span className="inline-block font-mono font-bold tracking-widest text-brand-navy bg-brand-light border-2 border-brand-navy/30 rounded px-2 py-0.5">
                          {row.licensePlate}
                        </span>
                      ) : (
                        <span className="text-brand-navy/40">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-brand-navy">
                      {[row.brand, row.vehicleModel, row.year]
                        .filter(Boolean)
                        .join(' ') || '—'}
                    </td>
                    <td className="px-4 py-3 text-brand-navy">
                      {/* scheduledLocal is the workshop's own string. */}
                      {row.scheduledLocal || formatDateTime(row.scheduledFor)}
                      <div className="text-brand-navy/50 text-xs">
                        {row.timezone}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right font-semibold text-brand-navy whitespace-nowrap">
                      {formatCop(row.estimatedRepairCostCop)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={row.status} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-1 flex-wrap">
                        {ALLOWED_TRANSITIONS[row.status].length === 0 ? (
                          <span className="text-brand-navy/40 text-xs italic">
                            estado final
                          </span>
                        ) : (
                          ALLOWED_TRANSITIONS[row.status].map((target) => (
                            <Button
                              key={target}
                              size="sm"
                              variant={
                                target === 'cancelada' ? 'danger' : 'secondary'
                              }
                              onClick={() => setPending({ row, target })}
                            >
                              {TRANSITION_LABEL[target]}
                            </Button>
                          ))
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Transition confirm ──────────────────────────────────────────── */}
      {pending && (
        <ConfirmDialog
          title="Cambiar estado"
          danger={pending.target === 'cancelada'}
          busy={busy}
          confirmLabel={TRANSITION_LABEL[pending.target]}
          message={
            <>
              La cita <strong>{pending.row.codigo}</strong> de{' '}
              <strong>{pending.row.customerName}</strong> pasará de{' '}
              <strong>{pending.row.status}</strong> a{' '}
              <strong>{pending.target}</strong>.
              {(pending.target === 'cancelada' ||
                pending.target === 'atendida') && (
                <p className="mt-2 text-brand-red font-semibold">
                  Es un estado final: no se podrá revertir. Reabrir significa
                  crear una cita nueva.
                </p>
              )}
            </>
          }
          onCancel={() => setPending(null)}
          onConfirm={() => void applyTransition()}
        />
      )}

      {/* ── Detail ──────────────────────────────────────────────────────── */}
      {(detail || detailLoading) && (
        <Modal title="Detalle de la cita" wide onClose={() => setDetail(null)}>
          {detailLoading || !detail ? (
            <TableSkeleton rows={4} />
          ) : (
            <div className="space-y-4 text-brand-navy">
              <div className="flex items-center gap-3">
                <span className="font-mono text-2xl font-bold text-brand-blue">
                  {detail.codigo}
                </span>
                <StatusBadge status={detail.status} />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <h3 className="font-display tracking-wider uppercase text-sm text-brand-navy/60 mb-1">
                    Cliente
                  </h3>
                  <p className="font-semibold">{detail.customerName}</p>
                  <p className="text-sm">{detail.customerPhone}</p>
                  <p className="text-sm">{detail.customerEmail}</p>
                </div>
                <div>
                  <h3 className="font-display tracking-wider uppercase text-sm text-brand-navy/60 mb-1">
                    Vehículo
                  </h3>
                  <p className="font-semibold">
                    {[detail.brand, detail.vehicleModel, detail.year]
                      .filter(Boolean)
                      .join(' ') || '—'}
                  </p>
                  {detail.licensePlate && (
                    <p className="text-sm">Placa: {detail.licensePlate}</p>
                  )}
                </div>
                <div>
                  <h3 className="font-display tracking-wider uppercase text-sm text-brand-navy/60 mb-1">
                    Cita
                  </h3>
                  <p className="font-semibold">{detail.scheduledLocal}</p>
                  <p className="text-sm text-brand-navy/60">
                    {detail.timezone}
                  </p>
                </div>
                <div>
                  <h3 className="font-display tracking-wider uppercase text-sm text-brand-navy/60 mb-1">
                    Estimado
                  </h3>
                  <p className="font-display text-2xl">
                    {formatCop(detail.estimatedRepairCostCop)}
                  </p>
                  {/* The cost above is already net of the discount; show what
                      was taken off so staff are not confused by a figure that
                      shrank after booking. */}
                  {detail.discountCode && (
                    <p className="text-sm text-brand-navy/60">
                      Antes {formatCop(detail.originalCostCop)} &middot;{' '}
                      {detail.discountPercent}% descuento (
                      {detail.ticketNumber ?? detail.discountCode})
                    </p>
                  )}
                </div>
              </div>

              {detail.notes && (
                <div>
                  <h3 className="font-display tracking-wider uppercase text-sm text-brand-navy/60 mb-1">
                    Notas
                  </h3>
                  <p className="text-sm">{detail.notes}</p>
                </div>
              )}

              {/* The quote as booked — kept so the workshop sees what was
                  promised even if the inspection changes later. */}
              {detail.inspectionSnapshot && (
                <div>
                  <h3 className="font-display tracking-wider uppercase text-sm text-brand-navy/60 mb-1">
                    Cotización al momento de agendar
                  </h3>
                  <pre className="bg-brand-navy/5 rounded-lg p-3 text-xs overflow-x-auto">
                    {JSON.stringify(detail.inspectionSnapshot, null, 2)}
                  </pre>
                </div>
              )}

              <p className="text-brand-navy/50 text-xs">
                Inspección: <span className="font-mono">{detail.inspectionId}</span>
              </p>
            </div>
          )}
        </Modal>
      )}
    </div>
  )
}

export default AppointmentsPage
