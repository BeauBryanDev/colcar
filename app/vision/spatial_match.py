
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.core.config import get_settings
from app.rag.vocabulary import is_affine, is_ignored_part
from app.vision.nms import box_iou_matrix, intersection_over_smaller
from app.vision.postprocess_seg import Detection


logger = logging.getLogger(__name__)
#Attach each surface defect to the car part it sits on.

@dataclass
class MatchedDefect:
    """A defect, plus the part it was attributed to (or None)."""

    defect: Detection
    part: Detection | None = None
    containment: float = 0.0 # fraction of the defect lying on the part
    iou: float = 0.0  # plain IoU, reported for diagnostics
    basis: str = "unmatched"  # "mask" | "bbox" | "unmatched"

    @property
    def pieza(self) -> str:
        """The part name, or `unknown` when nothing contained the defect."""
        return self.part.class_name if self.part else "unknown"

    @property
    def area_ratio(self) -> float:
        """Defect area ÷ part area -- the input to severity grading.

        0.0 when unmatched: without a part there is no ratio to take, and
        severity has to fall back to an image-relative rule.
        """
        if self.part is None:
            return 0.0
        
        part_area = self.part.area_px
        
        return float(self.defect.area_px / part_area) if part_area > 0 else 0.0


    def to_payload(self, width: int,
                   height: int
                   ) -> dict[str, Any]:
        
        payload = self.defect.to_payload(width, height)
        
        payload.update({
            "matched_part_id": self.part.detection_id if self.part else None,
            "matched_part_name": self.pieza,
            "match_containment": round(self.containment, 4),
            "match_iou": round(self.iou, 4),
            "match_basis": self.basis,
            "area_ratio": round(self.area_ratio, 5),
        })
        
        return payload


def _mask_containment(defect: Detection, 
                      part: Detection
                      ) -> float:
    """
    Fraction of the defect's mask pixels that fall inside the part's mask.

    Evaluated only over the boxes' overlapping region rather than the whole
    frame: at 1600x1157 a full-frame AND per candidate pair costs ~2 MB of work
    each, and a surface inspection can have 20 parts x 5 defects per image.
    """
    if defect.mask is None or part.mask is None:
        return 0.0

    dx0, dy0, dx1, dy1 = defect.bbox
    px0, py0, px1, py1 = part.bbox
    x0, y0 = int(max(dx0, px0)), int(max(dy0, py0))
    x1, y1 = int(np.ceil(min(dx1, px1))), int(np.ceil(min(dy1, py1)))
    
    if x1 <= x0 or y1 <= y0:
        return 0.0  # boxes do not even touch

    defect_total = int(defect.mask.sum())
    if defect_total == 0:
        return 0.0

    inter = np.logical_and(
        defect.mask[y0:y1, x0:x1], part.mask[y0:y1, x0:x1]
    ).sum()
    return float(inter / defect_total)


def match_defects_to_parts(
    defects: list[Detection],
    parts: list[Detection],
    *,
    min_containment: float | None = None,
) -> tuple[list[MatchedDefect], list[Detection]]:
    """
    Attribute each defect to its best-fitting part.

    Returns `(matched, unmatched_defects)`. A defect below `min_containment`
    against every part stays unmatched rather than being forced onto the
    nearest one -- an invented location produces an invented quote, and the
    agent is told to report it as unlocated instead.
    """
    threshold = (
        min_containment if min_containment is not None
        else get_settings().spatial_match_min_containment
    )
    usable_parts = [p for p in parts if not is_ignored_part(p.class_name)]
    
    if not defects:
        return [], []
    
    if not usable_parts:
        logger.debug("No usable parts; %d defect(s) unmatched.", len(defects))
        return [], list(defects)

    defect_boxes = np.array([d.bbox for d in defects], dtype=np.float32)
    part_boxes = np.array([p.bbox for p in usable_parts], dtype=np.float32)

    # Box-level containment and IoU for every pair, vectorised. Box containment
    # is both the fallback measure and a cheap pre-filter: a pair whose boxes
    # barely intersect cannot have overlapping masks.
    box_containment = intersection_over_smaller(defect_boxes, part_boxes)
    iou_matrix = box_iou_matrix(defect_boxes, part_boxes)

    matched: list[MatchedDefect] = []
    unmatched: list[Detection] = []

    for di, defect in enumerate(defects):
        candidates: list[tuple[float, float, float, int, str]] = []

        for pi, part in enumerate(usable_parts):
            if box_containment[di, pi] <= 0.0:
                continue
            # Affinity gate: a broken lamp belongs on a light, shattered glass
            # on glass. Ineligible parts are rejected outright rather than
            # ranked lower -- when the parts model misses the real light, the
            # right answer is "unlocated", not "the door behind it".
            if not is_affine(defect.class_name, part.class_name):
                continue
            
            if defect.mask is not None and part.mask is not None:
                score = _mask_containment(defect, part)
                basis = "mask"
                
            else:
                score = float(box_containment[di, pi])
                basis = "bbox"
                
            if score >= threshold:
                candidates.append(
                    (score, part.area_px, part.confidence, pi, basis)
                )

        if not candidates:
            unmatched.append(defect)
            logger.debug(
                "Defect %s (%s) matched no part.", defect.detection_id,
                defect.class_name,
            )
            continue

        # Highest containment, then smallest part, then most confident.
        # Containment is rounded so near-identical scores (a defect fully
        # inside both `back_door` and `back_left_door`) are decided by
        # specificity rather than floating-point noise.
        score, _area, _conf, pi, basis = max(
            candidates, key=lambda c: (round(c[0], 3), -c[1], c[2])
        )
        matched.append(MatchedDefect(
            defect=defect,
            part=usable_parts[pi],
            containment=score,
            iou=float(iou_matrix[di, pi]),
            basis=basis,
        ))

    logger.debug(
        "Matched %d/%d defect(s) to parts.", len(matched), len(defects)
    )
    return matched, unmatched


def summarize_matches(
    matched: list[MatchedDefect], 
    unmatched: list[Detection]
) -> dict[str, Any]:
    """Counts for the inspection payload's `summary` block."""
    by_type: dict[str, int] = {}
    by_part: dict[str, int] = {}
    
    for m in matched:
        
        by_type[m.defect.class_name] = by_type.get(m.defect.class_name, 0) + 1
        by_part[m.part.class_name] = by_part.get(m.part.class_name, 0) + 1
        
    for d in unmatched:
        by_type[d.class_name] = by_type.get(d.class_name, 0) + 1
        by_part[d.class_name] = by_part.get(d.class_name, 0) + 1
        
    return {
        "total_defects": len(matched) + len(unmatched),
        "defects_by_type": by_type,
        "parts_affected": sorted(by_part),
        "unmatched_defects": len(unmatched),
    }
