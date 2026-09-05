
from __future__ import annotations

import numpy as np

# Non-maximum suppression and IoU geometry, in pure numpy

__all__ = [
    "xywh2xyxy", "box_area", "box_iou", "box_iou_matrix",
    "mask_iou", "nms", "class_aware_nms", "intersection_over_smaller",
]
# Manually written rather than pulled from torchvision: the only reason torch is
# installed is the bge-m3 encoder, and importing it into the request path to
# suppress a few hundred boxes would be absurd. These operate on arrays of at
# most 8400 rows, where numpy is entirely adequate.

def xywh2xyxy(boxes: np.ndarray) -> np.ndarray:
    """YOLO emits centre-x, centre-y, width, height; everything else wants xyxy."""
    out = np.empty_like(boxes)
    half_w, half_h = boxes[:, 2] / 2, boxes[:, 3] / 2
    out[:, 0] = boxes[:, 0] - half_w
    out[:, 1] = boxes[:, 1] - half_h
    out[:, 2] = boxes[:, 0] + half_w
    out[:, 3] = boxes[:, 1] + half_h
    
    return out


def box_area(boxes: np.ndarray) -> np.ndarray:
    """Areas of (N, 4) xyxy boxes. Degenerate boxes clamp to 0, not negative."""
    if boxes.size == 0:
        return np.zeros((0,), dtype=np.float32)
    
    w = np.clip(boxes[:, 2] - boxes[:, 0], 0, None)
    h = np.clip(boxes[:, 3] - boxes[:, 1], 0, None)
    
    return w * h


