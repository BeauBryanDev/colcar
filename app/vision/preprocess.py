"""
Image loading and letterbox preprocessing for the YOLO models.

Shared by all three models -- they all take a 640x640 NCHW float32 batch, so the
tyre (detection) and the two segmentation models preprocess identically. Only
the decoding differs.

"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import get_settings
from app.core.exceptions import InvalidUploadError

logger = logging.getLogger(__name__)

# Ultralytics' letterbox fill. Matches training, so the model sees the padding
# it expects rather than black bars it may read as content.
PAD_VALUE: int = 114
# The letterbox transform is lossy in coordinate space: the image is scaled by one
# ratio and centre-padded, so every box and mask the model returns is in 640x640
# letterbox space, not original-image space. `LetterboxParams` carries the exact
# inverse, and lives here next to the forward transform so the two cannot drift.
# Getting this wrong does not crash -- it silently draws boxes in the wrong place
# and, worse, computes defect-to-part IoU against misaligned geometry.

@dataclass(frozen=True)
class LetterboxParams:
    """
    Forward transform record, and its inverse.

    ratio is a single scalar because aspect ratio is preserved -- distorting
    it would skew every downstream area calculation, and severity is an area
    ratio.
    """
    ratio: float
    pad_x: float  # left padding in letterbox pixels
    pad_y: float  # top padding
    orig_w: int
    orig_h: int
    net_w: int  # model input width  (640)
    net_h: int   # model input height (640)

    def unletterbox_boxes(self, boxes: np.ndarray) -> np.ndarray:
        """
        Map xyxy boxes from letterbox space back to the original image.

        Clipped to the image: a box may legitimately extend into the padding
        when an object is cut off at the frame edge, and an unclipped negative
        coordinate would corrupt area maths later.
        """
        if boxes.size == 0:
            return boxes
        
        out = boxes.astype(np.float32).copy()
        out[:, [0, 2]] = (out[:, [0, 2]] - self.pad_x) / self.ratio
        out[:, [1, 3]] = (out[:, [1, 3]] - self.pad_y) / self.ratio
        out[:, [0, 2]] = out[:, [0, 2]].clip(0, self.orig_w)
        out[:, [1, 3]] = out[:, [1, 3]].clip(0, self.orig_h)
        
        return out


    def unletterbox_points(self, points: np.ndarray) -> np.ndarray:
        """Same inverse for an (N, 2) array of xy points (mask contours)."""
        if points.size == 0:
            return points
        
        out = points.astype(np.float32).copy()
        out[:, 0] = ((out[:, 0] - self.pad_x) / self.ratio).clip(0, self.orig_w)
        out[:, 1] = ((out[:, 1] - self.pad_y) / self.ratio).clip(0, self.orig_h)
        
        return out

    @property
    def content_box(self) -> tuple[int, int, int, int]:
        """The non-padded region inside the letterbox, as xyxy.

        Used to crop proto masks before upscaling -- interpolating across the
        padding bleeds mask energy into it.
        """
        x0, y0 = int(round(self.pad_x)), int(round(self.pad_y))
        x1 = int(round(self.net_w - self.pad_x))
        y1 = int(round(self.net_h - self.pad_y))
        
        return x0, y0, x1, y1


def load_image(source: str | Path | bytes) -> np.ndarray:
    """
    Load an image as an RGB uint8 HWC array, EXIF orientation applied.

    RGB, not BGR: the models were exported from Ultralytics, which feeds RGB.
    Passing BGR does not error -- it just quietly degrades accuracy, so the
    channel order is fixed here once and never re-swapped downstream.
    """
    try:
        if isinstance(source, bytes):
            pil = Image.open(io.BytesIO(source))
            
        else:
            path = Path(source)
            if not path.exists():
                raise InvalidUploadError(log_message=f"image not found: {path}")
            
            pil = Image.open(path)
            
        pil = ImageOps.exif_transpose(pil)  # honour the camera's rotation flag
        pil = pil.convert("RGB")
        
    except UnidentifiedImageError as exc:
        
        raise InvalidUploadError(
            log_message=f"unreadable image data: {exc}"
        ) from exc
        
    except OSError as exc:
        
        raise InvalidUploadError(
            detail="No se pudo leer la imagen. Puede estar corrupta.",
            log_message=f"failed to open image: {exc}",
        ) from exc

    array = np.asarray(pil, dtype=np.uint8)
    
    if array.ndim != 3 or array.shape[2] != 3: # HWC RGB
        
        raise InvalidUploadError(
            
            log_message=f"unexpected image shape {array.shape}"
        )
        
    return array


def letterbox(
    image: np.ndarray,
    net_size: tuple[int, int] = (640, 640),
    pad_value: int = PAD_VALUE,
) -> tuple[np.ndarray, LetterboxParams]:
    """Resize preserving aspect ratio, then centre-pad to `net_size`."""
    net_h, net_w = net_size
    orig_h, orig_w = image.shape[:2]

    ratio = min(net_w / orig_w, net_h / orig_h)
    new_w, new_h = int(round(orig_w * ratio)), int(round(orig_h * ratio))

    # INTER_AREA downsamples without aliasing; INTER_LINEAR is right for the
    # (rare) upscale of a small image.
    interp = cv2.INTER_AREA if ratio < 1 else cv2.INTER_LINEAR
    resized = cv2.resize(image, (new_w, new_h), interpolation=interp)

    pad_w, pad_h = (net_w - new_w) / 2, (net_h - new_h) / 2
    top, bottom = int(round(pad_h - 0.1)), int(round(pad_h + 0.1))
    left, right = int(round(pad_w - 0.1)), int(round(pad_w + 0.1))

    padded = cv2.copyMakeBorder(
        resized, top, bottom, left, right,
        cv2.BORDER_CONSTANT, value=(pad_value,) * 3,
    )
    params = LetterboxParams(
        ratio=ratio, pad_x=pad_w, pad_y=pad_h,
        orig_w=orig_w, orig_h=orig_h, net_w=net_w, net_h=net_h,
    )
    return padded, params

# EXIF orientation is applied on load. Phone cameras record portrait shots as
# landscape plus a rotation flag; cv2.imread ignores it, which would feed the
# model a sideways car.

def to_tensor(image: np.ndarray) -> np.ndarray:
    """HWC uint8 RGB -> NCHW float32 in [0, 1], contiguous for ORT."""
    tensor = image.astype(np.float32) / 255.0
    tensor = np.transpose(tensor, (2, 0, 1))[np.newaxis, ...]
    
    return np.ascontiguousarray(tensor, dtype=np.float32)


def preprocess(
    source: str | Path | bytes | np.ndarray,
    net_size: tuple[int, int] = (640, 640),
) -> tuple[np.ndarray, LetterboxParams, np.ndarray]:
    """
    Full path: load -> letterbox -> tensor.

    Returns (tensor, params, original_rgb). The original is returned because
    both callers need it: severity uses its dimensions, and the annotated
    output image is drawn on it.
    """
    image = source if isinstance(source, np.ndarray) else load_image(source)
    padded, params = letterbox(image, net_size)
    
    return to_tensor(padded), params, image


def preprocess_batch(
    sources: list[str | Path | bytes],
    net_size: tuple[int, int] = (640, 640),
) -> tuple[np.ndarray, list[LetterboxParams], list[np.ndarray]]:
    """Preprocess several images.

    The exported models are fixed at batch=1, so callers must still run them one
    at a time; this only shares the loading work and keeps the per-image
    `LetterboxParams` aligned by index with the originals.
    """
    tensors, params, originals = [], [], []
    
    for src in sources:
        
        tensor, param, original = preprocess(src, net_size)
        tensors.append(tensor)
        params.append(param)
        originals.append(original)
        
    return (
        
        np.concatenate(tensors, axis=0) if tensors else np.empty((0, 3, *net_size)),
        params,
        originals,
    )


def validate_upload(filename: str, content_type: str, size_bytes: int) -> None:
    """Cheap gate before writing an upload to disk."""
    settings = get_settings()
    
    if size_bytes > settings.max_upload_bytes:
        
        from app.core.exceptions import UploadTooLargeError

        raise UploadTooLargeError(
            
            detail=(
                f"La imagen supera el maximo de {settings.max_upload_mb} MB."
            ),
            log_message=f"{filename}: {size_bytes} bytes",
        )
    if content_type not in settings.allowed_image_types:
        
        raise InvalidUploadError(
            
            detail="Formato no soportado. Usa JPG, PNG o WEBP.",
            log_message=f"{filename}: rejected content-type {content_type!r}",
        )
