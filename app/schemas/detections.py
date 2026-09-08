
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.schemas.common import (
    ApiResponse, 
    FallbackLevel, 
    ImageRole, 
    Severidad, 
    SeveridadDisplay,
    SeverityBasisKind,
)

# Vision output models :: the full payload the SPA renders overlays from.

class ImageMeta(ApiResponse):
    image_id: str
    filename: str
    role: ImageRole
    width: int
    height: int


class PartDetection(ApiResponse):
    """One detected car part."""

    detection_id: str
    image_id: str
    class_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: list[float] = Field(min_length=4, max_length=4)  # xyxy, original px
    bbox_normalized: list[float] = Field(min_length=4, max_length=4)
    mask_area_px: int | None = None
    segmentation_polygon: list[list[int]] | None = None
    polygon_format: str | None = None


class DefectDetection(ApiResponse):
    """A defect, its severity, and the part it was attributed to.

    `matched_part_name` is None when nothing contained the defect above the
    containment threshold -- the SPA should present that as "ubicacion no
    determinada" rather than guessing a panel.
    """

    detection_id: str
    image_id: str
    class_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: list[float] = Field(min_length=4, max_length=4)
    bbox_normalized: list[float] = Field(min_length=4, max_length=4)
    mask_area_px: int | None = None
    segmentation_polygon: list[list[int]] | None = None
    polygon_format: str | None = None

    # Spatial match (absent on tyre defects: no parts model runs for them)
    matched_part_id: str | None = None
    matched_part_name: str | None = None
    match_containment: float | None = None
    match_iou: float | None = None
    match_basis: str | None = None

    # Severity
    severidad: Severidad
    severidad_display: SeveridadDisplay
    severity_basis: str
    severity_basis_kind: SeverityBasisKind
    area_ratio: float


class InspectionSummary(ApiResponse):
    total_defects: int
    defects_by_type: dict[str, int]
    defects_by_severity: dict[str, int]
    parts_affected: list[str]
    unmatched_defects: int
    tires_inspected_ok: int = 0


class PipelineFlags(ApiResponse):
    tires_inspection_requested: bool


class VisionResult(ApiResponse):
    """Everything the vision stage produced for one inspection."""

    inspection_id: str
    created_at: str
    vehicle_info: dict[str, Any] = Field(default_factory=dict)
    pipeline_flags: PipelineFlags
    images_analyzed: list[ImageMeta] = Field(default_factory=list)
    parts_detected: list[PartDetection] = Field(default_factory=list)
    surface_defects_detected: list[DefectDetection] = Field(default_factory=list)
    tire_defects_detected: list[DefectDetection] = Field(default_factory=list)
    unmatched_defects: list[DefectDetection] = Field(default_factory=list)
    summary: InspectionSummary


# Agent Payload models :: the flat dict the agent reasons over and sends to the
class AgentDefect(ApiResponse):
    """One defect as Claude sees it.

    Flat and small on purpose: this is the first message of the tool-use loop
    and is re-sent every turn. `pieza` / `tipo_defecto` / `severidad` are
    exactly the keys the pricing trie and the compliance RAG look up.
    """

    pieza: str
    tipo_defecto: str
    severidad: Severidad
    confidence: float
    severity_basis: str
    bbox_normalized: list[float] = Field(min_length=4, max_length=4)


class AgentPayload(ApiResponse):
    vehicle_info: dict[str, Any] = Field(default_factory=dict)
    defects: list[AgentDefect] = Field(default_factory=list)
    defectos_sin_ubicar: int = 0
    # Only present when tyres were actually inspected, so the agent cannot
    # claim a check that never happened.
    llantas_sin_defecto: int | None = None


# Pricing tool result 
class PricingEntryModel(ApiResponse):
    service_name: str
    labor_hours: float
    labor_cost_cop: int
    materials_cost_cop: int
    parts_cost_cop: int | None = None
    total_cost_cop: int
    requires_replacement: bool


class PricingItem(ApiResponse):
    pieza: str
    tipo_defecto: str
    severidad: str
    exact_match: bool
    fallback_level: FallbackLevel
    entry: PricingEntryModel | None = None
    cantidad: int = 1
    precio_exacto: bool = False
    nota: str = ""
    subtotal_cop: int | None = None
    severidad_applied: str | None = None


class PricingSummary(ApiResponse):
    total_cop: int
    subtotal_mano_obra_cop: int
    subtotal_materiales_cop: int
    subtotal_repuestos_cop: int
    items_con_precio_exacto: int
    items_estimados: int
    items_sin_precio: list[str] = Field(default_factory=list)
    requieren_reemplazo: list[str] = Field(default_factory=list)
    moneda: str = "COP"


class PricingResult(ApiResponse):
    items: list[PricingItem] = Field(default_factory=list)
    resumen: PricingSummary
    instrucciones: str = ""


#  Compliance tool result  
class ComplianceHit(ApiResponse):
    """One regulation passage.

    `vinculante` False marks the advisory concepto juridico -- the agent must
    not cite it as a cause of RTM rejection.
    """

    score: float
    documento: str | None = None
    document_id: str | None = None
    tipo_documento: str | None = None
    vinculante: bool | None = None
    estado: str | None = None
    articulo: int | None = None
    seccion: str | None = None
    clase_rechazo: str | None = None
    tipo_vehiculo: str | None = None
    modificado_por: str | None = None
    texto: str


# Overlay payload  
# Served by GET /api/inspections/{id}/overlay for the SPA's mask rendering.
#
# Rendering data goes to the browser; the model gets
# `bbox_normalized` and nothing more.
class OverlayShape(ApiResponse):
    """One drawable shape in original-image pixel coordinates."""

    detection_id: str
    image_id: str
    kind: Literal["part", "defect"]
    class_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: list[float] = Field(min_length=4, max_length=4)
    # None for tyre defects: that model is detection-only and has no prototype
    # masks, so the SPA falls back to `bbox` rather than drawing nothing.
    polygon: list[list[int]] | None = None
    # Defect-only fields.
    severidad: Severidad | None = None
    severidad_display: SeveridadDisplay | None = None
    matched_part_name: str | None = None


class OverlayImage(ApiResponse):
    """One analysed image and everything drawn over it."""

    image_id: str
    filename: str
    role: ImageRole
    width: int
    height: int
    # Relative URL the SPA can put straight in an <img src>.
    image_url: str
    shapes: list[OverlayShape] = Field(default_factory=list)


class OverlayResponse(ApiResponse):
    session_id: str
    images: list[OverlayImage] = Field(default_factory=list)
