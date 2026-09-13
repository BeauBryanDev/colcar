
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.models.appointment import AppointmentDocument
from app.models.inspection import InspectionDocument
from app.schemas.common import ApiRequest, ApiResponse

# Mirrors AppointmentStatus in app/models/appointment.py.
AppointmentStatusLiteral = Literal["programada", "confirmada", "cancelada", "atendida"]

# Dashboard read shapes: appointments and inspections, filtered.

class AppointmentSummary(ApiResponse):
    codigo: str
    appointment_id: str
    inspection_id: str
    status: str

    customer_name: str
    customer_phone: str
    customer_email: str

    brand: str | None = None
    vehicle_model: str | None = None
    year: int | str | None = None
    license_plate: str | None = None

    scheduled_for: datetime
    scheduled_local: str
    timezone: str
    estimated_repair_cost_cop: int | None = None
    # Set when a discount was granted: the cost above is already net of it.
    discount_code: str | None = None
    ticket_number: str | None = None
    discount_percent: int | None = None
    original_cost_cop: int | None = None
    notes: str | None = None
    created_at: datetime

    @classmethod
    def from_document(cls, doc: AppointmentDocument) -> "AppointmentSummary":
        return cls(
            codigo=doc.codigo,
            appointment_id=doc.id,
            inspection_id=doc.inspection_id,
            status=doc.status,
            customer_name=doc.customer.name,
            customer_phone=doc.customer.phone,
            customer_email=doc.customer.email,
            brand=doc.car_info.brand,
            vehicle_model=doc.car_info.model,
            year=doc.car_info.year,
            license_plate=doc.car_info.license_plate,
            scheduled_for=doc.scheduled_for,
            scheduled_local=doc.scheduled_local,
            timezone=doc.timezone,
            estimated_repair_cost_cop=doc.estimated_repair_cost_cop,
            discount_code=doc.discount.code if doc.discount else None,
            ticket_number=doc.discount.ticket_number if doc.discount else None,
            discount_percent=doc.discount.percent if doc.discount else None,
            original_cost_cop=(
                doc.discount.original_cost_cop if doc.discount else None
            ),
            notes=doc.notes,
            created_at=doc.created_at,
        )


class AppointmentListResponse(ApiResponse):
    appointments: list[AppointmentSummary]
    total: int


class AppointmentStatusUpdate(ApiRequest):
    """`status` is required -- this endpoint exists to move a booking through
    its lifecycle, and a no-op PATCH would be a confusing way to edit notes."""

    status: AppointmentStatusLiteral
    notes: str | None = None


class AppointmentScheduleUpdate(ApiRequest):
    """Move a booking to a different slot to the dashboard dragging a card on
    the calendar.
    """

    fecha: str = Field(description="Nueva fecha, AAAA-MM-DD, hora local del taller.")
    hora: str = Field(description="Nueva hora, HH:MM en 24 horas.")


class InspectionSummary(ApiResponse):
    """One dashboard row. `report`/`pricing`/`compliance` are deliberately
    absent: they are kilobytes each and the full record is one
    `GET /api/admin/inspections/{id}` away."""

    inspection_id: str
    status: str
    created_at: datetime
    completed_at: datetime | None = None

    brand: str | None = None
    vehicle_model: str | None = None
    year: int | str | None = None

    defect_count: int = 0
    total_cop: int | None = None
    rechazo_rtm_probable: bool | None = None
    images_analyzed: int = 0

    @classmethod
    def from_document(cls, doc: InspectionDocument) -> "InspectionSummary":
        vehicle = doc.vehicle_info or {}
        return cls(
            inspection_id=doc.id,
            status=doc.status,
            created_at=doc.created_at,
            completed_at=doc.completed_at,
            brand=vehicle.get("brand"),
            vehicle_model=vehicle.get("model") or vehicle.get("vehicle_model"),
            year=vehicle.get("year"),
            defect_count=len(doc.defects),
            total_cop=doc.total_cop,
            rechazo_rtm_probable=doc.rechazo_rtm_probable,
            images_analyzed=doc.images_analyzed,
        )


class InspectionListResponse(ApiResponse):
    inspections: list[InspectionSummary]
    total: int


class InspectionDetailResponse(ApiResponse):
    """The whole stored record. `report` fields stay snake_case inside the
    bare dicts -- the same camel/snake exception the customer-facing
    $(REPORT)" endpoint has it."""

    inspection_id: str
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    vehicle_info: dict[str, Any] = Field(default_factory=dict)
    defects: list[dict[str, Any]] = Field(default_factory=list)
    pricing: dict[str, Any] | None = None
    compliance: dict[str, Any] | None = None
    resumen_agente: str | None = None
    total_cop: int | None = None
    rechazo_rtm_probable: bool | None = None
    images_analyzed: int = 0

    @classmethod
    def from_document(cls, doc: InspectionDocument) -> "InspectionDetailResponse":
        return cls(
            inspection_id=doc.id,
            status=doc.status,
            created_at=doc.created_at,
            completed_at=doc.completed_at,
            vehicle_info=doc.vehicle_info,
            defects=[d.model_dump() for d in doc.defects],
            pricing=doc.pricing,
            compliance=doc.compliance,
            resumen_agente=doc.resumen_agente,
            total_cop=doc.total_cop,
            rechazo_rtm_probable=doc.rechazo_rtm_probable,
            images_analyzed=doc.images_analyzed,
        )
