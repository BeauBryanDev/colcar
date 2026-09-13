
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.db.mongo import is_configured
from app.rag.brand_index import loaded_source
from app.rag.pricing_rag import get_trie
from app.vision.onnx_infer import ModelKind, get_model

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# health Endpoint

@router.get("/health")
async def health() -> dict[str, Any]:
    """Liveness. No dependencies touched."""
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
        "model": settings.anthropic_model,
    }

# Readniness check
@router.get("/health/ready")
async def readiness() -> JSONResponse:
    """Readiness. Reports dependency state without forcing anything to load."""
    settings = get_settings()
    checks: dict[str, Any] = {}
    ready = True

    # Visison model load on disk, plus whether already warmed.
    loaded = get_model.cache_info().currsize
    models: dict[str, Any] = {}
    
    for kind in ModelKind:
        # My Three YOLO ONNX models are in the same directory as the rest.
        path = {
            ModelKind.CAR_PARTS: settings.car_parts_model_path,
            ModelKind.CAR_DEFECTS: settings.car_defects_model_path,
            ModelKind.TYRES: settings.tyres_defect_model_path,
        }[kind]
        
        exists = path.exists()
        
        models[kind.value] = {"file": path.name, "exists": exists}
        
        if not exists:
            ready = False
            
    checks["vision"] = {
        "models": models,
        "loaded_count": loaded,
        "warmed": loaded == len(ModelKind),
    }

    # Pricing catalog: Mongo is the source of truth, the JSON the fallback.
    # A missing fallback file is a deploy error. `source` is reported only if
    # the trie is already built -> forcing it here could open a Mongo
    # connection inside a probe, the same rule as the models above.
    catalog = settings.pricing_catalog_path
    trie_loaded = get_trie.cache_info().currsize > 0
    
    checks["pricing"] = {
        "mongo_configured": is_configured(),
        "fallback_file": catalog.name,
        "fallback_exists": catalog.exists(),
        "loaded": trie_loaded,
        "source": get_trie().source if trie_loaded else None,
        "entries": len(get_trie()) if trie_loaded else None,
        "brands_source": loaded_source() if trie_loaded else None,
    }
    if not catalog.exists():
        ready = False

    # Compliance: report configuration only; probing Qdrant would add a
    # network round trip to every health check.
    checks["compliance"] = {
        "collection": settings.qdrant_collection,
        "embedding_model": settings.embedding_model,
        "configured": bool(settings.qdrant_url),
    }
    if not settings.qdrant_url:
        ready = False

    body = {"status": "ready" if ready else "degraded", "checks": checks}
    
    return JSONResponse(
        content=body,
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
    )

# This is Impoertant I made Two levels, because they answer different questions:

#     GET /health        is the process up?  -> cheap, no I/O
#     GET /health/ready  can it serve traffic? -> checks dependencies

# /health/ready  does NOT force models or the embedder to load.
# Loading bge-m3 takes ~8 s and the ONNX models ~0.4 s, so a health check that
# triggered them would time out on a cold process and could be turned into a
# denial of service by anything polling it. 
# It reports what is *already* loaded
# and whether the artefacts exist on disk; warming up is the lifespan handler's
# job, not the probe's.

@router.get("/health/models")
async def model_details() -> dict[str, Any]:
    """
    Loaded model geometry -> diagnostics, and it *will* load them.

    Separate from /health/ready precisely because it is expensive; call it by
    hand when debugging, never from a monitor.
    """
    from app.vision.onnx_infer import describe_models

    return {"models": describe_models()}
