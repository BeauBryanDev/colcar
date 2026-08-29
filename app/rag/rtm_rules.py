"""
When a defect fails the RTM outright.

Retrieval alone cannot answer "does this car pass?". `compliance_rag` returns
the *clauses* that match a defect; turning those into a verdict is a policy
decision, and it belongs in one place so the agent, the SPA and any future
report writer cannot disagree about it.

"""

from __future__ import annotations

import logging
from typing import Any

from app.rag.vocabulary import normalize_key

logger = logging.getLogger(__name__)

# Defects that reject the vehicle whatever retrieval returned. Mirrors
#[[ALWAYS_GRAVE_DEFECTS]] in vocabulary.py -- these are the same physical
# failures, seen from the legal side rather than the severity side.
ALWAYS_REJECTION_DEFECTS: frozenset[str] = frozenset({
    "lamp_broken",
    "glass_shatter",
})

# Rejection grades used by NTC 5375's defect tables. Both fail the inspection.
REJECTION_CLASSES: frozenset[str] = frozenset({"A", "B"})

_FLOOR_NOTE = (
    "Este defecto es causal de rechazo en la RTM por si mismo: circular con "
    "luces o vidrios en mal estado no esta permitido. Comunicalo de forma "
    "explicita: el vehiculo NO aprueba la revision tecnico-mecanica en su "
    "estado actual."
)
_CLASS_NOTE = (
    "La norma clasifica este defecto como Tipo {clase}, que es causal de "
    "rechazo en la RTM. Cita la clausula y dilo de forma explicita."
)
_NO_REJECTION_NOTE = (
    "Se encontraron clausulas relacionadas pero ninguna clasifica el defecto "
    "como causal de rechazo. No afirmes que el vehiculo sera rechazado."
)


def _binding(norma: dict[str, Any]) -> bool:
    """Advisory sources never justify a rejection."""
    # The RAG emits `vinculante`; the raw chunk payload uses `binding`.
    value = norma.get("vinculante")
    
    if value is None:
        
        value = norma.get("binding")
        
    return bool(value)


def is_always_rejection(tipo_defecto: str) -> bool:
    """True for defects that fail the RTM on their own, before any retrieval."""
    return normalize_key(tipo_defecto) in ALWAYS_REJECTION_DEFECTS


def worst_rejection_class(normas: list[dict[str, Any]]) -> str | None:
    """Most severe rejection grade among binding clauses, or None."""
    classes = {
        str(n.get("clase_rechazo")).strip().upper()
        for n in normas
        if _binding(n) and n.get("clase_rechazo")
    }
    hits = classes & REJECTION_CLASSES
    
    if not hits:
        
        return None
    # A is the critical grade, so it wins when both are present.
    return "A" if "A" in hits else "B"


def verdict(tipo_defecto: str, 
            normas: list[dict[str, Any]]
            ) -> dict[str, Any]:
    """Whether this defect rejects the vehicle, and why.

    Returns the fields merged into a `query_compliance` result entry:
    `causal_rechazo`, `clase_rechazo` and an explanatory `nota`.
    """
    clase = worst_rejection_class(normas)

    if is_always_rejection(tipo_defecto):
        # The floor holds even when retrieval found nothing usable.
        logger.info(
            "RTM legal floor: %s is a rejection cause (retrieved class=%s)",
            tipo_defecto, clase,
        )
        return {
            "causal_rechazo": True,
            "clase_rechazo": clase or "A",
            "nota": _FLOOR_NOTE,
        }

    if clase:
        return {
            "causal_rechazo": True,
            "clase_rechazo": clase,
            "nota": _CLASS_NOTE.format(clase=clase),
        }

    return {
        "causal_rechazo": False,
        "clase_rechazo": None,
        "nota": _NO_REJECTION_NOTE,
    }
