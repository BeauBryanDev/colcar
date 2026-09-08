
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

# The SPA was
# written first and its client  frontend/src/services/inspectionService.ts sends
# snake_case request bodies (`{session_id, message}`) while reading camelCase
# responses (`{sessionId, overallStatus, uploadedCount}`). Rather than "fix" one
# side and break the other, the convention is encoded here:

# ApiRequest   -> snake_case in, as sent
# ApiResponse  -> camelCase out, via alias generator

# Both allow population by field name, so Python code always uses snake_case
# internally and only the wire format differs.

def to_camel(snake: str) -> str:
    head, *rest = snake.split("_")
    return head + "".join(word.capitalize() for word in rest)

# Shared base models and enums.
class ApiRequest(BaseModel):
    """Request bodies: snake_case, exactly as the SPA sends them."""

    model_config = ConfigDict(extra="forbid")


class ApiResponse(BaseModel):
    """Response bodies: serialised camelCase for the SPA."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        ser_json_by_alias=True,
    )


# Domain vocabularies 
# Internal severity keys. These are the pricing catalog's `severidad` values and
# the PricingTrie is keyed on them -- do not rename.
Severidad = Literal["leve", "moderado", "grave"]

# Display labels for the SPA. NOTE: `frontend/src/types/defect.ts` currently
# declares 'Alto' where this says 'Grave'; they must be reconciled.
SeveridadDisplay = Literal["Bajo", "Medio", "Grave"]

# Mirrors DetectionModel in src/types/inspection.ts , the three upload panels.
DetectionModel = Literal["vehicle_parts", "surface_defects", "tires_wheels"]

# Mirrors InspectionStatus / ProcessingStep['status'].
InspectionStatus = Literal[
    "idle", "uploading", "processing", "analyzing", "complete", "error"
]
StepStatus = Literal["pending", "running", "done", "error"]

ImageRole = Literal["body", "tire"]

# How a price was resolved , see app/rag/pricing_rag.py.
FallbackLevel = Literal["exact", "part+defect_generic", "part_generic", "not_found"]

# How a severity grade was reached ,see app/vision/severity_rules.py.
SeverityBasisKind = Literal[
    "part_relative", "image_relative", "legal_floor", "tyre_type_rule"
]
