
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import get_settings
from app.rag.vocabulary import (is_always_grave, 
                                severity_display,
                                tyre_base_severity, 
                                tyre_can_escalate)

logger = logging.getLogger(__name__)

#Grade a defect `leve` / `moderado` / `grave` from how much it covers.
Severidad = Literal["leve", "moderado", "grave"]
# How the grade was arrived at -- carried through to the agent so it can explain
# itself, and to the payload so a reviewer can audit a surprising quote.
SeverityBasisKind = Literal[
    "part_relative",    # defect area / matched part area
    "image_relative",   # defect area / image area (tyres, unmatched)
    "legal_floor",      # forced grave by law, area ignored
    "tyre_type_rule",   # graded by tyre defect type, not area
]
# The measure is an area ratio, and the bigger the defect's mask relative to what
# it sits on, the higher the grade:

# ratio < 0.10          leve      (shown as "Bajo")
#  0.10 <= ratio < 0.25  moderado  (shown as "Medio")
#   ratio >= 0.25         grave     (shown as "Grave")

@dataclass(frozen=True)
class SeverityResult:
    severidad: Severidad
    ratio: float
    basis_kind: SeverityBasisKind
    basis: str            # e.g. "area_ratio:0.0451"

    @property
    def display(self) -> str:
        """Spanish label for the frontend: Bajo / Medio / Grave."""
        return severity_display(self.severidad)

    def to_payload(self) -> dict[str, Any]:
        return {
            "severidad": self.severidad,
            "severidad_display": self.display,
            "severity_basis": self.basis,
            "severity_basis_kind": self.basis_kind,
            "area_ratio": round(self.ratio, 5),
        }


def grade_from_ratio(
    ratio: float, *, leve_max: float, moderado_max: float
) -> Severidad:
    """Map a ratio onto a grade. Bands are half-open: [0, leve_max)."""
    if ratio < leve_max:
        return "leve"
    if ratio < moderado_max:
        return "moderado"
    return "grave"


def severity_for_part_relative(
    tipo_defecto: str, 
    defect_area_px: float, 
    part_area_px: float
) -> SeverityResult:
    """Grade a surface defect against the part it was matched to."""
    settings = get_settings()

    if is_always_grave(tipo_defecto):
        ratio = defect_area_px / part_area_px if part_area_px > 0 else 0.0
        return SeverityResult(
            "grave", ratio, "legal_floor",
            f"legal_floor:{tipo_defecto};area_ratio:{ratio:.4f}",
        )

    if part_area_px <= 0:
        # Should not happen -- a matched part always has area -- but grading a
        # division by zero as `grave` would inflate a quote on a bug.
        logger.warning("Part area is 0 for %s; defaulting to leve.", tipo_defecto)
        
        return SeverityResult("leve", 0.0, "part_relative", "area_ratio:0.0000")

    ratio = defect_area_px / part_area_px
    
    grade = grade_from_ratio(
        ratio,
        leve_max=settings.severity_leve_max,
        moderado_max=settings.severity_moderado_max,
    )
    return SeverityResult(grade, ratio, "part_relative", f"area_ratio:{ratio:.4f}")


def severity_for_image_relative(
    tipo_defecto: str, 
    defect_area_px: float, 
    image_area_px: float
) -> SeverityResult:
    """
    Grade a tyre defect, or a surface defect that matched no part.

    Uses its own, higher thresholds: framing dominates this ratio, and a tyre
    close-up legitimately fills the frame without being severe.
    """
    settings = get_settings()

    if is_always_grave(tipo_defecto):
        ratio = defect_area_px / image_area_px if image_area_px > 0 else 0.0
        return SeverityResult(
            "grave", ratio, 
            "legal_floor",
            f"legal_floor:{tipo_defecto};image_ratio:{ratio:.4f}",
        )

    if image_area_px <= 0:
        return SeverityResult("leve", 
                              0.0, 
                              "image_relative", 
                              "image_ratio:0.0000"
                              )

    ratio = defect_area_px / image_area_px
    grade = grade_from_ratio(
        ratio,
        leve_max=settings.severity_image_leve_max,
        moderado_max=settings.severity_image_moderado_max,
    )
    
    return SeverityResult(grade, ratio, 
                          "image_relative", 
                          f"image_ratio:{ratio:.4f}"
                          )


def severity_for_tyre(
    tipo_defecto: str, 
    defect_area_px: float, 
    image_area_px: float
) -> SeverityResult:
    """
    Grade a tyre defect by type, escalating some types by extent.

    Area is a poor signal here -- measured on real photos, genuine tyre defects
    cover 0.3%-6.5% of the frame, so an area rule graded a sidewall bulge
    `leve`. Type carries the risk instead: a bulge is a blowout waiting to
    happen whatever its size, while pitting is cosmetic however wide.
    """
    settings = get_settings()
    ratio = defect_area_px / image_area_px if image_area_px > 0 else 0.0
    base = tyre_base_severity(tipo_defecto)

    if base is None:
        # Unknown tyre class: fall back to area rather than guessing a grade.
        logger.debug("No tyre severity rule for %r; using area.", tipo_defecto)
        return severity_for_image_relative(tipo_defecto, 
                                           defect_area_px, 
                                           image_area_px)
        
    escalated = (
        tyre_can_escalate(tipo_defecto)
        and ratio >= settings.severity_tyre_escalate_ratio
    )
    grade: Severidad = "grave" if escalated else base  # type: ignore[assignment]
    reason = "extent" if escalated else "type"
    
    return SeverityResult(
        grade, ratio, "tyre_type_rule",
        f"tyre_rule:{tipo_defecto.strip().lower()}:{reason};image_ratio:{ratio:.4f}",
    )


def severity_for_match(match: Any, 
                       image_area_px: float
                       ) -> SeverityResult:
    """
    Grade a `MatchedDefect`, choosing the denominator automatically.

    Typed loosely to avoid importing spatial_match here -- that module already
    imports the vocabulary this one uses, and the coupling buys nothing.
    """
    defect = match.defect
    if match.part is not None and match.part.area_px > 0:
        
        return severity_for_part_relative(
            defect.class_name, 
            defect.area_px, 
            match.part.area_px
        )
        
    return severity_for_image_relative(
        defect.class_name, defect.area_px, image_area_px
    )
