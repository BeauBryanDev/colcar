
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, status
from fastapi.concurrency import run_in_threadpool
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.agent.make_appointment import parse_slot
from app.core.auth import StaffUser
from app.core.config import get_settings
from app.core.exceptions import (
    AppError,
    AppointmentNotFoundError,
    AppointmentUnavailableError,
)
from app.db import mongo, repository
from app.schemas.admin import (
    AppointmentListResponse,
    AppointmentScheduleUpdate,
    AppointmentStatusUpdate,
    AppointmentSummary,
    InspectionDetailResponse,
    InspectionListResponse,
    InspectionSummary,
)
from app.schemas.appointments import AppointmentResponse

logger = logging.getLogger(__name__)

# Dashboard queries over appointments and inspections.

router = APIRouter(tags=["admin"])

# The reschedule route shares parse_slot and `repository.reschedule_appointment`
# with the agent's `reschedule_appointment` tool: same workshop-hours rules and
# active-only filter whether a booking moves from the calendar or from chat.
# What differs is who may ask -- `StaffUser` here, a code+email+plate ownership
# check there.

# Both roles read everything here, contact details included (secretary calls
# customers to confirm bookings), and both may cancel/move a booking -- owner's
# decision, 2026-09-10. What staff may NOT do is touch money or accounts:
# prices and the users collection are admin-only. Prices have no HTTP endpoint
# today (edited in Atlas, re-seeded); when one exists, it must be `AdminUser`.

# Read routes take `StaffUser` (ranked -- admin passes it too); nothing here
# takes `AdminUser`.

class InspectionNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "inspeccion_no_encontrada"
    detail = "La inspeccion no existe."


class InvalidStatusTransitionError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "transicion_invalida"
    detail = "No se puede cambiar el estado de la cita a ese valor."


class InvalidSlotError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "horario_invalido"
    detail = "La fecha u hora no es valida para el taller."


class SlotUnavailableError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "horario_ocupado"
    detail = "Ese horario ya esta ocupado por otra cita activa."


# Which moves are legal. "atendida" and "cancelada" are terminal: a booking
# that was served or cancelled must not quietly go back to `programada`, or
# the history stops meaning anything. Reopening one is a new booking.
_ALLOWED_TRANSITIONS: dict[str, set[str]] = { # states machine
    "programada": {"confirmada", "cancelada"},
    "confirmada": {"atendida", "cancelada"},
    "atendida": set(),
    "cancelada": set(),
}


def _require_mongo() -> None:
    
    if not mongo.is_configured():
        raise AppointmentUnavailableError(log_message="MONGODB_URI is not set")


#  helpers _ wrapper
async def _call(fn, *args, **kwargs):
    try:
        return await run_in_threadpool(fn, *args, **kwargs)
    
    except PyMongoError as exc:
        raise AppointmentUnavailableError(log_message=str(exc)) from exc


# Colombia UTC -5 in Bogota time zone.
def _utc_window(
    date_from: datetime | None, 
    date_to: datetime | None
) -> tuple[datetime | None, datetime | None]:
    """Interpret a naive date/datetime as **workshop-local**, and return UTC.

    Slots are stored in UTC (see Appointments). Someone filtering "bookings on
    the 12th" means the workshop's 12th in America/Bogota, not UTC's -- and in
    a UTC-5 zone those differ by five hours at each end, which is a whole
    evening of bookings landing on the wrong day.

    A bare date (midnight) as `date_to` is widened to the end of that day, so
    `?date_to=2026-09-12` includes the 12th rather than excluding all of it.
    """
    tz = ZoneInfo(get_settings().workshop_timezone)

    def to_utc(value: datetime | None, *, end_of_day: bool) -> datetime | None:
        if value is None:
            return None
        
        if value.tzinfo is None:
            
            if end_of_day and value.time() == time(0, 0):
                
                value = datetime.combine(value.date(), time(0, 0)) + timedelta(
                    days=1, microseconds=-1
                )
            value = value.replace(tzinfo=tz)
            
        return value.astimezone(ZoneInfo("UTC"))

    return to_utc(date_from, end_of_day=False), to_utc(date_to, end_of_day=True)


#  appointments

