
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from app.core.config import get_settings
from app.core.exceptions import NoDetectionsError
from app.vision.onnx_infer import ModelKind, get_model
from app.vision.postprocess_det import postprocess_detection, split_findings
from app.vision.postprocess_seg import Detection, postprocess_segmentation
from app.vision.preprocess import preprocess
from app.vision.severity_rules import (SeverityResult, 
                                       severity_for_image_relative,
                                       severity_for_match, 
                                       severity_for_tyre)
from app.vision.spatial_match import MatchedDefect, match_defects_to_parts, summarize_matches

logger = logging.getLogger(__name__)

# MAIN VISION WORKFLOW 

ImageRole = Literal["body", "tire"]
ProgressFn = Callable[[str, str], None]  # (step_id, status)

# [[pieza]]]] for every tyre defect: the tyre model has no parts model behind it, so
# the part is known a priori rather than discovered.
TYRE_PIEZA = "tire"
# Two workflows:

#     surface:  parts(seg) + defects(seg) -> NMS -> spatial match -> severity
#     tyres:    tyres(det)  -> NMS -> pieza fixed as "tire"

# Produces two payloads from one run, because they have different audiences:

@dataclass
class AnalyzedImage:
    image_id: str
    filename: str
    role: ImageRole
    width: int
    height: int
    parts: list[Detection] = field(default_factory=list)
    matched: list[MatchedDefect] = field(default_factory=list)
    unmatched: list[Detection] = field(default_factory=list)
    positives: list[Detection] = field(default_factory=list)
    # Parallel to `matched` + `unmatched`, in that order.
    severities: list[SeverityResult] = field(default_factory=list)

    @property
    def image_area(self) -> float:
        return float(self.width * self.height)


@dataclass
class InspectionResult:
    inspection_id: str
    created_at: str
    vehicle_info: dict[str, Any]
    tires_inspection_requested: bool
    images: list[AnalyzedImage] = field(default_factory=list)

    # full payload, for the SPA
    def to_payload(self) -> dict[str, Any]:
        """The SPA's `inspection` block."""
        parts_detected: list[dict] = []
        surface_defects: list[dict] = []
        tire_defects: list[dict] = []
        unmatched_payload: list[dict] = []

        for img in self.images:
            
            for part in img.parts:
                
                parts_detected.append(part.to_payload(img.width, img.height))

            severities = iter(img.severities)
            
            for match in img.matched:
                
                entry = match.to_payload(img.width, img.height)
                entry.update(next(severities).to_payload())
                (tire_defects if img.role == "tire" else surface_defects).append(entry)
                
            for defect in img.unmatched:
                
                entry = defect.to_payload(img.width, img.height)
                entry.update(next(severities).to_payload())
                entry["matched_part_name"] = None
                (tire_defects if img.role == "tire" else unmatched_payload).append(entry)

        summary = summarize_matches(
            [m for i in self.images for m in i.matched],
            [d for i in self.images for d in i.unmatched],
        )
        summary["defects_by_severity"] = self._severity_counts()
        summary["tires_inspected_ok"] = sum(len(i.positives) for i in self.images)

        return {
            "inspection_id": self.inspection_id,
            "created_at": self.created_at,
            "vehicle_info": self.vehicle_info,
            "pipeline_flags": {
                "tires_inspection_requested": self.tires_inspection_requested,
            },
            "images_analyzed": [
                {"image_id": i.image_id, "filename": i.filename, "role": i.role,
                 "width": i.width, "height": i.height}
                for i in self.images
            ],
            "parts_detected": parts_detected,
            "surface_defects_detected": surface_defects,
            "tire_defects_detected": tire_defects,
            "unmatched_defects": unmatched_payload,
            "summary": summary,
        }

    # compact payload, for Agent[Claude-haiku]
    def to_agent_payload(self) -> dict[str, Any]:
        
        defects: list[dict[str, Any]] = []
        unlocated = 0

        for img in self.images:
            
            severities = iter(img.severities)
            
            for match in img.matched:
                
                sev = next(severities)
                
                defects.append({
                    "pieza": TYRE_PIEZA if img.role == "tire" else match.pieza,
                    "tipo_defecto": match.defect.class_name,
                    "severidad": sev.severidad,
                    "confidence": round(match.defect.confidence, 3),
                    "severity_basis": sev.basis,
                    "bbox_normalized": match.defect.bbox_normalized(img.width, img.height),
                })
            for defect in img.unmatched:
                
                sev = next(severities)
                # A tyre defect is never "unlocated" -- the part is known even
                # though no parts model ran.
                if img.role == "tire":
                    
                    defects.append({
                        "pieza": TYRE_PIEZA,
                        "tipo_defecto": defect.class_name,
                        "severidad": sev.severidad,
                        "confidence": round(defect.confidence, 3),
                        "severity_basis": sev.basis,
                        "bbox_normalized": defect.bbox_normalized(img.width, img.height),
                    })
                    
                else:
                    unlocated += 1

        payload: dict[str, Any] = {
            "vehicle_info": self.vehicle_info,
            "defects": defects,
            "defectos_sin_ubicar": unlocated,
        }
        # Only mention healthy tyres when tyres were actually inspected;
        # otherwise the agent could claim a check that never happened.
        ok = sum(len(i.positives) for i in self.images)
        
        if self.tires_inspection_requested:
            
            payload["llantas_sin_defecto"] = ok
            
        return payload

    def _severity_counts(self) -> dict[str, int]:
        
        counts: dict[str, int] = {}
        
        for img in self.images:
            
            for sev in img.severities:
                
                counts[sev.severidad] = counts.get(sev.severidad, 0) + 1
                
        return counts

    @property
    def total_defects(self) -> int:
        
        return sum(len(i.matched) + len(i.unmatched) for i in self.images)


