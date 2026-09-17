/**
 * Weekly calendar of bookings, with drag-to-reschedule.
 *
 * Reads `GET /admin/appointments` for the visible week and writes through
 * `PATCH /admin/appointments/{codigo}/schedule` — the same repository call and
 * the same `parse_slot` the agent's `reschedule_appointment` tool uses, so a
 * booking moved from here obeys the rules a booking moved from chat obeys.
 *
 * ## The timezone decision, which is the whole trick here
 *
 * Slots are stored in UTC; the workshop lives in `America/Bogota` (UTC-5); the
 * admin's browser could be anywhere. Three clocks, and FullCalendar only speaks
 * two of them natively (`local` and `UTC`) — a named zone needs an extra
 * luxon/moment plugin.
 *
 * So the grid runs in **`timeZone: 'UTC'` and is fed workshop wall-clock
 * times**. Each booking's UTC instant is converted to its own workshop hour via
 * `Intl` and handed over as a *naive* string, which FullCalendar then renders
 * verbatim instead of shifting it. The 08:00–18:00 bounds therefore mean the
 * workshop's 08:00–18:00 on every machine, and the hour a card is dropped on
 * reads back as the workshop hour to send as `fecha`/`hora`.
 *
 * Feeding `scheduledFor` with `timeZone: 'local'` instead would look right only
 * on a laptop already set to Bogota, and would quietly slide every card by the
 * offset anywhere else — a secretary in another zone would drag a booking into
 * an hour the backend then rejects, or worse, a wrong one it accepts.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import FullCalendar from '@fullcalendar/react'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
import type {
  DatesSetArg,
  EventClickArg,
  EventContentArg,
  EventDropArg,
  EventInput,
} from '@fullcalendar/core'
import esLocale from '@fullcalendar/core/locales/es'
import { FiCalendar, FiPhone, FiRefreshCw } from 'react-icons/fi'
import { Button } from '@/components/common/Button'
import { adminService } from '@/services/adminService'
import {
  ALLOWED_TRANSITIONS,
  ConfirmDialog,
  ErrorState,
  PageHeader,
  StatusBadge,
  formatCop,
} from '@/components/admin/uiKit'
import type { AppointmentStatus, AppointmentSummary } from '@/types/admin'

/**
 * Mirrors `workshop_open_hour` / `workshop_close_hour` / `workshop_days` in
 * app/core/config.py. Changing them there means changing them here — the grid
 * would otherwise offer hours `parse_slot` refuses, and the secretary would
 * only find out on the 400.
 */
const OPEN_HOUR = 8
const CLOSE_HOUR = 18
/** Mon..Sat. FullCalendar counts days from Sunday=0; the backend from Monday=0. */
const WORKSHOP_WEEKDAYS = [1, 2, 3, 4, 5, 6]

/** Cancelled bookings are history, not schedule — they do not hold a slot. */
const HIDDEN_ON_CALENDAR: AppointmentStatus[] = ['cancelada']

const EVENT_COLOR: Record<AppointmentStatus, string> = {
  programada: '#1a3a6e', // brand-blue
  confirmada: '#c99a00', // brand-yellow
  atendida: '#15803d',
  cancelada: '#cc1f1f', // brand-red
}

/** A booking is only draggable while it is still open. */
function isMovable(status: AppointmentStatus): boolean {
  return ALLOWED_TRANSITIONS[status].length > 0
}

/**
 * An instant → that same moment as workshop wall-clock, `YYYY-MM-DDTHH:mm:ss`.
 *
 * `en-CA` because it formats dates as `YYYY-MM-DD`; `hourCycle: 'h23'` because
 * `hour12: false` alone renders midnight as `24` in several runtimes, which
 * would push a booking onto the previous day.
 */