# GET   /api/admin/appointments   date range / status / code
@router.get("/admin/appointments", response_model=AppointmentListResponse)
async def list_appointments(
    _: StaffUser,
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    codigo: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> AppointmentListResponse:
    _require_mongo()
    start, end = _utc_window(date_from, date_to)

    docs = await _call(
        repository.query_appointments,
        date_from=start,
        date_to=end,
        status=status_filter,
        codigo=codigo,
        limit=limit,
    )
    total = await _call(
        repository.count_appointments,
        date_from=start,
        date_to=end,
        status=status_filter,
        codigo=codigo,
    )
    return AppointmentListResponse(
        appointments=[AppointmentSummary.from_document(d) for d in docs], 
        total=total
    )


# GET   /api/admin/appointments/{codigo} -> one booking, with its snapshot
@router.get("/admin/appointments/{codigo}", response_model=AppointmentResponse)
async def get_appointment(codigo: str, _: StaffUser) -> AppointmentResponse:
    """The full booking, including `inspection_snapshot` -- what the customer
    was quoted at the moment they booked."""
    _require_mongo()
    doc = await _call(repository.get_appointment, codigo)
    
    if doc is None:
        raise AppointmentNotFoundError(log_message=f"appointment {codigo!r} not found")
    
    return AppointmentResponse.from_document(doc)


# PATCH /api/admin/appointments/{codigo} -> one booking, with its snapshot
@router.patch("/admin/appointments/{codigo}", response_model=AppointmentSummary)
async def update_appointment_status(
    codigo: str,
    payload: AppointmentStatusUpdate,
    actor: StaffUser
) -> AppointmentSummary:
    """`programada → confirmada → atendida`, with `cancelada` reachable from
    either open state. Staff may cancel; that is the secretary's job."""
    _require_mongo()

    current = await _call(repository.get_appointment, codigo)
    
    if current is None:
        raise AppointmentNotFoundError(log_message=f"appointment {codigo!r} not found")

    if payload.status != current.status:
        
        allowed = _ALLOWED_TRANSITIONS.get(current.status, set())
        
        if payload.status not in allowed:
            
            raise InvalidStatusTransitionError(
                detail=(
                    f"Una cita en estado '{current.status}' no puede pasar a "
                    f"'{payload.status}'."
                ),
                log_message=(
                    f"{current.codigo}: {current.status} -> {payload.status} "
                    f"not allowed"
                ),
            )

    updated = await _call(
        repository.set_appointment_status,
        current.id,
        payload.status,
        notes=payload.notes,
    )
    if updated is None:
        
        raise AppointmentNotFoundError(log_message=f"{codigo!r} vanished mid-update")

    logger.info(
        "%s (%s) moved appointment %s: %s -> %s",
        actor.username,
        actor.role.value,
        updated.codigo,
        current.status,
        updated.status,
    )
    return AppointmentSummary.from_document(updated)


# PATCH /api/admin/appointments/{codigo}/schedule   move it to another slot
@router.patch(
    "/admin/appointments/{codigo}/schedule", 
    response_model=AppointmentSummary
)
async def update_appointment_schedule(
    codigo: str, 
    payload: AppointmentScheduleUpdate, 
    actor: StaffUser
) -> AppointmentSummary:
    """Move an ACTIVE booking to a different slot -- dragging a card on the
    calendar.

    Validated through the agent tool's own `parse_slot`, so a past date, a
    Sunday or an out-of-hours time is refused here exactly as it would be in
    chat. Terminal bookings do not move: reopening one is a new booking, the
    same rule the status transition table enforces.
    """
    _require_mongo()

    slot = parse_slot(payload.fecha, payload.hora)
    
    if isinstance(slot, dict):
        # parse_slot's rejection dict is shaped for the agent's tool-result
        # channel; over HTTP the reason belongs in a 400.
        raise InvalidSlotError(
            detail=slot.get("error", 
                            InvalidSlotError.detail
                            ),
            log_message=f"{codigo!r}: rejected slot {payload.fecha} {payload.hora}",
        )
        
    scheduled_utc, scheduled_local = slot

    current = await _call(repository.get_appointment, codigo)
    
    if current is None:
        
        raise AppointmentNotFoundError(log_message=f"appointment {codigo!r} not found")

    # uniq_active_slot is the real guard against double-booking, and it
    # raises DuplicateKeyError , which is a PyMongoError, so this must NOT go
    # through _call() or an occupied hour would be reported as a 503 outage.
    try:
        updated = await run_in_threadpool(
            repository.reschedule_appointment,
            current.id,
            scheduled_utc,
            scheduled_local,
        )
    except DuplicateKeyError as exc:
        raise SlotUnavailableError(
            log_message=f"{codigo!r}: slot {scheduled_local} already taken ({exc})"
        ) from exc
        
    except PyMongoError as exc:
        raise AppointmentUnavailableError(log_message=str(exc)) from exc

    if updated is None:
        # The document exists -> read above^^, so the filter fell through on
        # status: it is already cancelled or attended.
        raise InvalidStatusTransitionError(
            detail=(
                f"Una cita en estado '{current.status}' no se puede reagendar."
            ),
            log_message=f"{current.codigo}: reschedule refused, status {current.status}",
        )

    logger.info(
        "%s (%s) rescheduled appointment %s: %s -> %s",
        actor.username,
        actor.role.value,
        updated.codigo,
        current.scheduled_local,
        updated.scheduled_local,
    )
    
    return AppointmentSummary.from_document(updated)


#  inspections

# GET   /api/admin/inspections -> date / brand / RTM verdict
@router.get("/admin/inspections", 
            response_model=InspectionListResponse)
async def list_inspections(
    _: StaffUser,  # fixed::only for admin and staff. we not not handle regualr users yet.
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    brand: str | None = Query(default=None),
    rechazo_rtm_probable: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> InspectionListResponse:
    _require_mongo()
    
    start, end = _utc_window(date_from, date_to)

    docs = await _call(
        repository.query_inspections,
        date_from=start,
        date_to=end,
        brand=brand,
        rechazo_rtm_probable=rechazo_rtm_probable,
        limit=limit,
    )
    total = await _call(
        repository.count_inspections,
        date_from=start,
        date_to=end,
        brand=brand,
        rechazo_rtm_probable=rechazo_rtm_probable,
    )
    return InspectionListResponse(
        inspections=[InspectionSummary.from_document(d) for d in docs], total=total
    )


# GET   /api/admin/inspections/{id} -> the whole stored record
@router.get("/admin/inspections/{inspection_id}", 
            response_model=InspectionDetailResponse)
async def get_inspection(inspection_id: str, _: StaffUser) -> InspectionDetailResponse:
    _require_mongo()
    
    doc = await _call(repository.get_inspection, inspection_id)
    
    if doc is None:
        
        raise InspectionNotFoundError(
            log_message=f"inspection {inspection_id!r} not found"
        )
        
    return InspectionDetailResponse.from_document(doc)