def analyze_surface_image(path: str | Path, image_id: str) -> AnalyzedImage:
    """Parts + defects + spatial match + severity for one body photo."""
    settings = get_settings()
    tensor, params, original = preprocess(path)
    height, width = original.shape[:2]

    parts_model = get_model(ModelKind.CAR_PARTS)
    defects_model = get_model(ModelKind.CAR_DEFECTS)

    parts = postprocess_segmentation(
        parts_model.run(tensor), parts_model.meta, params,
        conf_threshold=settings.det_confidence_threshold,
        iou_threshold=settings.nms_iou_threshold, image_id=image_id,
    )
    defects = postprocess_segmentation(
        defects_model.run(tensor), defects_model.meta, params,
        conf_threshold=settings.det_confidence_threshold,
        iou_threshold=settings.nms_iou_threshold, image_id=image_id,
    )
    matched, unmatched = match_defects_to_parts(defects, parts)

    result = AnalyzedImage(
        image_id=image_id, filename=Path(path).name, role="body",
        width=width, height=height,
        parts=parts, matched=matched, unmatched=unmatched,
    )
    result.severities = [
        severity_for_match(m, result.image_area) for m in matched
    ] + [
        severity_for_image_relative(d.class_name, 
                                    d.area_px, 
                                    result.image_area
                                    )
        for d in unmatched
    ]
    logger.info(
        "%s: %d part(s), %d defect(s) (%d matched, %d unlocated)",
        result.filename, 
        len(parts), 
        len(defects), 
        len(matched), 
        len(unmatched),
    )
    
    return result


def analyze_tyre_image(path: str | Path, image_id: str) -> AnalyzedImage:
    """Tyre defects for one wheel photo. No parts model, no masks."""
    settings = get_settings()
    tensor, params, original = preprocess(path)
    height, width = original.shape[:2]

    model = get_model(ModelKind.TYRES)
    detections = postprocess_detection(
        model.run(tensor), model.meta, params,
        conf_threshold=settings.det_confidence_threshold,
        iou_threshold=settings.nms_iou_threshold, image_id=image_id,
    )
    defects, positives = split_findings(detections)

    result = AnalyzedImage(
        image_id=image_id, filename=Path(path).name, role="tire",
        width=width, height=height,
        unmatched=defects,     # no parts model, so nothing to match against
        positives=positives,
    )
    result.severities = [
        severity_for_tyre(d.class_name, d.area_px, result.image_area)
        for d in defects
    ]
    logger.info(
        "%s: %d tyre defect(s), %d healthy reading(s)",
        result.filename, len(defects), len(positives),
    )
    return result


# MASTER ORCHESTRATOR
def run_inspection(
    surface_images: list[str | Path] | None = None,
    tyre_images: list[str | Path] | None = None,
    *,
    vehicle_info: dict[str, Any] | None = None,
    inspection_id: str | None = None,
    progress: ProgressFn | None = None,
) -> InspectionResult:
    """
    Run the whole vision stage.

    `progress(step_id, status)` mirrors `SessionStore.set_step`, so a router can
    pass `lambda s, st: session_store.set_step(sid, s, st)` and drive the SPA's
    progress UI without this module knowing sessions exist.
    """
    surface_images = list(surface_images or [])
    tyre_images = list(tyre_images or [])
    
    if not surface_images and not tyre_images:
        
        raise NoDetectionsError(
            detail="No hay imagenes para analizar.",
            log_message="run_inspection called with no images",
        )

    def step(step_id: str, status: str) -> None:
        
        if progress:
            
            progress(step_id, status)

    result = InspectionResult(
        inspection_id=inspection_id or str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        vehicle_info=vehicle_info or {},
        tires_inspection_requested=bool(tyre_images),
    )

    step("upload", "done")

    if surface_images:
        # Both segmentation models and the match run per image; the SPA shows
        # them as three steps, so they are marked around the whole surface pass.
        step("vision_parts", "running")
        step("vision_defects", "running")
        
        for index, path in enumerate(surface_images):
            
            result.images.append(
                analyze_surface_image(path, image_id=f"img_{index + 1}")
            )
            
        step("vision_parts", "done")
        step("vision_defects", "done")
        step("spatial_match", "done")

    if tyre_images:
        
        step("vision_tires", "running")
        
        offset = len(result.images)
        
        for index, path in enumerate(tyre_images):
            
            result.images.append(
                analyze_tyre_image(path, 
                                   image_id=f"img_{offset + index + 1}"
                                   )
            )
        step("vision_tires", "done")

    logger.info(
        "Inspection %s: %d image(s), %d defect(s).",
        result.inspection_id, 
        len(result.images), 
        result.total_defects,
    )
    
    return result
