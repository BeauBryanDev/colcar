
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

AppointmentStatus = Literal["programada", "confirmada", "cancelada", "atendida"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Any) -> Any:
    """Tag a naive datetime as UTC.
    """
    if isinstance(value, datetime) and value.tzinfo is None:
        
        return value.replace(tzinfo=timezone.utc)
    
    return value


def new_appointment_id() -> str:
    return uuid.uuid4().hex


def code_of(appointment_id: str, length: int = 6) -> str:
    return appointment_id[:length].upper()


class Customer(BaseModel):
    name: str
    phone: str
    email: str


class CarInfo(BaseModel):
    """What we know about the car: the session's vehicle info plus, when API
    Ninjas answered, the engine sheet (None when it did not)."""

    brand: str | None = None
    model: str | None = None
    year: int | str | None = None
    color: str | None = None
    license_plate: str | None = None
    specs: dict[str, Any] | None = None


class Discount(BaseModel):
    """A granted discount, copied onto the booking it pays for.

    `estimated_repair_cost_cop` on the appointment is always what the customer
    OWES -- discount already applied -- so every existing reader (dashboard,
    tool result, customer endpoint) shows the right figure without knowing
    about discounts. `original_cost_cop` is kept so the workshop can see what
    was taken off.
    """

    code: str
    percent: int
    original_cost_cop: int
    # The number the customer quotes at the counter; None only for discounts
    # granted before ticket numbers existed.
    ticket_number: str | None = None
    granted_at: datetime = Field(default_factory=_utcnow)


# appointments collection::booking at Beau Auto-Repairs.
# Wired to inspections by inspection_id (the SQL-style reference) AND
# carrying a compact `inspection_snapshot`

class AppointmentDocument(BaseModel):
    
    id: str = Field(default_factory=new_appointment_id, alias="_id")
    codigo: str = ""
    inspection_id: str
    status: AppointmentStatus = "programada"

    customer: Customer
    car_info: CarInfo

    # Stored in UTC; `scheduled_local` is the human string in workshop time,
    # so a reader never has to convert.
    scheduled_for: datetime
    scheduled_local: str
    timezone: str

    estimated_repair_cost_cop: int | None = None
    discount: Discount | None = None
    inspection_snapshot: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    model_config = {"populate_by_name": True}

    @field_validator(
        "scheduled_for", "created_at", "updated_at", mode="before"
    )
    @classmethod
    def _utc_aware(cls, v: Any) -> Any:
        return _as_utc(v)

    def model_post_init(self, __context: Any) -> None:
        if not self.codigo:
            self.codigo = code_of(self.id)

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "AppointmentDocument":
        return cls.model_validate(doc)

    def to_doc(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)

    def to_tool_result(self) -> dict[str, Any]:
        """What the agent gets back -- and what it must tell the customer."""
        return {
            "codigo": self.codigo,
            "appointment_id": self.id,
            "inspection_id": self.inspection_id,
            "estado": self.status,
            "fecha_hora_local": self.scheduled_local,
            "zona_horaria": self.timezone,
            "cliente": self.customer.model_dump(),
            "vehiculo": self.car_info.model_dump(exclude={"specs"}),
            "costo_estimado_cop": self.estimated_repair_cost_cop,
            "descuento": (
                {
                    "codigo": self.discount.code,
                    "porcentaje": self.discount.percent,
                    "total_sin_descuento_cop": self.discount.original_cost_cop,
                    "numero_ticket": self.discount.ticket_number,
                }
                if self.discount
                else None
            ),
        }
