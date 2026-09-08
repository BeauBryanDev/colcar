
from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.common import ApiResponse

# Wire shapes for appointments. camelCase out via `ApiResponse`.

# Bookings are created by the agent tool, not by a POST: the chat flow collects
# the customer data and the explicit confirmation. These endpoints let the SPA
# (and the workshop) read a booking back by its code.

class CustomerInfo(ApiResponse):
    name: str
    phone: str
    email: str


class CarInfoResponse(ApiResponse):
    brand: str | None = None
    model: str | None = None
    year: int | str | None = None
    color: str | None = None
    license_plate: str | None = None
    specs: dict[str, Any] | None = None


class AppointmentResponse(ApiResponse):
    appointment_id: str
    codigo: str
    inspection_id: str
    status: str
    customer: CustomerInfo
    car_info: CarInfoResponse
    scheduled_for: str
    scheduled_local: str
    timezone: str
    estimated_repair_cost_cop: int | None = None
    inspection_snapshot: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
    created_at: str

    @classmethod
    def from_document(cls, doc: Any) -> "AppointmentResponse":
        
        return cls(
            appointment_id=doc.id,
            codigo=doc.codigo,
            inspection_id=doc.inspection_id,
            status=doc.status,
            customer=CustomerInfo(**doc.customer.model_dump()),
            car_info=CarInfoResponse(**doc.car_info.model_dump()),
            scheduled_for=doc.scheduled_for.isoformat(),
            scheduled_local=doc.scheduled_local,
            timezone=doc.timezone,
            estimated_repair_cost_cop=doc.estimated_repair_cost_cop,
            inspection_snapshot=_jsonable(doc.inspection_snapshot),
            notes=doc.notes,
            created_at=doc.created_at.isoformat(),
        )


class AppointmentListResponse(ApiResponse):
    inspection_id: str
    appointments: list[AppointmentResponse] = Field(default_factory=list)


def _jsonable(value: Any) -> Any:
    """datetimes inside the snapshot -> ISO strings."""
    from datetime import datetime

    if isinstance(value, datetime):
        return value.isoformat()
    
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    
    return value
