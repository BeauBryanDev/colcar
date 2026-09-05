
from __future__ import annotations

import logging

import numpy as np

from app.rag.vocabulary import is_defect_class
from app.vision.nms import class_aware_nms, xywh2xyxy
from app.vision.onnx_infer import ModelMeta
from app.vision.postprocess_seg import Detection # came from seg model even tough it is obj det

logger = logging.getLogger(__name__)

# Decode YOLO11m detection output into boxes.
# output0  (1, 4 + nc, 8400)     boxes + class scores. 

def postprocess_detection(
    outputs: list[np.ndarray],
    meta: ModelMeta,
    params,  # LetterboxParams; untyped to avoid a needless import cycle
    *,
    conf_threshold: float = 0.25,
    iou_threshold: float = 0.45,
    max_detections: int = 100,
    image_id: str = "",
) -> list[Detection]:
    """
    Decode raw detection outputs into Detections in original image space.

    Returns every class the model emitted, `Good` included -- filtering is the
    caller's decision, via `split_findings`.
    """
    output0 = outputs[0]

    # (1, 4+nc, 8400) -> (8400, 4+nc)
    preds = np.squeeze(output0, axis=0).T
    nc = meta.num_classes
    boxes_xywh = preds[:, :4]
    class_scores = preds[:, 4 : 4 + nc]

    # YOLO11 has no separate objectness term: the class score is the confidence.
    class_ids = class_scores.argmax(axis=1)
    confidences = class_scores[np.arange(len(class_scores)), class_ids]
    keep = confidences >= conf_threshold
    
    if not keep.any():
        logger.debug("%s: no detections above %.2f", meta.path.name, conf_threshold)
        return []

    boxes_net = xywh2xyxy(boxes_xywh[keep])
    confidences = confidences[keep]
    class_ids = class_ids[keep]

    selected = class_aware_nms(
        boxes_net, confidences, class_ids,
        iou_threshold=iou_threshold, max_detections=max_detections,
    )
    boxes_orig = params.unletterbox_boxes(boxes_net[selected])

    detections = [
        Detection(
            class_id=int(class_ids[selected[i]]),
            class_name=meta.name_of(int(class_ids[selected[i]])),
            confidence=float(confidences[selected[i]]),
            bbox=tuple(float(v) for v in boxes_orig[i]),  # type: ignore[arg-type]
            mask=None,
            image_id=image_id,
            detection_id=f"{image_id or 'img'}_{meta.kind.value}_{i}",
        )
        for i in range(len(selected))
    ]
    logger.debug(
        "%s: %d candidates -> %d after conf -> %d after NMS",
        meta.path.name, len(preds), int(keep.sum()), len(detections),
    )
    return detections


def split_findings(
    detections: list[Detection],
) -> tuple[list[Detection], list[Detection]]:
    """Separate real defects from positive findings.

    """
    defects = [d for d in detections if is_defect_class(d.class_name)]
    positives = [d for d in detections if not is_defect_class(d.class_name)]
    
    return defects, positives
