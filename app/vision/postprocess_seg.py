
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from app.vision.nms import class_aware_nms, xywh2xyxy
from app.vision.onnx_infer import MASK_COEFF_COUNT, ModelMeta
from app.vision.preprocess import LetterboxParams

logger = logging.getLogger(__name__)
# Decode YOLO11m-seg output into boxes, masks and polygons.
# Prototype activations are logits; 0.5 after sigmoid is the usual cut.
MASK_BINARY_THRESHOLD = 0.5
# Contour simplification tolerance, as a fraction of the contour's perimeter.
# Keeps polygons small enough to ship to the frontend without losing shape.
POLYGON_EPSILON_RATIO = 0.004

@dataclass
class Detection:
    """
    One detected instance, in ORIGINAL image coordinates.

    Shared by both postprocessors: the tyre model produces these with
    `mask=None`, so anything consuming detections must treat the mask as
    optional rather than assume segmentation.
    """
    class_id: int
    class_name: str
    confidence: float
    bbox: tuple[float, float, float, float]        # xyxy, original image space
    mask: np.ndarray | None = None                 # bool (H, W), original size
    mask_area_px: int = 0
    polygon: list[list[int]] = field(default_factory=list)
    image_id: str = ""
    detection_id: str = ""
    # output0  (1, 4 + nc + 32, 8400)    boxes, class scores, mask coefficients
    # output1  (1, 32, 160, 160)         mask prototypes
    @property
    def bbox_area(self) -> float:
        
        x0, y0, x1, y1 = self.bbox
        
        return max(0.0, x1 - x0) * max(0.0, y1 - y0)

    @property
    def area_px(self) -> float:
        """
        Mask area when segmented, else box area.

        Severity is an area ratio, so this is what it divides -- mask area is
        far more honest than a bounding box for a diagonal scratch, where the
        box can be several times the actual damaged surface.
        """
        return float(self.mask_area_px) if self.mask is not None else self.bbox_area

    def bbox_normalized(self, width: int, height: int) -> list[float]:
        
        x0, y0, x1, y1 = self.bbox
        
        return [round(x0 / width, 4), 
                round(y0 / height, 4),
                round(x1 / width, 4), 
                round(y1 / height, 4)
                ]

    def to_payload(self, width: int, height: int) -> dict[str, Any]:
        
        payload: dict[str, Any] = {
            "detection_id": self.detection_id,
            "image_id": self.image_id,
            "class_name": self.class_name,
            "confidence": round(self.confidence, 4),
            "bbox": [round(v, 2) for v in self.bbox],
            "bbox_normalized": self.bbox_normalized(width, height),
        }
        
        if self.mask is not None:
            
            payload["mask_area_px"] = self.mask_area_px
            payload["segmentation_polygon"] = self.polygon
            payload["polygon_format"] = "xy_absolute_pixels"
            
            
        return payload

# The mask for one detection is a linear combination of the 32 prototypes,
# weighted by that detection's 32 coefficients, squashed through a sigmoid:
# mask = sigmoid(coeffs @ proto.reshape(32, 160*160)).reshape(160, 160)
def _sigmoid(x: np.ndarray) -> np.ndarray:
    """Overflow-safe sigmoid.

    Prototype logits reach +-30 or so; plain `1/(1+exp(-x))` warns and returns
    nan for large negatives, which would silently poison mask areas.
    """
    return np.where(
        x >= 0,
        1.0 / (1.0 + np.exp(-np.clip(x, -60, 60))),
        np.exp(np.clip(x, -60, 60)) / (1.0 + np.exp(np.clip(x, -60, 60))),
    )


def _build_masks(
    coeffs: np.ndarray,
    proto: np.ndarray,
    boxes_orig: np.ndarray,
    params: LetterboxParams,
) -> tuple[list[np.ndarray], list[int], list[list[list[int]]]]:
    """Turn mask coefficients into full-resolution boolean masks.

    coeffs     (n, 32)             per-detection prototype weights
    proto     (32, ph, pw)        prototype bank, typically 160x160
    boxes_orig (n, 4) xyxy         boxes in ORIGINAL image space
    """
    n = len(coeffs)
    ch, ph, pw = proto.shape

    # The whole mask computation, vectorised: (n, 32) @ (32, ph*pw) -> (n, ph*pw)
    mask_logits = coeffs @ proto.reshape(ch, -1)
    masks_proto = _sigmoid(mask_logits).reshape(n, ph, pw)
    # transpose to (8400, 4+nc+32) -- ONNX gives channels-first
    masks: list[np.ndarray] = []
    areas: list[int] = []
    polygons: list[list[list[int]]] = []
    # prototypes are global and leak activation
    cx0, cy0, cx1, cy1 = params.content_box

    for i in range(n):
        # Prototype -> letterbox resolution, then strip the padding. The
        # padding is discarded before the final resize so its (near-zero)
        # activation cannot bleed into the image region.
        m_net = cv2.resize(masks_proto[i], 
                           (params.net_w, 
                            params.net_h),
                           interpolation=cv2.INTER_LINEAR
                           )
        m_content = m_net[cy0:cy1, cx0:cx1]
        
        if m_content.size == 0:
            
            masks.append(np.zeros((params.orig_h, params.orig_w), dtype=bool))
            areas.append(0)
            polygons.append([])
            continue

        # Letterbox content -> original resolution. Because the padding is
        # already gone, this maps exactly onto the source image.
        m_orig = cv2.resize(m_content, 
                            (params.orig_w, 
                             params.orig_h),
                            interpolation=cv2.INTER_LINEAR
                            )
        
        #  Crop to this detection's own box, at full resolution against the
        # very box that gets reported. Prototypes are global -- a door's mask
        # carries activation over neighbouring doors -- so without this crop one
        # instance absorbs its neighbours.
        bx0, by0, bx1, by1 = boxes_orig[i]
        x0, y0 = int(np.floor(bx0)), int(np.floor(by0))
        x1, y1 = int(np.ceil(bx1)), int(np.ceil(by1))
        x0, y0 = max(x0, 0), max(y0, 0)
        x1 = min(x1, params.orig_w)
        y1 = min(y1, params.orig_h)
        
        if x1 <= x0 or y1 <= y0:
            
            masks.append(np.zeros((params.orig_h, params.orig_w), dtype=bool))
            areas.append(0)
            polygons.append([])
            continue

        binary = np.zeros((params.orig_h, params.orig_w), dtype=bool)
        binary[y0:y1, x0:x1] = m_orig[y0:y1, x0:x1] >= MASK_BINARY_THRESHOLD

        masks.append(binary)
        areas.append(int(binary.sum()))
        polygons.append(_mask_to_polygon(binary))

    return masks, areas, polygons