function toWorkshopWallClock(iso: string, timeZone: string): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  })
    .formatToParts(new Date(iso))
    .reduce<Record<string, string>>((acc, p) => {
      acc[p.type] = p.value
      return acc
    }, {})
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}`
}

/**
 * The reverse, for a date FullCalendar hands back from a drop. Because the grid
 * is in UTC, the UTC parts of that Date *are* the workshop wall-clock the user
 * pointed at — so read them, never the local ones.
 */
function fromGridDate(date: Date): { fecha: string; hora: string } {
  const iso = date.toISOString()
  return { fecha: iso.slice(0, 10), hora: iso.slice(11, 16) }
}

/** `YYYY-MM-DD` for a Date already expressed in grid (UTC) terms. */
function gridDay(date: Date): string {
  return date.toISOString().slice(0, 10)
}

interface PendingMove {
  row: AppointmentSummary
  fecha: string
  hora: string
  revert: () => void
}

export const CalendarPage: React.FC = () => {
  const [rows, setRows] = useState<AppointmentSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const [range, setRange] = useState<{ from: string; to: string } | null>(null)
  const [selected, setSelected] = useState<AppointmentSummary | null>(null)
  const [pending, setPending] = useState<PendingMove | null>(null)
  const [busy, setBusy] = useState(false)

  // FullCalendar fires datesSet on mount as well as on navigation, so the week
  // it decides to show is what drives the fetch — there is no second source of
  // truth to keep in step.
  const load = useCallback(async () => {
    if (!range) return
    setLoading(true)
    setError(null)
    try {
      const data = await adminService.listAppointments({
        date_from: range.from,
        date_to: range.to,
        limit: 500,
      })
      setRows(data.appointments)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error cargando citas.')
    } finally {
      setLoading(false)
    }
  }, [range])

  useEffect(() => {
    void load()
  }, [load])

  const events = useMemo<EventInput[]>(
    () =>
      rows
        .filter((r) => !HIDDEN_ON_CALENDAR.includes(r.status))
        .map((r) => ({
          id: r.codigo,
          title: `${r.codigo} · ${r.customerName}`,
          start: toWorkshopWallClock(r.scheduledFor, r.timezone),
          // The backend stores a start, not a duration; one hour is the slot
          // granularity the workshop books in, so cards fill their own slot
          // rather than rendering as zero-height slivers.
          end: toWorkshopWallClock(
            new Date(
              new Date(r.scheduledFor).getTime() + 60 * 60 * 1000,
            ).toISOString(),
            r.timezone,
          ),
          backgroundColor: EVENT_COLOR[r.status],
          borderColor: EVENT_COLOR[r.status],
          editable: isMovable(r.status),
          extendedProps: { row: r },
        })),
    [rows],
  )

  const rangeRef = useRef<string>('')
  const handleDatesSet = (arg: DatesSetArg) => {
    // `end` is exclusive; step back a day so the request does not pull an extra
    // one. The backend widens a bare date to the end of that workshop day.
    const to = new Date(arg.end.getTime() - 24 * 60 * 60 * 1000)
    const next = { from: gridDay(arg.start), to: gridDay(to) }
    const key = `${next.from}|${next.to}`
    if (rangeRef.current === key) return // same week, don't refetch
    rangeRef.current = key
    setRange(next)
  }

  const handleEventDrop = (arg: EventDropArg) => {
    const row = arg.event.extendedProps.row as AppointmentSummary
    if (!arg.event.start) {
      arg.revert()
      return
    }
    const { fecha, hora } = fromGridDate(arg.event.start)
    // Confirm before writing: a drag is easy to do by accident, and the card
    // stays where it was dropped only until the user answers.
    setPending({ row, fecha, hora, revert: arg.revert })
  }

  const applyMove = async () => {
    if (!pending) return
    setBusy(true)
    setActionError(null)
    try {
      const updated = await adminService.rescheduleAppointment(
        pending.row.codigo,
        { fecha: pending.fecha, hora: pending.hora },
      )
      setRows((prev) =>
        prev.map((r) => (r.codigo === updated.codigo ? updated : r)),
      )
      setPending(null)
    } catch (err) {
      // 400 horario_invalido, 409 horario_ocupado, 409 transicion_invalida —
      // the backend decides, and the card goes back where it came from so the
      // grid never shows a move that did not happen.
      pending.revert()
      setActionError(
        err instanceof Error ? err.message : 'No se pudo mover la cita.',
      )
      setPending(null)
    } finally {
      setBusy(false)
    }
  }

  const cancelMove = () => {
    pending?.revert()
    setPending(null)
  }

  const handleEventClick = (arg: EventClickArg) => {
    setSelected(arg.event.extendedProps.row as AppointmentSummary)
  }

  const renderEvent = (arg: EventContentArg) => {
    const row = arg.event.extendedProps.row as AppointmentSummary
    return (
      // Sized for the 4.25rem rows set in styles.css — the card has room for
      // the plate and the quote now, which is what the secretary reads off the
      // grid before phoning.
      <div className="px-1 py-0.5 overflow-hidden leading-snug">
        <div className="font-mono font-bold text-xs tracking-wide">
          {row.codigo}
        </div>
        <div className="truncate text-xs font-semibold">{row.customerName}</div>
        <div className="truncate text-[11px] opacity-85">
          {[row.brand, row.vehicleModel].filter(Boolean).join(' ') || '—'}
          {row.licensePlate ? ` · ${row.licensePlate}` : ''}
        </div>
        <div className="truncate text-[11px] opacity-75">
          {formatCop(row.estimatedRepairCostCop)}
        </div>
      </div>
    )
  }

  const openCount = rows.filter((r) => isMovable(r.status)).length

  return (
    // Wider than the other admin pages (max-w-7xl): six day columns need the
    // room, and a booking card narrower than its own code is unreadable.
    <div className="max-w-[1800px] mx-auto">
      <PageHeader
        title="Calendario"
        subtitle={`${openCount} cita(s) abierta(s) esta semana · arrastra una tarjeta para reagendar`}
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

      {(error || actionError) && (
        <div className="mb-4">
          <ErrorState
            message={error ?? actionError ?? ''}
            onRetry={error ? () => void load() : undefined}
          />
        </div>
      )}

      <div className="bg-white rounded-xl border-2 border-brand-navy/10 p-3 relative">
        {loading && (
          <div className="absolute inset-0 bg-white/60 z-10 flex items-start justify-center pt-20">
            <span className="text-brand-navy/60 text-sm font-semibold">
              Cargando…
            </span>
          </div>
        )}

        <FullCalendar
          plugins={[timeGridPlugin, interactionPlugin]}
          initialView="timeGridWeek"
          locale={esLocale}
          // See the module docstring: the grid runs in UTC and is fed workshop
          // wall-clock strings, so it reads the same on any machine.
          timeZone="UTC"
          headerToolbar={{
            left: 'prev,next today',
            center: 'title',
            right: 'timeGridWeek,timeGridDay',
          }}
          allDaySlot={false}
          slotMinTime={`${String(OPEN_HOUR).padStart(2, '0')}:00:00`}
          slotMaxTime={`${String(CLOSE_HOUR).padStart(2, '0')}:00:00`}
          slotDuration="01:00:00"
          hiddenDays={[0]} /* the workshop is closed on Sundays */
          businessHours={{
            daysOfWeek: WORKSHOP_WEEKDAYS,
            startTime: `${String(OPEN_HOUR).padStart(2, '0')}:00`,
            endTime: `${String(CLOSE_HOUR).padStart(2, '0')}:00`,
          }}
          height="auto"
          expandRows
          nowIndicator
          editable
          eventDurationEditable={false}
          eventStartEditable
          events={events}
          eventContent={renderEvent}
          eventClick={handleEventClick}
          eventDrop={handleEventDrop}
          datesSet={handleDatesSet}
        />
      </div>

      <p className="mt-3 text-brand-navy/50 text-xs">
        Horario del taller: {OPEN_HOUR}:00 a {CLOSE_HOUR}:00, lunes a sábado
        (America/Bogota). Las citas canceladas no ocupan un espacio y no se
        muestran aquí.
      </p>

      {/* ── Drop confirm ──────────────────────────────────────────────────── */}
      {pending && (
        <ConfirmDialog
          title="Reagendar cita"
          busy={busy}
          confirmLabel="Reagendar"
          message={
            <>
              La cita <strong>{pending.row.codigo}</strong> de{' '}
              <strong>{pending.row.customerName}</strong> pasará de{' '}
              <strong>{pending.row.scheduledLocal}</strong> a{' '}
              <strong>
                {pending.fecha} {pending.hora}
              </strong>
              .
              <p className="mt-2 text-brand-navy/60 text-sm">
                El cliente conserva el mismo código; no se genera uno nuevo.
              </p>
            </>
          }
          onCancel={cancelMove}
          onConfirm={() => void applyMove()}
        />
      )}

      {/* ── Quick look ────────────────────────────────────────────────────── */}
      {selected && (
        <ConfirmDialog
          title={`Cita ${selected.codigo}`}
          confirmLabel="Cerrar"
          message={
            <div className="space-y-2 text-brand-navy">
              <div className="flex items-center gap-2">
                <StatusBadge status={selected.status} />
                <span className="text-sm">{selected.scheduledLocal}</span>
              </div>
              <p className="font-semibold">{selected.customerName}</p>
              {/* The secretary phones customers to confirm — owner's call. */}
              <a
                href={`tel:${selected.customerPhone}`}
                className="flex items-center gap-1 text-sm text-brand-blue hover:underline"
              >
                <FiPhone className="w-3 h-3" />
                {selected.customerPhone}
              </a>
              <p className="text-sm">
                {[selected.brand, selected.vehicleModel, selected.year]
                  .filter(Boolean)
                  .join(' ') || '—'}
                {selected.licensePlate ? ` · ${selected.licensePlate}` : ''}
              </p>
              <p className="font-display text-xl">
                {formatCop(selected.estimatedRepairCostCop)}
              </p>
            </div>
          }
          onCancel={() => setSelected(null)}
          onConfirm={() => setSelected(null)}
        />
      )}
    </div>
  )
}

export default CalendarPage
