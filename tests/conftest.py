"""Shared fixtures. Everything here runs offline."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP_UPLOADS = Path(tempfile.mkdtemp(prefix="carscanner-tests-"))

## Set before any app import: config reads .env at module import time.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key-0123456789")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_API_KEY", "test-qdrant-key-0123456789")
os.environ["WARMUP_ON_STARTUP"] = "false"
os.environ["EMBEDDING_OFFLINE"] = "true"
os.environ["UPLOAD_DIR"] = str(_TMP_UPLOADS)
## Force the JSON fallback for both catalogs even when the developer's .env has
## a real cluster: the suite is offline, and a blank URI means "unset".
os.environ["MONGODB_URI"] = ""
os.environ["API_NINJA_KEY"] = ""
## A deterministic signing key so the JWT tests do not depend on the
## developer's .env -- and one long enough to pass the >= 32 char guard.
os.environ["JWT_SECRET"] = "test-jwt-secret-0123456789abcdefghijklmnop"

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.session import SessionStore, session_store as global_store  # noqa: E402
from app.rag.pricing_rag import PricingEntry, PricingTrie, build_trie  # noqa: E402
from app.vision.postprocess_seg import Detection  # noqa: E402
from app.vision.spatial_match import MatchedDefect  # noqa: E402


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail loudly if a test tries to reach Anthropic, Qdrant or HuggingFace."""
    import socket

    def blocked(*args, **kwargs):
        raise RuntimeError("network access is not allowed in the test suite")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture
def make_detection():
    """Build a Detection, optionally with a rectangular mask."""

    def _make(
        class_name: str,
        bbox: tuple[float, float, float, float],
        *,
        confidence: float = 0.9,
        with_mask: bool = False,
        canvas: tuple[int, int] = (400, 400),
        class_id: int = 0,
        detection_id: str = "",
    ) -> Detection:
        mask = None
        area = 0
        if with_mask:
            height, width = canvas
            mask = np.zeros((height, width), dtype=bool)
            x0, y0, x1, y1 = (int(round(v)) for v in bbox)
            mask[y0:y1, x0:x1] = True
            area = int(mask.sum())
        return Detection(
            class_id=class_id,
            class_name=class_name,
            confidence=confidence,
            bbox=bbox,
            mask=mask,
            mask_area_px=area,
            image_id="img_1",
            detection_id=detection_id or f"img_1_{class_name}",
        )

    return _make


@pytest.fixture
def make_match():
    def _make(defect: Detection, part: Detection | None = None) -> MatchedDefect:
        return MatchedDefect(defect=defect, part=part, containment=1.0, basis="mask")

    return _make


@pytest.fixture(scope="session")
def trie() -> PricingTrie:
    """The real catalog, loaded in memory."""
    return build_trie()


@pytest.fixture
def tiny_trie() -> PricingTrie:
    """Hand-built trie with a known shape for fallback assertions."""

    def entry(name: str, severidad: str, total: int) -> PricingEntry:
        return PricingEntry(
            service_name=f"{name} {severidad}",
            labor_hours=1.0,
            labor_cost_cop=total // 2,
            materials_cost_cop=total // 4,
            parts_cost_cop=total - total // 2 - total // 4,
            total_cost_cop=total,
            requires_replacement=False,
            pieza=name,
            tipo_defecto="dent",
            severidad=severidad,
            category="body_panel",
        )

    built = PricingTrie()
    built.insert("hood", "dent", "leve", entry("hood", "leve", 100_000))
    built.insert("hood", "dent", "grave", entry("hood", "grave", 400_000))
    built.insert(
        "generic:body_panel", "dent", "moderado",
        entry("generic:body_panel", "moderado", 250_000),
    )
    return built


def _text_message(role: str, text: str) -> dict:
    return {"role": role, "content": [{"type": "text", "text": text}]}


@pytest.fixture
def msg_user():
    def _make(text: str = "hola") -> dict:
        return _text_message("user", text)

    return _make


@pytest.fixture
def msg_assistant():
    def _make(text: str = "listo") -> dict:
        return _text_message("assistant", text)

    return _make


@pytest.fixture
def msg_tool_use():
    def _make(tool_id: str, name: str = "query_pricing_batch") -> dict:
        return {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": tool_id, "name": name, "input": {}}
            ],
        }

    return _make


@pytest.fixture
def msg_tool_result():
    def _make(tool_id: str, content: str = "{}") -> dict:
        return {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": tool_id, "content": content}
            ],
        }

    return _make


@pytest.fixture
def store() -> SessionStore:
    """Isolated store, so tests never share sessions."""
    fresh = SessionStore()
    yield fresh
    for session_id in fresh.active_ids:
        fresh.delete(session_id)


@pytest.fixture
def client():
    """TestClient with warmup disabled, so no model or network load."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    for session_id in global_store.active_ids:
        global_store.delete(session_id)


@pytest.fixture
def jpeg_bytes() -> bytes:
    import cv2

    image = np.full((64, 64, 3), 128, dtype=np.uint8)
    ok, buffer = cv2.imencode(".jpg", image)
    assert ok
    return buffer.tobytes()
