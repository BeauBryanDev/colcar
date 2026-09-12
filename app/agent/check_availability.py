
from __future__ import annotations
 
import logging
from typing import Any
 
from app.agent.make_appointment import parse_slot
from app.core.config import get_settings
from app.core.exceptions import AppointmentUnavailableError
from app.db import mongo, repository
 
logger = logging.getLogger(__name__)
 
# Availability check the agent calls BEFORE make_appointment, so it can tell the
# user a slot is taken without attempting (and failing) the booking.

def check_availability(
    tool_input: dict[str, Any], 
    context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return whether a date+time is free. 
    Does not book anything."""
    slot = parse_slot(str(tool_input.get("fecha") or ""), 
                      str(tool_input.get("hora") or "")
                      )
    # parse_slot already returns a user-facing rejection for bad/past/off-hours
    # slots; pass it straight through so the agent explains the real reason.
    if isinstance(slot, dict):
        return slot
    
    scheduled_utc, scheduled_local = slot
 
    if not mongo.is_configured():
        raise AppointmentUnavailableError(log_message="MONGODB_URI is not set")
 
    available = repository.slot_is_available(scheduled_utc)
    logger.info("check_availability: %s -> %s", scheduled_local, available)
 
    if available:
        return {
            "disponible": True,
            "fecha_hora_local": scheduled_local,
            "instrucciones": (
                "El horario esta libre. Si el usuario quiere agendar, continua "
                "con el flujo normal de make_appointment. No confirmes la cita "
                "todavia: primero reune los datos y pide confirmacion explicita."
            ),
          }
# This is the friendly, conversational half the real guarantee against
# double-booking lives in the uniq_active_slot index and make_appointment's
# DuplicateKeyError handling; this tool just lets the agent check first and give
# a clean answer.
        
    return {
        "disponible": False,
        "fecha_hora_local": scheduled_local,
        "instrucciones": (
            "Ese horario ya esta ocupado (el taller atiende un solo vehiculo a "
            "la vez). Dile al usuario que no hay cupo en esa fecha y hora, y "
            "pidele otra. No llames make_appointment para ese horario."
        ),
    }