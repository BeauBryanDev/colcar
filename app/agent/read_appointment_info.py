
from __future__ import annotations

import logging
from typing import Any

from app.agent.reschedule_and_cancel import _verify

logger = logging.getLogger(__name__)

# Agent tool: read back an existing booking for a customer who forgot its
# date. Same code + email + plate gate as reschedule/cancel, by reusing
# _verify()  a second verification path is how one gate ends up weaker.
 
_ESTADO_NOTA = {
    "programada": "La cita esta agendada y pendiente de confirmacion del taller.",
    "confirmada": "La cita esta confirmada por el taller.",
    "cancelada": "La cita fue cancelada; ya no reserva ese horario.",
    "atendida": "La cita ya fue atendida en el taller.",
}  # AppointmentStatus.name -> agent tool help


def read_appointment(
    tool_input: dict[str, Any],
    context: dict[str, Any] | None = None
) -> dict[str, Any]:

    appt = _verify(tool_input)

    if isinstance(appt, dict):
        return appt

    logger.info("Appointment %s read by verified owner", appt.codigo)

    car = appt.car_info
    discount = appt.discount

    return {
        "encontrada": True,
        "codigo": appt.codigo,
        "estado": appt.status,
        "nota_estado": _ESTADO_NOTA.get(appt.status, ""),
        # The workshop's own string, not an instant re-derived by the model.
        "fecha_hora_local": appt.scheduled_local,
        "zona_horaria": appt.timezone,
        "cliente": appt.customer.name,
        "vehiculo": {
            "marca": car.brand,
            "modelo": car.model,
            "anio": car.year,
            "placa": car.license_plate,
        },
        # Already net of any discount -- what the customer owes.
        "costo_estimado_cop": appt.estimated_repair_cost_cop,
        "descuento": (
            {
                "porcentaje": discount.percent,
                "total_sin_descuento_cop": discount.original_cost_cop,
                "numero_ticket": discount.ticket_number,
            }
            if discount
            else None
        ),
        "instrucciones": (
            "Estos son los datos guardados de la cita. Responde con ellos tal "
            "cual: usa fecha_hora_local sin convertirla, y costo_estimado_cop "
            "como el valor a pagar (ya incluye cualquier descuento; no lo "
            "recalcules). Si el estado es cancelada o atendida, dilo con "
            "claridad y ofrece agendar una nueva si el usuario lo desea."
        ),
    }
