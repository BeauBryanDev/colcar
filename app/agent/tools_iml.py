
from __future__ import annotations

import logging
from typing import Any

from app.core.exceptions import (
    CarSpecsUnavailableError,
    ComplianceUnavailableError,
    PricingCatalogError,
)
from app.agent.make_appointment import make_appointment
from app.agent.check_availability import check_availability
from app.agent.discount import grant_discount, query_email_and_plate_number
from app.agent.reschedule_and_cancel import reschedule_appointment, cancel_appointment

from app.rag.car_specs import get_car_specs as _get_car_specs
from app.rag.check_repair_prices import check_repair_prices as _check_repair_prices
from app.rag.compliance_rag import query_compliance as _query_compliance
from app.rag.pricing_rag import query_pricing_batch as _query_pricing_batch
from app.rag.rtm_rules import is_always_rejection, verdict as rtm_verdict
from app.rag.vocabulary import is_rtm_relevant


logger = logging.getLogger(__name__)

# Tool implementations , this is what actually runs when Claude calls a tool.

def _normalise_defects(raw: Any) -> list[dict[str, str]]:
    """Accept what Claude sends and coerce it into the expected shape.

    Small models occasionally send a bare object instead of a list, or omit
    `severidad`. Repairing that here costs one line and saves a whole retry
    round trip.
    """
    if isinstance(raw, dict):
        raw = [raw]
        
    if not isinstance(raw, list):
        return []
    
    out: list[dict[str, str]] = []
    
    for item in raw:
        
        if not isinstance(item, dict):
            continue
        
        out.append({
            "pieza": str(item.get("pieza", "")).strip(),
            "tipo_defecto": str(item.get("tipo_defecto", "")).strip(),
            "severidad": str(item.get("severidad", "moderado")).strip().lower(),
        })
    return [d for d in out if d["pieza"] and d["tipo_defecto"]]