def box_iou(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    """IoU of one box against many. Returns (N,)."""
    if boxes.size == 0:
        return np.zeros((0,), dtype=np.float32)
    
    x0 = np.maximum(box[0], boxes[:, 0])
    y0 = np.maximum(box[1], boxes[:, 1])
    x1 = np.minimum(box[2], boxes[:, 2])
    y1 = np.minimum(box[3], boxes[:, 3])
    
    inter = np.clip(x1 - x0, 0, None) * np.clip(y1 - y0, 0, None)
    union = box_area(box[None, :])[0] + box_area(boxes) - inter
    # union == 0 only for degenerate boxes; avoid the warning and return 0.
    return np.where(union > 0, inter / np.maximum(union, 1e-9), 0.0)

# boxes are `xyxy` float arrays of shape (N, 4)...

def box_iou_matrix(a: np.ndarray, 
                   b: np.ndarray
                   ) -> np.ndarray:
    """Full (Na, Nb) IoU matrix -- used by spatial matching, not by NMS."""
    if a.size == 0 or b.size == 0:
        return np.zeros((len(a), len(b)), dtype=np.float32)
    
    x0 = np.maximum(a[:, None, 0], b[None, :, 0])
    y0 = np.maximum(a[:, None, 1], b[None, :, 1])
    x1 = np.minimum(a[:, None, 2], b[None, :, 2])
    y1 = np.minimum(a[:, None, 3], b[None, :, 3])
    
    inter = np.clip(x1 - x0, 0, None) * np.clip(y1 - y0, 0, None)
    union = box_area(a)[:, None] + box_area(b)[None, :] - inter
    
    return np.where(union > 0, inter / np.maximum(union, 1e-9), 0.0)


def intersection_over_smaller(a: np.ndarray,
                              b: np.ndarray
                              ) -> np.ndarray:
    """
    (Na, Nb) intersection divided by the *smaller* box's area.

    Plain IoU is the wrong measure when one box is contained in a much larger
    one -- a 20 px scratch inside a whole door scores near-zero IoU despite
    being entirely on that door. Spatial matching needs containment, not
    overlap; this is that measure.
    """
    if a.size == 0 or b.size == 0:
        return np.zeros((len(a), len(b)), dtype=np.float32)
    
    x0 = np.maximum(a[:, None, 0], b[None, :, 0])
    y0 = np.maximum(a[:, None, 1], b[None, :, 1])
    x1 = np.minimum(a[:, None, 2], b[None, :, 2])
    y1 = np.minimum(a[:, None, 3], b[None, :, 3])
    
    inter = np.clip(x1 - x0, 0, None) * np.clip(y1 - y0, 0, None)
    smaller = np.minimum(box_area(a)[:, None], box_area(b)[None, :])
    
    return np.where(smaller > 0, inter / np.maximum(smaller, 1e-9), 0.0)


def mask_iou(masks_a: np.ndarray, masks_b: np.ndarray) -> np.ndarray:
    """
    (Na, Nb) IoU over boolean masks.

    More faithful than box IoU for segmentation -- two diagonal scratches can
    have heavily overlapping boxes while sharing almost no pixels. Flattened to
    a matmul, which is far quicker than looping pairs.
    """
    if masks_a.size == 0 or masks_b.size == 0:
        return np.zeros((len(masks_a), len(masks_b)), dtype=np.float32)
    
    a = masks_a.reshape(len(masks_a), -1).astype(np.float32)
    b = masks_b.reshape(len(masks_b), -1).astype(np.float32)
    
    inter = a @ b.T
    area_a, area_b = a.sum(1)[:, None], b.sum(1)[None, :]
    union = area_a + area_b - inter
    
    return np.where(union > 0, inter / np.maximum(union, 1e-9), 0.0)


def nms(
    boxes: np.ndarray,
    scores: np.ndarray,
    iou_threshold: float = 0.45,
    *,
    masks: np.ndarray | None = None,
    max_detections: int | None = None,
) -> np.ndarray:
    """Greedy NMS. Returns kept indices, highest score first.

    Take the best-scoring box, suppress everything overlapping it beyond the
    threshold, repeat. When `masks` is supplied, overlap is measured on pixels
    instead of boxes.
    """
    if boxes.size == 0:
        return np.empty((0,), dtype=np.int64)

    order = scores.argsort()[::-1]
    keep: list[int] = []

    while order.size > 0:
        
        best = int(order[0])
        keep.append(best)
        
        if order.size == 1 or (max_detections and len(keep) >= max_detections):
            break

        rest = order[1:]
        
        if masks is not None:
            
            overlap = mask_iou(masks[best : best + 1], masks[rest])[0]
            
        else:
            
            overlap = box_iou(boxes[best], boxes[rest])
            
        order = rest[overlap <= iou_threshold]

    return np.asarray(keep, dtype=np.int64)


def class_aware_nms(
    boxes: np.ndarray,
    scores: np.ndarray,
    class_ids: np.ndarray,
    iou_threshold: float = 0.45,
    *,
    masks: np.ndarray | None = None,
    max_detections: int | None = None,
) -> np.ndarray:
    """
    NMS that never suppresses across classes.

    A scratch and a dent can legitimately occupy the same region of a panel, and
    a door overlaps the car body it belongs to. Suppressing between classes
    would delete one of them. Implemented with the standard coordinate-offset
    trick: shifting each class into its own region of the plane makes
    cross-class IoU structurally zero, so one pass does the whole job.
    """
    if boxes.size == 0:
        return np.empty((0,), dtype=np.int64)

    if masks is not None:
        # Pixel overlap cannot be offset, so run per class instead.
        keep: list[int] = []
        
        for cls in np.unique(class_ids):
            
            idx = np.nonzero(class_ids == cls)[0]
            sel = nms(boxes[idx], scores[idx], iou_threshold, masks=masks[idx])
            keep.extend(idx[sel].tolist())
            
        keep_arr = np.asarray(keep, dtype=np.int64)
        keep_arr = keep_arr[scores[keep_arr].argsort()[::-1]]
        
        return keep_arr[:max_detections] if max_detections else keep_arr

    offset = (boxes.max() + 1.0) if boxes.size else 1.0
    shifted = boxes + (class_ids.astype(np.float32) * offset)[:, None]
    
    return nms(shifted, scores, iou_threshold, max_detections=max_detections)
