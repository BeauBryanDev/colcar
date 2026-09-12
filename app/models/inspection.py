
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Any) -> Any:
    """Tag a naive datetime as UTC.
    """
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    
    return value


class DefectRecord(BaseModel):
    """One defect, matched or not, as the agent saw it."""

    pieza: str
    tipo_defecto: str
    severidad: str
    confidence: float | None = None
    severity_basis: str | None = None
    matched_part_name: str | None = None
    match_containment: float | None = None
    # Filled from the pricing tool result when present.
    precio_exacto: bool | None = None
    total_cost_cop: int | None = None
    fallback_level: str | None = None
    # Filled from the compliance tool result when present.
    causal_rechazo: bool | None = None
    clase_rechazo: str | None = None

# inspections collection -- the audit record of one run.

class InspectionDocument(BaseModel):
    """One document per inspection. _id is the session id."""

    id: str = Field(alias="_id")
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    persisted_at: datetime = Field(default_factory=_utcnow)

    vehicle_info: dict[str, Any] = Field(default_factory=dict)
    images_analyzed: int = 0
    tires_inspection_requested: bool = False

    defects: list[DefectRecord] = Field(default_factory=list)
    defectos_sin_ubicar: int = 0

    # Raw tool results, as the agent received them -- the quote and the
    # verdict exactly as shown to the customer.
    pricing: dict[str, Any] | None = None
    compliance: dict[str, Any] | None = None
    resumen_agente: str | None = None
    tools_used: list[str] = Field(default_factory=list)

    # Denormalised for querying and for the appointment snapshot.
    total_cop: int | None = None
    rechazo_rtm_probable: bool | None = None
    catalog_source: str | None = None

    model_config = {"populate_by_name": True}

    @field_validator(
        "created_at", "completed_at", "persisted_at", mode="before"
    )
    @classmethod
    def _utc_aware(cls, v: Any) -> Any:
        return _as_utc(v)

    #  builders

    @classmethod
    def from_session(cls, session: Any, *, 
                     catalog_source: str | None = None
                     ) -> "InspectionDocument":
        """Assemble the record from an InspectionSession after completion."""
        report = session.report or {}
        pricing = report.get("pricing")
        compliance = report.get("compliance")
        agent_payload = session.agent_payload or {}

        priced = _index_pricing(pricing)
        verdicts = _index_compliance(compliance)

        defects: list[DefectRecord] = []
        
        for d in agent_payload.get("defects", []):
            
            key = (str(d.get("pieza", "")).lower(), str(d.get("tipo_defecto", "")).lower())
            p = priced.get(key, {})
            v = verdicts.get(key, {})
            
            defects.append(DefectRecord(
                pieza=d.get("pieza", ""),
                tipo_defecto=d.get("tipo_defecto", ""),
                severidad=d.get("severidad", ""),
                confidence=d.get("confidence"),
                severity_basis=d.get("severity_basis"),
                matched_part_name=d.get("matched_part_name"),
                match_containment=d.get("match_containment"),
                precio_exacto=p.get("precio_exacto"),
                total_cost_cop=(p.get("entry") or {}).get("total_cost_cop"),
                fallback_level=p.get("fallback_level"),
                causal_rechazo=v.get("causal_rechazo"),
                clase_rechazo=v.get("clase_rechazo"),
            ))

        resumen = (pricing or {}).get("resumen") or {}
        
        return cls(
            _id=session.id,
            status=session.status,
            created_at=session.created_at,
            completed_at=session.completed_at,
            vehicle_info=dict(session.vehicle_info or {}),
            images_analyzed=len(session.files),
            tires_inspection_requested=session.tires_inspection_requested,
            defects=defects,
            defectos_sin_ubicar=int(agent_payload.get("defectos_sin_ubicar") or 0),
            pricing=pricing,
            compliance=compliance,
            resumen_agente=report.get("resumen"),
            tools_used=list(report.get("tools_used") or []),
            total_cop=resumen.get("total_cop"),
            rechazo_rtm_probable=(compliance or {}).get("rechazo_rtm_probable"),
            catalog_source=catalog_source,
        )

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "InspectionDocument":
        return cls.model_validate(doc)

    def to_doc(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)

    def snapshot(self) -> dict[str, Any]:
        """The compact copy nested inside an appointment."""
        return {
            "inspection_id": self.id,
            "completed_at": self.completed_at,
            "defects": [
                {
                    "pieza": d.pieza,
                    "tipo_defecto": d.tipo_defecto,
                    "severidad": d.severidad,
                    "total_cost_cop": d.total_cost_cop,
                    "causal_rechazo": d.causal_rechazo,
                }
                for d in self.defects
            ],
            "total_cop": self.total_cop,
            "rechazo_rtm_probable": self.rechazo_rtm_probable,
            "items_sin_precio": list(
                ((self.pricing or {}).get("resumen") or {}).get("items_sin_precio") or []
            ),
        }

# Built from the in-memory InspectionSession once the agent has produced the
# first report. It carries what the business needs to read back months later:
# the vehicle, every defect with the evidence for its severity.

def _index_pricing(pricing: dict[str, Any] | None) -> dict[tuple[str, str], dict]:
    
    out: dict[tuple[str, str], dict] = {}
    
    for item in (pricing or {}).get("items") or []:
        
        key = (
            str(item.get("pieza", "")).lower(), 
            str(item.get("tipo_defecto", "")).lower()
               )
        
        out.setdefault(key, item)
        
    return out


def _index_compliance(compliance: dict[str, Any] | None) -> dict[tuple[str, str], dict]:
    
    out: dict[tuple[str, str], dict] = {}
    
    for r in (compliance or {}).get("resultados") or []:
        
        key = (
            str(r.get("pieza", "")).lower(), 
            str(r.get("tipo_defecto", "")).lower()
            )
        out.setdefault(key, r)
        
    return out
