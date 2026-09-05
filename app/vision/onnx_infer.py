
from __future__ import annotations

import ast
import logging
import time
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort

from app.core.config import Settings, get_settings
from app.core.exceptions import VisionModelError

logger = logging.getLogger(__name__)

MASK_COEFF_COUNT = 32  # YOLO segmentation head, fixed by the architecture
# ONNX Runtime session management for the three YOLO11m models.

class ModelKind(str, Enum):
    """
    The three models. Values match the SPA's `DetectionModel` where they
    overlap, so a router can map an upload panel straight onto a model."""

    CAR_PARTS = "vehicle_parts"
    CAR_DEFECTS = "surface_defects"
    TYRES = "tires_wheels"

# Class names, image size and task are read from the ONNX
# metadata rather than hardcoded, so retraining a model with different classes
# does not silently desynchronise this file from the weights.

@dataclass(frozen=True)
class ModelMeta:
    kind: ModelKind
    path: Path
    task: str  # "segment" | "detect"
    input_name: str
    imgsz: tuple[int, int]  # (height, width)
    class_names: dict[int, str]
    channels: int  # output0 rows
    has_proto: bool

    @property
    def num_classes(self) -> int:
        return len(self.class_names)

    def name_of(self, class_id: int) -> str:
        return self.class_names.get(class_id, f"class_{class_id}")

# Model geometry, read from the files themselves:

# car_parts     segment  [1,59,8400] + [1,32,160,160]  x23 classes
# car_defects   segment  [1,42,8400] + [1,32,160,160]   x6 classes
# tyres_defect  detect   [1,10,8400]    x6 classes

# The channel count is `4 bbox + n_classes + 32 mask coefficients` for the
# segmentation models, and `4 + n_classes` for the detection one
# (`[1,10,8400]` is the input shape).

class OnnxModel:
    """One loaded ONNX model plus its parsed metadata."""

    def __init__(self, kind: ModelKind, path: Path, settings: Settings) -> None:
        if not path.exists():
            raise VisionModelError(
                log_message=f"model file missing: {path}",
            )
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        # CPU-only box: leave thread counts to ORT unless configured, but keep
        # inference single-session so concurrent requests queue rather than
        # oversubscribe the cores.
        if settings.onnx_intra_op_threads:
            opts.intra_op_num_threads = settings.onnx_intra_op_threads

        t0 = time.perf_counter()
        try:
            self.session = ort.InferenceSession(
                str(path), 
                sess_options=opts, 
                providers=["CPUExecutionProvider"]
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a domain error
            raise VisionModelError(
                log_message=f"failed to load {path.name}: {exc}"
            ) from exc

        self.meta = self._parse_meta(kind, path)
        logger.info(
            "Loaded %s (%s, %d classes) in %.2fs",
            path.name, 
            self.meta.task, 
            self.meta.num_classes,
            time.perf_counter() - t0,
        )

    def _parse_meta(self, kind: ModelKind, path: Path) -> ModelMeta:
        raw: dict[str, str] = self.session.get_modelmeta().custom_metadata_map
        inp = self.session.get_inputs()[0]
        outs = self.session.get_outputs()

        class_names = self._parse_names(raw.get("names", ""))
        imgsz = self._parse_imgsz(raw.get("imgsz", ""), inp.shape)

        channels = outs[0].shape[1]
        channels = int(channels) if isinstance(channels, int) else -1
        # Proto branch present == mask coefficients in output0.
        has_proto = len(outs) > 1
        
        if has_proto and channels > 0:
            
            expected = 4 + len(class_names) + MASK_COEFF_COUNT
            
            if channels != expected:
                
                logger.warning(
                    "%s: output0 has %d channels, expected %d "
                    "(4 bbox + %d classes + %d mask coeffs)",
                    path.name, channels, expected, len(class_names),
                    MASK_COEFF_COUNT,
                )

        return ModelMeta(
            kind=kind,
            path=path,
            task=raw.get("task", "segment" if has_proto else "detect"),
            input_name=inp.name,
            imgsz=imgsz,
            class_names=class_names,
            channels=channels,
            has_proto=has_proto,
        )

    @staticmethod
    def _parse_names(raw: str) -> dict[int, str]:
        """Ultralytics stores `names` as a stringified dict.

        `literal_eval`, never `eval`: this parses a string embedded in a model
        file, which is untrusted input if the weights ever come from elsewhere.
        """
        if not raw:
            return {}
        
        try:
            parsed = ast.literal_eval(raw)
            
        except (ValueError, SyntaxError):
            
            logger.warning("Could not parse class names from model metadata.")
            return {}
        
        if isinstance(parsed, dict):
            
            return {int(k): str(v) for k, v in parsed.items()}
        
        if isinstance(parsed, (list, tuple)):
            
            return {i: str(v) for i, v in enumerate(parsed)}
        
        return {}

    @staticmethod
    def _parse_imgsz(raw: str, 
                     input_shape: list[Any]
                     ) -> tuple[int, int]:
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, (list, tuple)) and len(parsed) == 2:
                return int(parsed[0]), int(parsed[1])
            
            if isinstance(parsed, int):
                return parsed, parsed
            
        except (ValueError, SyntaxError):
            pass
        
        # Fall back to the graph's own input shape.
        h, w = input_shape[2], input_shape[3]
        
        return (int(h) if isinstance(h, int) else 640,
                int(w) if isinstance(w, int) else 640)

    #  INFERENCE
    def run(self, tensor: np.ndarray) -> list[np.ndarray]:
        """
        Run inference on a preprocessed NCHW float32 batch.

        Returns raw outputs: `[output0]` for detection, `[output0, proto]` for
        segmentation. Decoding lives in postprocess_det / postprocess_seg.
        """
        if tensor.dtype != np.float32:
            tensor = tensor.astype(np.float32)
            
        try:
            return self.session.run(None, {self.meta.input_name: tensor})
        
        except Exception as exc:  # noqa: BLE001
            
            raise VisionModelError(
                log_message=f"inference failed on {self.meta.path.name}: {exc}"
            ) from exc


