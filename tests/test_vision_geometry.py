"""Geometry: boxes, NMS, letterbox, detection decode, spatial matching."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.core.exceptions import InvalidUploadError, UploadTooLargeError
from app.vision.nms import (
    box_area,
    box_iou,
    class_aware_nms,
    intersection_over_smaller,
    mask_iou,
    nms,
    xywh2xyxy,
)
from app.vision.onnx_infer import ModelKind, ModelMeta
from app.vision.postprocess_det import postprocess_detection, split_findings
from app.vision.preprocess import PAD_VALUE, letterbox, validate_upload
from app.vision.spatial_match import match_defects_to_parts


def test_xywh2xyxy_and_degenerate_area():
    boxes = np.array([[50.0, 50.0, 20.0, 10.0]], dtype=np.float32)
    assert xywh2xyxy(boxes).tolist() == [[40.0, 45.0, 60.0, 55.0]]
    assert box_area(np.array([[10.0, 10.0, 5.0, 5.0]], dtype=np.float32))[0] == 0.0


def test_box_iou_on_identical_disjoint_and_overlapping():
    box = np.array([0.0, 0.0, 10.0, 10.0], dtype=np.float32)
    others = np.array(
        [[0.0, 0.0, 10.0, 10.0], [20.0, 20.0, 30.0, 30.0], [0.0, 0.0, 10.0, 5.0]],
        dtype=np.float32,
    )
    result = box_iou(box, others)
    assert result[0] == pytest.approx(1.0)
    assert result[1] == pytest.approx(0.0)
    assert result[2] == pytest.approx(0.5)


def test_containment_is_one_for_a_small_box_inside_a_large_one():
    scratch = np.array([[10.0, 10.0, 20.0, 20.0]], dtype=np.float32)
    door = np.array([[0.0, 0.0, 400.0, 400.0]], dtype=np.float32)
    assert intersection_over_smaller(scratch, door)[0, 0] == pytest.approx(1.0)
    assert box_iou(scratch[0], door)[0] < 0.01


def test_nms_suppresses_only_above_the_threshold():
    boxes = np.array(
        [[0.0, 0.0, 10.0, 10.0], [0.0, 0.0, 10.0, 9.0]], dtype=np.float32
    )
    scores = np.array([0.9, 0.8], dtype=np.float32)
    assert nms(boxes, scores, 0.45).tolist() == [0]
    assert sorted(nms(boxes, scores, 0.95).tolist()) == [0, 1]


def test_class_aware_nms_keeps_overlapping_classes():
    boxes = np.array(
        [[0.0, 0.0, 10.0, 10.0], [0.0, 0.0, 10.0, 10.0]], dtype=np.float32
    )
    scores = np.array([0.9, 0.8], dtype=np.float32)
    same = class_aware_nms(boxes, scores, np.array([0, 0]))
    different = class_aware_nms(boxes, scores, np.array([0, 1]))
    assert same.tolist() == [0]
    assert sorted(different.tolist()) == [0, 1]


def test_mask_iou_matches_the_box_result_for_rectangles():
    a = np.zeros((1, 20, 20), dtype=bool)
    b = np.zeros((1, 20, 20), dtype=bool)
    a[0, 0:10, 0:10] = True
    b[0, 0:10, 0:5] = True
    assert mask_iou(a, b)[0, 0] == pytest.approx(0.5)


def test_letterbox_pads_to_the_net_size_preserving_aspect():
    image = np.zeros((200, 400, 3), dtype=np.uint8)
    padded, params = letterbox(image, (640, 640))
    assert padded.shape == (640, 640, 3)
    assert params.ratio == pytest.approx(1.6)
    ## Padding sits on the top and bottom rows.
    assert int(padded[0, 320, 0]) == PAD_VALUE


def test_unletterbox_inverts_the_transform():
    image = np.zeros((200, 400, 3), dtype=np.uint8)
    _, params = letterbox(image, (640, 640))
    original = np.array([[10.0, 20.0, 300.0, 150.0]], dtype=np.float32)

    forward = original * params.ratio
    forward[:, [0, 2]] += params.pad_x
    forward[:, [1, 3]] += params.pad_y
    back = params.unletterbox_boxes(forward)

    assert np.allclose(back, original, atol=1.0)
    x0, y0, x1, y1 = params.content_box
    assert (x1 - x0, y1 - y0) == (640, 320)


def test_validate_upload_gates_type_and_size(settings):
    validate_upload("a.jpg", "image/jpeg", 1024)
    validate_upload("a.webp", "image/webp", 1024)
    with pytest.raises(InvalidUploadError):
        validate_upload("a.mp4", "video/mp4", 1024)
    with pytest.raises(UploadTooLargeError):
        validate_upload("a.jpg", "image/jpeg", settings.max_upload_bytes + 1)


def test_detection_decode_filters_and_splits_positive_findings():
    names = {0: "Good", 1: "Bulge"}
    meta = ModelMeta(
        kind=ModelKind.TYRES,
        path=Path("tyres_defect_model.onnx"),
        task="detect",
        input_name="images",
        imgsz=(640, 640),
        class_names=names,
        channels=6,
        has_proto=False,
    )
    ## Two candidates above threshold, one below.
    raw = np.zeros((1, 6, 3), dtype=np.float32)
    raw[0, :4, 0] = [100, 100, 40, 40]
    raw[0, :4, 1] = [300, 300, 40, 40]
    raw[0, :4, 2] = [500, 500, 40, 40]
    raw[0, 4, 0] = 0.9
    raw[0, 5, 1] = 0.8
    raw[0, 4, 2] = 0.1

    _, params = letterbox(np.zeros((640, 640, 3), dtype=np.uint8), (640, 640))
    detections = postprocess_detection([raw], meta, params, image_id="img_1")
    defects, positives = split_findings(detections)

    assert len(detections) == 2
    assert all(d.mask is None for d in detections)
    assert [d.class_name for d in defects] == ["Bulge"]
    assert [d.class_name for d in positives] == ["Good"]


def test_spatial_matching_gates_containment_specificity_and_affinity(make_detection):
    ## Containment 0.406 and 0.556, the two values measured on real photos.
    below = make_detection("scratch", (0, 0, 100, 100), with_mask=True)
    part_below = make_detection("hood", (0, 0, 100, 41), with_mask=True)
    matched, unmatched = match_defects_to_parts([below], [part_below])
    assert matched == []
    assert unmatched == [below]

    above = make_detection("scratch", (0, 0, 100, 100), with_mask=True)
    part_above = make_detection("hood", (0, 0, 100, 56), with_mask=True)
    matched, unmatched = match_defects_to_parts([above], [part_above])
    assert unmatched == []
    assert matched[0].containment >= 0.55

    ## Smallest containing part wins.
    dent = make_detection("dent", (10, 10, 30, 30), with_mask=True)
    wide = make_detection("back_door", (0, 0, 300, 300), with_mask=True)
    narrow = make_detection("back_left_door", (0, 0, 120, 120), with_mask=True)
    matched, _ = match_defects_to_parts([dent], [wide, narrow])
    assert matched[0].pieza == "back_left_door"

    ## Affinity beats geometry: a lamp defect never lands on a door.
    lamp = make_detection("lamp_broken", (10, 10, 30, 30), with_mask=True)
    matched, unmatched = match_defects_to_parts([lamp], [narrow])
    assert matched == []
    assert unmatched == [lamp]
