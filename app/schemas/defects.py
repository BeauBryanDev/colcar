
from __future__ import annotations

from typing import Literal 

from pydantic import Field

from app.schemas.common import ApiResponse, Severidad, SeveridadDisplay

# 'Cumple' = passes, 'No Cumple' = would be rejected, 'Advertencia' = worth
# flagging but not a rejection cause on its own.
ComplianceStatus = Literal["Cumple", "No Cumple", "Advertencia", "Revisar"]
Priority = Literal["Alta", "Media", "Baja"]
# The agent's final report: diagnosis, quote and RTM compliance.

# This is what Agent[Claude] produces at the end of the tool-use loop and what the SPA
# renders. It is not free text -- the numbers come from the pricing trie and the
# citations from the compliance RAG, so they are structured and auditable rather
# than reconstructed from prose.

# Currency is **COP throughout** (`*_cop` suffixes).

class DiagnosedDefect(ApiResponse):
    """One defect as the customer sees it, in Spanish."""

    pieza: str
    pieza_display: str  # Spanish part name, e.g. "puerta trasera izquierda"
    tipo_defecto: str
    tipo_defecto_display: str   # e.g. "abolladura"
    severidad: Severidad
    severidad_display: SeveridadDisplay
    confidence: float
    descripcion: str = ""
    # False when the price came from a category fallback rather than an exact
    # catalog row -- the agent must present those as estimates.
    precio_exacto: bool = True


class RepairEstimate(ApiResponse):
    """One line of the quote."""

    item: str
    pieza: str
    tipo_defecto: str
    severidad: Severidad
    cantidad: int = 1
    labor_cost_cop: int = 0
    materials_cost_cop: int = 0
    parts_cost_cop: int = 0
    total_cost_cop: int = 0
    requires_replacement: bool = False
    prioridad: Priority = "Media"
    precio_exacto: bool = True
    nota: str = ""


class LegalCompliance(ApiResponse):
    """One RTM finding, traceable to the clause it came from.

    `vinculante` False means the source is the advisory concepto juridico, which
    may inform but must never be cited as a rejection cause.
    """

    norma: str                  # e.g. "NTC 5375"
    documento_id: str | None = None
    articulo: str | None = None
    clase_rechazo: str | None = None   # 'A' | 'B' from the NTC defect tables
    requisito: str
    estado: ComplianceStatus
    detalle: str
    vinculante: bool = True
    pieza: str | None = None
    tipo_defecto: str | None = None


class QuoteSummary(ApiResponse):
    total_cop: int = 0
    subtotal_mano_obra_cop: int = 0
    subtotal_materiales_cop: int = 0
    subtotal_repuestos_cop: int = 0
    items_con_precio_exacto: int = 0
    items_estimados: int = 0
    # Defects with no catalog price: excluded from the total, and the agent is
    # told to name them as requiring a manual quote rather than implying free.
    items_sin_precio: list[str] = Field(default_factory=list)
    moneda: str = "COP"


class InspectionReport(ApiResponse):
    """The complete agent output for one inspection."""

    inspection_id: str
    session_id: str
    generated_at: str
    generated_by: str = "Car-Lens"

    resumen: str = ""  # the customer-facing narrative
    diagnostico: list[DiagnosedDefect] = Field(default_factory=list)
    cotizacion: list[RepairEstimate] = Field(default_factory=list)
    cotizacion_resumen: QuoteSummary = Field(default_factory=QuoteSummary)
    cumplimiento_rtm: list[LegalCompliance] = Field(default_factory=list)
    recomendaciones: list[str] = Field(default_factory=list)

    total_defectos: int = 0
    defectos_sin_ubicar: int = 0
    llantas_sin_defecto: int | None = None
    # True when any finding is a legal rejection cause -- lets the SPA show the
    # alert without re-parsing the compliance list.
    rechazo_rtm_probable: bool = False
