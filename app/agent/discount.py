
from __future__ import annotations
 
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any
 
from pymongo.errors import DuplicateKeyError, PyMongoError
 
from app.core.exceptions import AppointmentUnavailableError
from app.db import mongo, repository
 
logger = logging.getLogger(__name__)
 
DISCOUNT_PERCENT = 10
_DISCOUNT_MULTIPLIER = 1 - DISCOUNT_PERCENT / 100  # 0.9
 
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PLATE_RE = re.compile(r"^[A-Z]{3}\d{3}$")
 
# Two tools for the new-user discount, kept separate on purpose so the agent's
# ReAct trace shows the observation (eligibility) and the action (grant) as
# distinct steps. 
 
def _normalise_plate(raw: str) -> str:
    return re.sub(r"[\s-]", "", raw or "").upper()
 
 
def _customer_key(email: str, plate: str) -> str:
    """Stable one-per-customer key. Plate is the harder-to-fake anchor; email
    rides along so either match blocks a re-grant."""
    return f"{plate}|{email.strip().lower()}"
 
 
# eligibility lookup 
# agent must  check first if user is elgible for a discount it is read-only
def query_email_and_plate_number(
    tool_input: dict[str, Any], 
    context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return whether the customer is new (no prior appointment on email/plate)."""
    email = str(tool_input.get("email") or "").strip()
    plate = _normalise_plate(str(tool_input.get("placa") or ""))
# the LLM decides WHEN to offer the discount if the user is new (first time buyer
# user complaints to much and bargains), but never WHETHER the user is eligible or 
# HOW MUCH. Eligibility is a database fact re-checked server-side inside grant_discount; 
# the 10% ceiling ishard-coded here.  
    if not _EMAIL_RE.match(email):
        return {
            "es_usuario_nuevo": False,
            "instrucciones": (
                "No hay un correo valido para verificar. Pideselo al usuario "
                "antes de ofrecer cualquier descuento. No ofrezcas el descuento "
                "sin verificar."
            ),
        }
        
    if not _PLATE_RE.match(plate):
        return {
            "es_usuario_nuevo": False,
            "instrucciones": (
                "No hay una placa valida (formato ABC123) para verificar. "
                "Pidesela al usuario. No ofrezcas el descuento sin verificar."
            ),
        }
 
    if not mongo.is_configured():
        raise AppointmentUnavailableError(log_message="MONGODB_URI is not set")
 
    try:
        seen_before = repository.find_appointment_by_email_or_plate(
            email, plate, exclude_inspection_id=(context or {}).get("inspection_id")
        )

    except PyMongoError as exc:
        raise AppointmentUnavailableError(
            log_message=f"eligibility lookup failed: {exc}"
        ) from exc
 
    is_new = not seen_before
    logger.info("query_email_and_plate_number: %s / %s -> new=%s",
                email, plate, is_new)
 
    if is_new:
        return {
            "es_usuario_nuevo": True,
            "instrucciones": (
                "El usuario es nuevo y califica para el descuento de "
                f"{DISCOUNT_PERCENT}% por primera cita. Puedes ofrecerselo como "
                "gesto de bienvenida SI ya se quejo del precio o pidio rebaja. "
                "Si acepta, llama grant_discount. No apliques el descuento tu "
                "mismo en el texto: espera el resultado de la tool."
            ),
        }
    return {
        "es_usuario_nuevo": False,
        "instrucciones": (
            "El usuario NO es nuevo (ya tiene registros previos), asi que no "
            "califica para el descuento de bienvenida. No se lo ofrezcas. "
            "Puedes explicarle con amabilidad que el descuento es solo para "
            "clientes nuevos."
        ),
    }
 
 
#  Grant Discount (action step, gated)
 
def grant_discount(
    tool_input: dict[str, Any], 
    context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Apply the new-user discount. Re-verifies eligibility server-side; never
    trusts a flag the model passes in."""
    ctx = context or {}
    email = str(tool_input.get("email") or "").strip()
    plate = _normalise_plate(str(tool_input.get("placa") or ""))
 
    if not _EMAIL_RE.match(email) or not _PLATE_RE.match(plate):
        
        return {
            "descuento_aplicado": False,
            "instrucciones": (
                "Falta un correo o placa validos. No se aplico ningun "
                "descuento. Pide los datos y vuelve a verificar con "
                "query_email_and_plate_number."
            ),
        }
 
    if not mongo.is_configured():
        raise AppointmentUnavailableError(log_message="MONGODB_URI is not set")
 
    # Gate: re-check eligibility here. The model does not get to assert it.
    try:
        seen_before = repository.find_appointment_by_email_or_plate(
            email, plate, exclude_inspection_id=ctx.get("inspection_id")
        )

    except PyMongoError as exc:
        raise AppointmentUnavailableError(
            log_message=f"grant eligibility recheck failed: {exc}"
        ) from exc
 
    if seen_before:
        return {
            "descuento_aplicado": False,
            "instrucciones": (
                "El usuario no es nuevo: no se aplico el descuento. Explicale "
                "que la promocion es solo para clientes nuevos."
            ),
        }
 
    total = ctx.get("total_cop")
    
    if not isinstance(total, (int, float)) or total <= 0:
        return {
            "descuento_aplicado": False,
            "instrucciones": (
                "No hay un total de cotizacion en la sesion para aplicar el "
                "descuento. Primero cotiza la inspeccion con query_pricing_batch."
            ),
        }
 
    new_total = round(total * _DISCOUNT_MULTIPLIER)
    discount_id = uuid.uuid4().hex[:5].upper()

    # Minted before the insert so the number is on the stored record. A mint
    # whose grant then fails leaves a gap in the sequence, which is harmless;
    # two customers sharing a ticket number at the counter would not be.
    try:
        ticket_number = repository.next_ticket_number()
    except PyMongoError as exc:
        raise AppointmentUnavailableError(
            log_message=f"ticket number mint failed: {exc}"
        ) from exc

    record = {
        "discount_id": discount_id,
        "ticket_number": ticket_number,
        "customer_key": _customer_key(email, plate),
        "email": email,
        "license_plate": plate,
        "inspection_id": ctx.get("inspection_id"),
        "percent": DISCOUNT_PERCENT,
        "original_total_cop": int(total),
        "new_total_cop": new_total,
        "created_at": datetime.now(timezone.utc),
    }
 
    try:
        repository.record_discount(record)
        
    except DuplicateKeyError:
        # This customer already has a discount on file.
        existing = repository.get_discount_by_customer_key(_customer_key(email, plate))
        
        return {
            "descuento_aplicado": False,
            "ya_tenia_descuento": True,
            "codigo_descuento": existing.get("discount_id") if existing else None,
            "numero_ticket": existing.get("ticket_number") if existing else None,
            "instrucciones": (
                "Este usuario ya recibio un descuento antes. No se aplico uno "
                "nuevo. Si ya tiene un codigo y un numero de ticket, puedes "
                "recordarselos; no generes otros."
            ),
        }
        
    except PyMongoError as exc:
        raise AppointmentUnavailableError(
            log_message=f"discount insert failed: {exc}"
        ) from exc
 
    # Write it onto any booking already made for this inspection. A booking
    # made LATER picks the discount up in make_appointment, so either order
    # ends with the customer paying the discounted figure.
    citas: list[str] = []
    try:
        updated = repository.apply_discount_to_appointments(
            
            str(ctx.get("inspection_id") or ""),
            discount_id, 
            DISCOUNT_PERCENT,
            ticket_number=ticket_number,
        )
        
        citas = [d.codigo for d in updated]
        
    except PyMongoError as exc:
        # The discount is already on file and the code is valid; a failed
        # write-back must not lose it. The workshop applies it by code.
        logger.error("discount %s write-back failed: %s", discount_id, exc)

    logger.info(
        "grant_discount: %s%% for %s -> %s COP (code %s, ticket %s)",
        DISCOUNT_PERCENT,
        _customer_key(email, plate),
        new_total,
        discount_id,
        ticket_number,
    )
    
    return {
        "descuento_aplicado": True,
        "porcentaje": DISCOUNT_PERCENT,
        "codigo_descuento": discount_id,
        "numero_ticket": ticket_number,
        "total_original_cop": int(total),
        "total_con_descuento_cop": new_total,
        "citas_actualizadas": citas,
        "instrucciones": (
            "El descuento quedo registrado. Entrega al usuario su NUMERO DE "
            f"TICKET ({ticket_number}) y el codigo ({discount_id}) tal cual, "
            "junto con el nuevo total. Explicale que debe presentar el numero "
            "de ticket el dia de la cita en el taller. El descuento es sobre "
            "el estimado, sujeto a revision fisica por humano en taller. "
        ),
    }
 