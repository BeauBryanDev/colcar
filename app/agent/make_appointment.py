
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.config import get_settings
from app.core.exceptions import AppointmentUnavailableError, CarSpecsUnavailableError
from app.db import mongo, repository
from app.models.appointment import (
    AppointmentDocument,
    CarInfo,
    Customer,
    Discount,
)
from app.rag.car_specs import get_car_specs

logger = logging.getLogger(__name__)

#  Make and Appointment tool when user wants to book something with the agent

_DAY_NAMES_ES = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[\d\s().-]{7,20}$")
# Colombian car plate: three letters, three digits (ABC123). Motorcycles
# (ABC12D) are not handled yet and are rejected like any other bad plate.
_PLATE_RE = re.compile(r"^[A-Z]{3}\d{3}$")


def _reject(motivo: str, **extra: Any) -> dict[str, Any]:
    """A recoverable, user-facing rejection. Not an exception on purpose."""
    return {
        "error": motivo,
        "recuperable": True,
        "cita_creada": False,
        "instrucciones": (
            "La cita NO se creo. Explica el motivo al usuario con tus palabras "
            "y pidele el dato que falta o una nueva fecha y hora. No inventes "
            "un codigo de cita."
        ),
        **extra,
    }


#  validation

def parse_slot(fecha: str, hora: str) -> tuple[datetime, str] | dict[str, Any]:
    """Validate a local slot; return (utc_datetime, local_label) or a rejection.

    Rules from settings: workshop timezone, open/close hours, working days,
    and the slot must be in the future.
    """
    s = get_settings()
    tz = ZoneInfo(s.workshop_timezone)
    
    try:
        local = datetime.strptime(f"{fecha.strip()} {hora.strip()}", "%Y-%m-%d %H:%M")
        
    except ValueError:
        return _reject(
            "Fecha u hora invalida. Se necesita fecha AAAA-MM-DD y hora HH:MM "
            "(24 horas), por ejemplo 2026-09-15 y 10:30.",
            campo="fecha_hora",
        )
        
    local = local.replace(tzinfo=tz)
    now_local = datetime.now(tz)

    if local <= now_local:
        
        return _reject(
            f"La fecha y hora ya pasaron (ahora es {now_local:%Y-%m-%d %H:%M} "
            f"en {s.workshop_timezone}). Pide una fecha futura.",
            campo="fecha_hora",
        )
    if local.weekday() not in s.workshop_days:
        
        dias = ", ".join(_DAY_NAMES_ES[d] for d in s.workshop_days)
        
        return _reject(
            f"El taller no atiende los {_DAY_NAMES_ES[local.weekday()]}. "
            f"Dias de atencion: {dias}.",
            campo="fecha",
        )
    if not (s.workshop_open_hour <= local.hour < s.workshop_close_hour):
        
        return _reject(
            f"Hora fuera del horario de atencion "
            f"({s.workshop_open_hour:02d}:00 a {s.workshop_close_hour:02d}:00, "
            f"hora de Colombia). Pide otra hora.",
            campo="hora",
        )
    label = f"{local:%A %Y-%m-%d %H:%M}"
    label = label.replace(local.strftime("%A"), _DAY_NAMES_ES[local.weekday()])
    
    return local.astimezone(timezone.utc), label


def parse_customer(tool_input: dict[str, Any]) -> Customer | dict[str, Any]:
    
    name = str(tool_input.get("nombre_cliente") or "").strip()
    phone = str(tool_input.get("telefono") or "").strip()
    email = str(tool_input.get("email") or "").strip()
    
    if len(name) < 2:
        return _reject("Falta el nombre del cliente.", campo="nombre_cliente")
    
    if not _PHONE_RE.match(phone):
        return _reject("Falta un telefono de contacto valido.", campo="telefono")
    
    if not _EMAIL_RE.match(email):
        return _reject("Falta un correo electronico valido.", campo="email")
    
    return Customer(name=name, phone=phone, email=email)


def parse_plate(tool_input: dict[str, Any]) -> str | dict[str, Any]:
    """Required to book. Customer-supplied like the phone, so it is a tool
    argument; normalised to the stored form (abc-123 -> ABC123)."""
    raw = str(tool_input.get("placa") or "")
    plate = re.sub(r"[\s-]", "", raw).upper()
    
    if not plate:
        return _reject("Falta la placa del vehiculo.", campo="placa")
    
    if not _PLATE_RE.match(plate):
        
        return _reject(
            f"La placa '{raw.strip()}' no es valida. Debe tener el formato de "
            "placa de carro colombiana: tres letras y tres numeros, por "
            "ejemplo ABC123.",
            campo="placa",
        )
        
    return plate


#  tool