def _mask_to_polygon(mask: np.ndarray) -> list[list[int]]:
    """Largest contour of a mask, simplified. Empty when the mask is blank.

    Only the largest is kept: a fragmented mask would otherwise ship several
    disjoint blobs, and the frontend draws a single outline per detection.
    """
    if not mask.any():
        return []
    
    contours, _ = cv2.findContours(
        mask.astype(np.uint8), 
        cv2.RETR_EXTERNAL, 
        cv2.CHAIN_APPROX_SIMPLE
    )
    
    if not contours:
        return []
    
    largest = max(contours, key=cv2.contourArea)
    epsilon = POLYGON_EPSILON_RATIO * cv2.arcLength(largest, True)
    simplified = cv2.approxPolyDP(largest, epsilon, True)
    
    return [[int(p[0][0]), int(p[0][1])] for p in simplified]

#strip letterbox padding, then resize to the original resolution

def postprocess_segmentation(
    outputs: list[np.ndarray],
    meta: ModelMeta,
    params: LetterboxParams,
    *,
    conf_threshold: float = 0.25,
    iou_threshold: float = 0.45,
    max_detections: int = 100,
    image_id: str = "",
    build_masks: bool = True,
) -> list[Detection]:
    """Decode one segmentation model's raw outputs into `Detection`s."""
    output0, proto = outputs[0], outputs[1]

    # 1. (1, 4+nc+32, 8400) -> (8400, 4+nc+32)
    preds = np.squeeze(output0, axis=0).T
    nc = meta.num_classes
    boxes_xywh = preds[:, :4]
    class_scores = preds[:, 4 : 4 + nc]
    coeffs_all = preds[:, 4 + nc : 4 + nc + MASK_COEFF_COUNT]

    # Best class per candidate, then threshold. YOLO11 emits per-class
    # sigmoid scores with no separate objectness term, so the class score *is*
    # the confidence.
    class_ids = class_scores.argmax(axis=1)
    confidences = class_scores[np.arange(len(class_scores)), class_ids]
    keep = confidences >= conf_threshold
    
    if not keep.any():
        return []

    boxes_net = xywh2xyxy(boxes_xywh[keep])
    confidences = confidences[keep]
    class_ids = class_ids[keep]
    coeffs = coeffs_all[keep]

    # NMS on boxes, never across classes.
    selected = class_aware_nms(
        boxes_net,
        confidences, 
        class_ids,
        iou_threshold=iou_threshold, 
        max_detections=max_detections,
    )
    boxes_net = boxes_net[selected]
    confidences = confidences[selected]
    class_ids = class_ids[selected]
    coeffs = coeffs[selected]

    # Undo the letterbox first: masks are cropped against original-space boxes,
    # so the reported bbox and the mask are  to agree.
    boxes_orig = params.unletterbox_boxes(boxes_net)

    # 4. Masks for survivors only.
    if build_masks and len(selected):
        
        masks, areas, polygons = _build_masks(
            coeffs,
            np.squeeze(proto, axis=0), 
            boxes_orig, params
        )
    else:
        masks = [None] * len(selected)   # type: ignore[list-item]
        areas = [0] * len(selected)
        polygons = [[] for _ in range(len(selected))]

    detections = [
        Detection(
            class_id=int(class_ids[i]),
            class_name=meta.name_of(int(class_ids[i])),
            confidence=float(confidences[i]),
            bbox=tuple(float(v) for v in boxes_orig[i]),  # type: ignore[arg-type]
            mask=masks[i],
            mask_area_px=areas[i],
            polygon=polygons[i],
            image_id=image_id,
            detection_id=f"{image_id or 'img'}_{meta.kind.value}_{i}",
        )
        for i in range(len(selected))
    ]
    logger.debug(
        "%s: %d candidates -> %d after conf -> %d after NMS",
        meta.path.name, 
        len(preds), 
        int(keep.sum()), 
        len(detections),
    )
    
    return detections
