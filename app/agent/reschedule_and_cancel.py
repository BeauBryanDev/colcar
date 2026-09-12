
from __future__ import annotations
 
import logging
import re
from typing import Any
 
from pymongo.errors import DuplicateKeyError, PyMongoError
 
from app.agent.make_appointment import parse_slot
from app.core.exceptions import AppointmentUnavailableError
from app.db import mongo, repository
 
logger = logging.getLogger(__name__)
 
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PLATE_RE = re.compile(r"^[A-Z]{3}\d{3}$")
 
# Two agent tools for when a customer comes back to chat to change or cancel a
# booking they already made. Both share the same ownership gate: a bare
# appointment code proves nothing on its own booking code.
 
def _reject(motivo: str,
            **extra: Any
            ) -> dict[str, Any]:
    
    return {
        "error": motivo,
        "recuperable": True,
        "instrucciones": (
            "La operacion NO se realizo. Explica el motivo al usuario con tus "
            "palabras y pidele el dato que falta o corrija. No inventes un "
            "resultado."
        ),
        **extra,
    }
 
 
# Verify helper


def _verify(tool_input: dict[str, Any]) -> Any:
    """Shared owner check for both tools. 
    Returns the appointment or a
    rejection dict."""
    codigo = str(tool_input.get("codigo_cita") or "").strip()
    email = str(tool_input.get("email") or "").strip()
    plate = re.sub(r"[\s-]", "", str(tool_input.get("placa") or "")).upper()
 
    if not codigo:
        return _reject("Falta el codigo de la cita.", campo="codigo_cita")
    
    if not _EMAIL_RE.match(email):
        return _reject("Falta un correo electronico valido.", campo="email")
    
    if not _PLATE_RE.match(plate):
        return _reject(
            "Falta una placa valida, formato ABC123.", campo="placa"
        )
 
    if not mongo.is_configured():
        raise AppointmentUnavailableError(log_message="MONGODB_URI is not set")
 
    try:
        appt = repository.verify_appointment_owner(codigo, email, plate)
        
    except PyMongoError as exc:
        raise AppointmentUnavailableError(
            log_message=f"owner verification failed: {exc}"
        ) from exc
 
    if appt is None:
        return _reject(
            "El codigo de cita, el correo y la placa no coinciden con ninguna "
            "cita registrada. Pide al usuario que revise los tres datos; no "
            "confirmes ni asumas cual es el error.",
            campo="verificacion",
        )
    return appt


# Agent tool 4 re-schedule an existing appointment


def reschedule_appointment(
    tool_input: dict[str, Any], 
    context: dict[str, Any] | None = None
) -> dict[str, Any]:
    
    appt = _verify(tool_input)
    
    if isinstance(appt, dict):
        return appt
 
    slot = parse_slot(str(tool_input.get("fecha") or ""), 
                      str(tool_input.get("hora") or ""))
    
    if isinstance(slot, dict):
        return slot
    
    scheduled_utc, scheduled_local = slot
 
    try:
        updated = repository.reschedule_appointment(appt.codigo, 
                                                    scheduled_utc, 
                                                    scheduled_local)
        
    except DuplicateKeyError:
        
        return _reject(
            "Ese horario ya esta ocupado por otra cita activa. Pide al "
            "usuario otra fecha u hora.",
            campo="fecha_hora",
            slot_ocupado=True,
        )
        
    except PyMongoError as exc:
        
        raise AppointmentUnavailableError(
            log_message=f"reschedule failed: {exc}"
        ) from exc
 
    if updated is None:
        
        return _reject(
            "La cita ya no esta activa (cancelada o atendida) y no se puede "
            "reagendar."
        )
 
    logger.info("Appointment %s rescheduled to %s", 
                appt.codigo, scheduled_local)
    
    return {
        "reagendada": True,
        "codigo": updated.codigo,
        "nueva_fecha_hora_local": updated.scheduled_local,
        "instrucciones": (
            "La cita quedo reagendada. Confirma al usuario el mismo codigo "
            f"({updated.codigo}) y la nueva fecha y hora. No generes un "
            "codigo nuevo."
        ),
    }
 
 
# Clancel an Appointment by agent


def cancel_appointment(
    tool_input: dict[str, Any], 
    context: dict[str, Any] | None = None
) -> dict[str, Any]:
    
    appt = _verify(tool_input)
    
    if isinstance(appt, dict):
        return appt
 
    if appt.status in ("cancelada", "atendida"):
        return _reject(
            f"Esta cita ya esta en estado '{appt.status}' y no se puede "
            "cancelar de nuevo."
        )
 
    try:
        updated = repository.set_appointment_status(appt.codigo, "cancelada")
        
    except PyMongoError as exc:
        raise AppointmentUnavailableError(
            log_message=f"cancel failed: {exc}"
        ) from exc
 
    if updated is None:
        return _reject("No se encontro la cita al intentar cancelarla.")
 
    logger.info("Appointment %s cancelled by customer request", 
                appt.codigo)
    
    return {
        "cancelada": True,
        "codigo": updated.codigo,
        "instrucciones": (
            "La cita quedo cancelada. Confirmalo al usuario. Si quiere "
            "agendar una nueva, usa make_appointment normalmente."
        ),
    }
    