def run_query_pricing_batch(
    tool_input: dict[str, Any],
    context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Price every detected defect in one call.

    The brand multiplier comes from context the session's vehicle info  
    not from `tool_input`. Claude is told the vehicle but never supplies the
    index: pricing arithmetic must be deterministic, and a model that omits or
    misremembers a multiplier would silently misquote.
    """
    defects = _normalise_defects(tool_input.get("defects"))
    
    if not defects:
        
        return {
            "items": [],
            "resumen": {"total_cop": 0, "moneda": "COP", "items_sin_precio": []},
            "instrucciones": (
                "No se recibieron defectos validos. Pide al usuario que "
                "confirme la inspeccion antes de cotizar."
            ),
        }
    try:
        result = _query_pricing_batch(
            defects, brand=(context or {}).get("brand")
        )
    except (OSError, ValueError, KeyError) as exc:
        raise PricingCatalogError(
            log_message=f"pricing lookup failed: {exc}"
        ) from exc
        
    logger.info(
        "query_pricing_batch: %d defect(s) -> %s COP",
        len(defects), result["resumen"]["total_cop"],
    )
    
    return result


def run_query_compliance(
    tool_input: dict[str, Any], 
    context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Look up RTM regulation for every defect, one entry per defect."""
    defects = _normalise_defects(tool_input.get("defects"))
    
    if not defects:
        return {
            "resultados": [],
            "instrucciones": "No se recibieron defectos validos para consultar.",
        }

    resultados: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for defect in defects:
        key = (defect["pieza"].lower(), defect["tipo_defecto"].lower())
        
        if key in seen:
            continue
        
        seen.add(key)

        in_scope = is_rtm_relevant(defect["pieza"], 
                                   defect["tipo_defecto"])
        
        entry: dict[str, Any] = {
            "pieza": defect["pieza"],
            "tipo_defecto": defect["tipo_defecto"],
            "aplica_rtm": in_scope,
            # Stated here rather than left to each consumer to infer from
            # `len(normas)`. The SPA, the agent and any future report writer
            # must agree on what fails an RTM, and a missed rejection cause is
            # the costliest error this system can make.
            "causal_rechazo": False,
            "clase_rechazo": None,
            "normas": [],
        }
        if not in_scope and not is_always_rejection(defect["tipo_defecto"]):
            
            entry["nota"] = (
                "La NTC 5375 no regula este tipo de dano: es estetico y NO es "
                "causal de rechazo en la RTM. Explicalo asi al usuario."
            )
        else:
            
            try:
                entry["normas"] = _query_compliance(
                    defect["pieza"], 
                    defect["tipo_defecto"], 
                    defect["severidad"]
                )
                
            except Exception as exc:  # noqa: BLE001 - upstream/network failure
                
                raise ComplianceUnavailableError(
                    log_message=f"compliance lookup failed: {exc}"
                ) from exc

            # The verdict runs even when `normas` is empty: a defect on the
            # legal floor rejects the vehicle whether or not the vector search
            # found a clause for it. Letting a retrieval miss decide would
            # downgrade a broken headlight to a cosmetic note.
            entry.update(rtm_verdict(defect["tipo_defecto"], entry["normas"]))
            
            if not entry["normas"] and not entry["causal_rechazo"]:
                
                entry["nota"] = (
                    "No se encontro una clausula aplicable. No afirmes que hay "
                    "causal de rechazo."
                )
        resultados.append(entry)

    n_scope = sum(1 for r in resultados if r["aplica_rtm"])
    rechazos = [r for r in resultados if r["causal_rechazo"]]
    
    logger.info(
        "query_compliance: %d defect(s), %d in RTM scope, %d rejection cause(s)",
        len(resultados), n_scope, len(rechazos),
    )
    
    return {
        "resultados": resultados,
        # Pre-computed so no consumer has to re-derive the verdict.
        "rechazo_rtm_probable": bool(rechazos),
        "defectos_causal_rechazo": [
            f"{r['pieza']}/{r['tipo_defecto']}" for r in rechazos
        ],
        "instrucciones": (
            "aplica_rtm=false significa que la norma NO cubre ese defecto: no "
            "es causal de rechazo. Cita unicamente resultados con "
            "vinculante=true; los que tienen vinculante=false son conceptos "
            "orientativos y no sirven como causal de rechazo. "
            "causal_rechazo=true significa que ESE defecto SI hace que el "
            "vehiculo sea rechazado en la RTM: dilo de forma explicita e "
            "inequivoca. Si rechazo_rtm_probable=true, el vehiculo NO aprueba "
            "la revision tecnico-mecanica en su estado actual; nunca digas que "
            "puede circular sin problemas."
        ),
    }


def run_query_car_specs(
    tool_input: dict[str, Any], 
    context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Engine specifications for the inspected vehicle.

    The vehicle comes from `context` only -- the session's brand / model /
    year, which the SPA requires before a scan starts. `tool_input` is
    ignored on purpose, same rule as the brand multiplier: a model that
    misremembers the year would describe the wrong engine with confidence.
    """
    ctx = context or {}
    make = str(ctx.get("brand") or "").strip()
    model = str(ctx.get("model") or "").strip() or None
    year = ctx.get("year") or None

    if not make:
        # Should not happen (the SPA enforces the selects), but a session
        # created through the API directly could reach here.
        return {
            "vehiculo": None,
            "especificaciones": [],
            "instrucciones": (
                "La sesion no tiene un vehiculo registrado, asi que no es "
                "posible consultar la ficha tecnica. Dilo al usuario; no "
                "describas el motor de memoria."
            ),
        }

    try:
        records = _get_car_specs(make, model, year)
        
    except CarSpecsUnavailableError:
        raise
    
    except Exception as exc:  # noqa: BLE001 - keep the loop alive
        raise CarSpecsUnavailableError(
            log_message=f"car specs lookup failed: {exc}"
        ) from exc

    vehiculo = {"marca": make, "modelo": model, "anio": year}
    
    if not records:
        return {
            "vehiculo": vehiculo,
            "especificaciones": [],
            "instrucciones": (
                "No se encontro ficha tecnica para este vehiculo. Dilo "
                "explicitamente; no describas el motor de memoria."
            ),
        }
    return {
        "vehiculo": vehiculo,
        "especificaciones": records,
        "instrucciones": (
            "Presenta estos datos como ficha tecnica de referencia. Un campo "
            "en null significa 'no disponible': indicalo asi y no lo estimes. "
            "Los consumos vienen en millas por galon (mpg)."
        ),
    }


def run_check_repair_prices(
    tool_input: dict[str, Any], 
    context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Reference prices for whatever the user asks about.
    """
    raw = tool_input.get("consultas")
    
    if isinstance(raw, dict):
        
        raw = [raw]
        
    consultas = [q for q in (raw or []) if isinstance(q, dict)]
    
    if not consultas:
        return {
            "consultas": [],
            "instrucciones": (
                "No se recibio ninguna consulta valida. Pregunta al usuario "
                "que pieza o reparacion quiere consultar."
            ),
        }
        
    try:
        return _check_repair_prices(
            consultas,
            brand=(context or {}).get("brand")
        )
        
    except (OSError, ValueError, KeyError) as exc:
        
        raise PricingCatalogError(
            log_message=f"repair price lookup failed: {exc}"
        ) from exc


# Dispatch table. Keys must match `app/agent/tools_schema.py`.
TOOL_IMPLEMENTATIONS = {
    "query_pricing_batch": run_query_pricing_batch,
    "query_compliance": run_query_compliance,
    "query_car_specs": run_query_car_specs,
    "check_repair_prices": run_check_repair_prices,
    "check_availability": check_availability,
    "make_appointment": make_appointment,
    "query_email_and_plate_number": query_email_and_plate_number,
    "grant_discount": grant_discount,
    "reschedule_appointment": reschedule_appointment,
    "cancel_appointment": cancel_appointment,
}


def execute_tool(
    name: str, 
    tool_input: dict[str, Any], 
    context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Run one tool by name.

    An unknown name is returned to Claude as an error result rather than
    raised: the loop can recover by calling a real tool, whereas an exception
    would abort the inspection.
    """
    impl = TOOL_IMPLEMENTATIONS.get(name)
    
    if impl is None:
        
        logger.warning("Claude called unknown tool %r", name)
        
        return {
            "error": f"Tool desconocida: {name}",
            "tools_disponibles": sorted(TOOL_IMPLEMENTATIONS),
        }
        
    return impl(tool_input, context)
