
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.session import session_store
from app.routers import (
    admin,
    admin_users,
    appointments,
    auth,
    chat,
    health,
    inspection,
    vehicles,
)

logger = logging.getLogger(__name__)

# Warmup is the important part of startup, bge-m3 takes ~7 s to load embeddings model
# and the three ONNX models ~0.4 s. Loading them lazily on the first request
# would push that cost onto a customer and in testing, an unauthenticated
# HuggingFace cache check once stalled inside a request for 8 minutes. So the
# lifespan handler loads everything up front: the process is only ready once
# it can actually serve first request.

def _warmup() -> None:
    """
    Load models and verify dependencies. Failures degrade, they do not abort.

    A missing Qdrant should not stop the API from booting: the vision pipeline
    and the quote still work, and `query_compliance` returns an error the agent
    is built to handle. Refusing to start would take down the whole service for
    a partial outage.
    """
    settings = get_settings()

    try:
        from app.vision.onnx_infer import warmup as warmup_vision

        warmup_vision()
        
    except Exception:  # noqa: BLE001
        logger.exception("Vision warmup failed; inspections will error until fixed")

    # MongoDB is the source of truth for both catalogs; each loader falls back
    # to its JSON file on its own. The ping is only so an unreachable cluster
    # is one clear line at boot instead of two fallback errors.
    from app.db.mongo import is_configured, ping

    if is_configured():
        
        reachable = ping()
        logger.info("MongoDB reachable: %s", reachable)
        
        if reachable:
            try:
                from app.db.repository import (
                    ensure_admin_indexes,
                    ensure_discount_indexes,
                    ensure_indexes,
                    ensure_user_indexes,
                )

                ensure_indexes()
                ensure_user_indexes()
                ensure_admin_indexes()
                # uniq_customer_key is what actually stops a second grant to
                # the same customer; grant_discount's check races itself.
                ensure_discount_indexes()
                logger.info(
                    "MongoDB indexes ensured (inspections, appointments, "
                    "users, discounts)."
                )
            except Exception:  # noqa: BLE001
                logger.exception("Could not ensure MongoDB indexes")
    else:
        logger.warning("MONGODB_URI not set: catalogs load from JSON")

    try:
        from app.rag.pricing_rag import get_trie

        trie = get_trie()
        
        logger.info(
            "PricingTrie ready: %d entries (source=%s).", 
            len(trie), 
            trie.source
        )
    except Exception:  # noqa: BLE001
        logger.exception("Pricing catalog failed to load")

    try:
        from app.rag.brand_index import list_brands, loaded_source

        logger.info(
            "Brand index ready: %d brands (source=%s).",
            len(list_brands()), 
            loaded_source(),
        ) # I need to get the logs for traceback
    except Exception:  # noqa: BLE001
        logger.exception("Brand index failed to load; quoting at baseline")
# lazy loadingg eenforced yb backend design
    try:
        from app.rag.qdrant_client import warmup as warmup_rag
# if qdrant failes the SPA still works without RAg.
        warmup_rag()
        # get vector from qdrant
    except Exception:  # noqa: BLE001
        logger.exception(
            "Compliance RAG unavailable; diagnosis and quotes still work"
        )
# Traceback  backend logs at main startup
    logger.info(
        "Startup complete: %s on %s:%s", 
        settings.app_name,
        settings.api_host,
        settings.api_port,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Async-contect-manager is a decorator that runs the block in a separate
    # thread and returns the result. It is the only way to do async cleanup.
    settings = get_settings()
    setup_logging(settings)
    
    logger.info("Starting %s (%s)...", 
                settings.app_name, 
                settings.environment)

    if settings.warmup_on_startup:
        _warmup()
        
    else:
        logger.warning(
            "warmup_on_startup disabled: the first request pays the model load."
        )

    yield

    purged = session_store.purge_expired()
    logger.info("Shutting down. %d expired session(s) purged.", purged)


# FastAPI application entry point.

# uvicorn app.main:app --reload --port 8015 --host 0.0.0.0

# Port 8015, not uvicorn's default 8000 -- `frontend/vite.config.ts` proxies
# `/api` there and i have other services on the same port.

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description=(
            "Inspeccion vehicular por vision computacional (YOLO11m ONNX), "
            "cotizacion desde catalogo y verificacion RTM (NTC 5375, "
            "Resolucion 3768 de 2013)."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    
    register_exception_handlers(app)

    # Health sits at the root so probes do not depend on the API prefix.
    app.include_router(health.router)
    app.include_router(inspection.router, prefix=settings.api_prefix)
    app.include_router(chat.router, prefix=settings.api_prefix)
    app.include_router(vehicles.router, prefix=settings.api_prefix)
    app.include_router(appointments.router, prefix=settings.api_prefix)
    # Admin dashboard: login is public, everything under /admin is guarded
    # per-route by app/core/auth.py --- never globally.
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(admin_users.router, prefix=settings.api_prefix)
    app.include_router(admin.router, prefix=settings.api_prefix)
    # I do not have such a global middleware 4 /admin required JWT
    # I have a middleware for /admin that checks JWT endpoint by users
    # reutns the app buildup
    return app


app = create_app()

@app.get("/", tags=["meta"])
async def root() -> dict[str, Any]:
    settings = get_settings()
    return {
        "app": settings.app_name,
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "api": settings.api_prefix,
    }