def make_appointment(
    tool_input: dict[str, Any], 
    context: dict[str, Any] | None = None
) -> dict[str, Any]:
    
    ctx = context or {}

    if not tool_input.get("confirmado", False):
        return _reject(
            "El usuario todavia no ha confirmado explicitamente que quiere "
            "agendar. Preguntale y vuelve a llamar con confirmado=true.",
            campo="confirmado",
        )

    inspection_id = ctx.get("inspection_id")
    
    if not inspection_id:
        return _reject(
            "No hay una inspeccion asociada a esta conversacion; no es posible "
            "agendar sin inspeccion.",
            campo="inspection_id",
        )

    customer = parse_customer(tool_input)
    if isinstance(customer, dict):
        return customer

    plate = parse_plate(tool_input)
    if isinstance(plate, dict):
        return plate

    slot = parse_slot(str(tool_input.get("fecha") or ""),
                      str(tool_input.get("hora") or "")
                      )
    
    if isinstance(slot, dict):
        return slot
    
    scheduled_utc, scheduled_local = slot

    if not mongo.is_configured():
        raise AppointmentUnavailableError(log_message="MONGODB_URI is not set")

    #  the inspection: stored record first, session facts as fallback
    try:
        stored = repository.get_inspection(inspection_id)
        
    except PyMongoError as exc:
        
        raise AppointmentUnavailableError(
            log_message=f"inspection read failed: {exc}"
        ) from exc

    if stored is not None:
        
        snapshot = stored.snapshot()
        total = stored.total_cop
        vehicle = stored.vehicle_info
        
    else:
        # Persisted record missing (persist step failed, or booking before the
        # run finished). Book anyway from the session's facts; never from the
        # model's memory.
        snapshot = {
            "inspection_id": inspection_id,
            "total_cop": ctx.get("total_cop"),
            "rechazo_rtm_probable": ctx.get("rechazo_rtm_probable"),
            "defects": [],
            "nota": "inspeccion no persistida al momento de agendar",
        }
        total = ctx.get("total_cop")
        vehicle = {k: ctx.get(k) for k in ("brand", "model", "year", "color", "license_plate")}

    #  engine sheet, best effort
    specs: dict[str, Any] | None = None
    if vehicle.get("brand"):
        
        try:
            found = get_car_specs(vehicle["brand"],
                                  vehicle.get("model"),
                                  vehicle.get("year")
                                  )
            
            specs = found[0] if found else None
            
        except CarSpecsUnavailableError as exc:
            logger.info("Appointment: car specs unavailable (%s)", 
                        exc.log_message)

    car_info = CarInfo(
        brand=vehicle.get("brand"),
        model=vehicle.get("model"),
        year=vehicle.get("year"),
        color=vehicle.get("color"),
        license_plate=plate,
        specs=specs,
    )

    #  a discount granted before the booking applies to it
    discount: Discount | None = None
    
    if total:
        granted = repository.get_discount_for_inspection(inspection_id)
        
        if granted:
            percent = int(granted.get("percent") or 0)
            
            if percent:
                discount = Discount(
                    code=granted["discount_id"],
                    percent=percent,
                    original_cost_cop=int(total),
                    ticket_number=granted.get("ticket_number"),
                )
                # Stored cost is always what the customer OWES.
                total = round(total * (1 - percent / 100))

    #  idempotent write
    s = get_settings()
    try:
        existing = repository.find_appointment_for_slot(inspection_id, 
                                                        scheduled_utc)
        if existing is not None:
            return {
                **existing.to_tool_result(),
                "cita_creada": False,
                "ya_existia": True,
                "instrucciones": (
                    "Ya existia una cita para esta inspeccion en esa fecha y "
                    "hora. Entrega al usuario el mismo codigo; no crees otra."
                ),
            }
        doc = AppointmentDocument(
            inspection_id=inspection_id,
            customer=customer,
            car_info=car_info,
            scheduled_for=scheduled_utc,
            scheduled_local=scheduled_local,
            timezone=s.workshop_timezone,
            estimated_repair_cost_cop=total,
            discount=discount,
            inspection_snapshot=snapshot,
            notes=(str(tool_input.get("notas") or "").strip() or None),
        )
        created = repository.create_appointment(doc)
    
    # Two distinct unique indexes can fire here:
    except DuplicateKeyError as exc:
        
        #   uniq_inspection_slot -> this same inspection already booked this
        #     slot (idempotent retry): return the existing booking.
        if "uniq_active_slot" in str(exc):
        #   uniq_active_slot -> a DIFFERENT inspection already holds this slot:
        #     reject so the agent offers another time.
            return _reject(
                "Ese horario acaba de ser ocupado por otra reserva. El taller "
                "atiende un solo vehiculo a la vez; pide al usuario otra fecha "
                "u hora.",
                campo="fecha_hora",
                slot_ocupado=True,
            )
        existing = repository.find_appointment_for_slot(inspection_id, 
                                                        scheduled_utc)
        if existing is None:
            raise AppointmentUnavailableError(log_message="slot duplicate without a row")
        
        return {**existing.to_tool_result(), "cita_creada": False, "ya_existia": True}
        
    except PyMongoError as exc:
        raise AppointmentUnavailableError(
            log_message=f"appointment insert failed: {exc}"
        ) from exc

    logger.info(
        "Appointment %s (%s) booked for inspection %s at %s",
        created.codigo, 
        created.id, 
        inspection_id, 
        scheduled_local,
    )
    
    return {
        **created.to_tool_result(),
        "cita_creada": True,
        "instrucciones": (
            "La cita quedo registrada. Entrega al usuario el CODIGO tal cual "
            f"({created.codigo}), la fecha y hora local, y recuerdale que el "
            "costo es un estimado sujeto a revision en el taller. No inventes "
            "direccion ni telefono del taller."
        ),
    }