def _model_path(kind: ModelKind, 
                settings: Settings
                ) -> Path:
    
    return {
        ModelKind.CAR_PARTS: settings.car_parts_model_path,
        ModelKind.CAR_DEFECTS: settings.car_defects_model_path,
        ModelKind.TYRES: settings.tyres_defect_model_path,
    }[kind]


@lru_cache(maxsize=len(ModelKind))
def get_model(kind: ModelKind) -> OnnxModel:
    """Load-once accessor. Raises `VisionModelError` if the file is unusable."""
    settings = get_settings()
    
    return OnnxModel(kind, _model_path(kind, settings), settings)


def warmup(kinds: tuple[ModelKind, ...] | None = None) -> None:
    """
    Load models and run one dummy inference each.

    Call from the FastAPI lifespan handler: the first real inference otherwise
    pays both the load and ORT's lazy kernel initialisation, which shows up as a
    slow first inspection rather than a slow startup.
    """
    for kind in kinds or tuple(ModelKind):
        
        model = get_model(kind)
        h, w = model.meta.imgsz
        
        model.run(np.zeros((1, 3, h, w), 
                           dtype=np.float32
                           )
                  )
        logger.info("Warmed up %s.",
                    model.meta.path.name
                    )


def describe_models() -> list[dict[str, Any]]:
    """Diagnostics for the health endpoint."""
    out: list[dict[str, Any]] = []
    
    for kind in ModelKind:
        
        try:
            m = get_model(kind).meta
            out.append({
                "kind": kind.value, 
                "file": m.path.name, 
                "task": m.task,
                "classes": m.num_classes, 
                "imgsz": list(m.imgsz),
                "loaded": True,
            })
            
        except VisionModelError as exc:
            
            out.append({"kind": kind.value, 
                        "loaded": False,
                        "error": exc.log_message}
                       )
            
            
    return out
