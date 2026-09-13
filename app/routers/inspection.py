
from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile, status
from fastapi.responses import FileResponse

from app.agent.claude_agent import start_inspection_conversation
from app.core.config import get_settings
from app.core.exceptions import AppError, InvalidUploadError, SessionStateError
from app.core.session import DETECTION_MODELS, DetectionModel, session_store
from app.schemas.detections import OverlayImage, OverlayResponse, OverlayShape
from app.schemas.inspection import (
    InspectionResultResponse, ProcessingStatusResponse, ProcessingStepModel,
    RunInspectionRequest, RunInspectionResponse, StartInspectionRequest,
    StartInspectionResponse, UploadedFileInfo, UploadFilesResponse,
)
from app.vision.pipeline import run_inspection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inspections", tags=["inspections"])

# Which upload panel feeds which flow.
_SURFACE_MODELS = ("vehicle_parts", "surface_defects")

# The inspection lifecycle: start -> upload -> run -> poll status -> results.

# Contract from `frontend/src/services/inspectionService.ts`:

# POST /api/inspections/start  -> {sessionId, message}
# POST /api/inspections/upload  -> multipart: session_id, model, files[]
# POST /api/inspections/run   ->  {session_id} -> {message}
# GET  /api/inspections/{id}/status   -> {sessionId, overallStatus, steps[]}
# GET  /api/inspections/{id}/results   -> vision payload + agent report

#/run returns immediately -> Vision takes ~1 s per surface image and the
# agent loop 5-15 s, well past a  HTTP wait, so the work happens in a
# BackgroundTask and the SPA polls `/status`. That is also why `SessionStore`
# exists: it is the only shared state between the request that starts the work
# and the requests that observe it.

# Uploads are validated and written to disk per session (`data/uploads/<id>/`),
# then deleted with the session when it expires.

@router.post("/start", response_model=StartInspectionResponse,
             status_code=status.HTTP_201_CREATED)
async def start_inspection(
    payload: StartInspectionRequest | None = None,
) -> StartInspectionResponse:
    """Create a session. Vehicle info is optional and only personalises replies."""
    vehicle_info = (
        payload.vehicle_info.model_dump(exclude_none=True)
        if payload and payload.vehicle_info else {}
    )
    session = session_store.create(vehicle_info)
    
    return StartInspectionResponse(
        session_id=session.id,
        message="Sesion de inspeccion creada. Carga las imagenes del vehiculo.",
    )


@router.post("/upload", response_model=UploadFilesResponse)
async def upload_files(
    session_id: Annotated[str, Form()],
    model: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()],
    brand: Annotated[str | None, Form()] = None,
    vehicle_model: Annotated[str | None, Form()] = None,
    year: Annotated[int | None, Form()] = None,
) -> UploadFilesResponse:
    """Store images for one detection panel, with optional vehicle metadata.

    Multipart rather than JSON, matching the SPA's FormData. Per-panel caps come
    from config: 3 surface images (both segmentation models run on each), 1 tyre.

    `brand` / `vehicle_model` / `year` come from the SPA's three select lists and
    ride along with the image. They are merged into the session rather than
    replacing it, so sending them on the first upload only is enough  and
    `brand` is what scales the quote, so an unrecognised value silently falls
    back to baseline pricing rather than erroring mid-upload.
    """
    # TODO: this upload image must goes to S3 bucket in AWS when it is deployed
    settings = get_settings()
    session = session_store.get(session_id)

    if model not in DETECTION_MODELS:
        
        raise InvalidUploadError(
            detail=f"Modelo de deteccion invalido: {model}.",
            log_message=f"unknown model {model!r}",
        )
        
    detection_model: DetectionModel = model  # type: ignore[assignment]

    limit = (
        settings.max_images_tyres if detection_model == "tires_wheels"
        else settings.max_images_surface 
    ) # Tyresget spectial handling, this is a obj-det model.
    already = len(session.files_for(detection_model))
    
    if already + len(files) > limit:
        
        raise InvalidUploadError(
            detail=(
                f"Maximo {limit} imagen(es) para esta seccion. "
                f"Ya cargaste {already}."
            ),
            log_message=f"upload cap: {already}+{len(files)} > {limit}",
        )

    metadata = {"brand": brand, "model": vehicle_model, "year": year}
    provided = {k: v for k, v in metadata.items() if v is not None}
    
    if provided:
        
        session.vehicle_info.update(provided)
        logger.info("Session %s: vehicle metadata %s", session_id, provided)

    stored: list[UploadedFileInfo] = []
    
    for upload in files:
        
        contents = await upload.read()
        # Validate against the real byte count; Content-Length is client-supplied.
        from app.vision.preprocess import validate_upload

        validate_upload(
            upload.filename or "imagen",
            upload.content_type or "", 
            len(contents)
        )

        destination = session.upload_dir / f"{len(session.files)}_{upload.filename}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)

        record = session_store.add_file(
            session_id, name=upload.filename or destination.name,
            size=len(contents), 
            content_type=upload.content_type or "",
            model=detection_model, path=destination,
        )
        stored.append(UploadedFileInfo(
            id=record.id, 
            name=record.name, 
            size=record.size, 
            type=record.type,
            model=record.model,
            uploaded_at=record.uploaded_at.isoformat().replace("+00:00", "Z"),
        ))

    logger.info("Session %s: stored %d file(s) for %s",
                session_id, len(stored), detection_model)
    
    return UploadFilesResponse(
        session_id=session_id, 
        uploaded_count=len(stored),
        message=f"{len(stored)} imagen(es) cargada(s).", 
        files=stored,
    )


def _execute_pipeline(session_id: str) -> None:
    """Vision + agent, in the background. Never raises into the task runner."""
    try:
        session = session_store.get(session_id)
        surface = [
            f.path for f in session.files
            if f.model in _SURFACE_MODELS
        ]
        tyres = [f.path for f in session.files if f.model == "tires_wheels"]

        session_store.set_status(session_id, "processing")
        result = run_inspection(
            surface_images=surface, 
            tyre_images=tyres,
            vehicle_info=session.vehicle_info, 
            inspection_id=session_id,
            progress=lambda step, state: session_store.set_step(
                session_id, step, state  # type: ignore[arg-type]
            ),
        )
        session.vision_result = result.to_payload()
        session.agent_payload = result.to_agent_payload()

        session_store.set_status(session_id, "analyzing")
        session_store.set_step(session_id, "agent", "running")
        run = start_inspection_conversation(
            session.agent_payload, 
            context=session.agent_context()
        )
        session_store.append_messages(session_id, run.messages)
        session.report = {
            "resumen": run.reply,
            "pricing": run.tool_result("query_pricing_batch"),
            "compliance": run.tool_result("query_compliance"),
            "tools_used": run.tools_used,
        }
        session_store.set_step(session_id, "agent", "done")
        session_store.set_status(session_id, "complete")
        logger.info("Inspection %s complete.", session_id)
        _persist_inspection(session_id)

    except AppError as exc:
        logger.warning("Inspection %s failed: %s", session_id, exc.log_message)
        _fail(session_id, exc.detail)
        
    except Exception as exc:  # noqa: BLE001 - background task must not die silently
        logger.exception("Inspection %s crashed", session_id)
        _fail(session_id, "Ocurrio un error inesperado durante el analisis.")


def _persist_inspection(session_id: str) -> None:
    """Write the durable record. Runs after `complete` and can never fail the
    run: the SPA reads the session, Mongo is the audit copy."""
    from app.db import mongo, repository
    from app.models.inspection import InspectionDocument
    from app.rag.pricing_rag import get_trie

    if not mongo.is_configured():
        return
    
    try:
        session = session_store.get(session_id)
        doc = InspectionDocument.from_session(
            session, 
            catalog_source=get_trie().source
        )
        repository.save_inspection(doc)
        logger.info("Inspection %s persisted (%d defects).", 
                    session_id, 
                    len(doc.defects)
                    )
        
    except Exception:  # noqa: BLE001 - audit copy only
        logger.exception("Inspection %s could not be persisted", session_id)


def _fail(session_id: str, detail: str) -> None:
    
    try:
        session = session_store.get(session_id)
        
        for step in session.steps:
            
            if step.status == "running":
                
                session_store.set_step(session_id, step.id, "error")
                
        session_store.set_status(session_id, "error", error=detail)
        
    except AppError:
        pass  # session already gone; nothing to record


@router.post("/run", response_model=RunInspectionResponse)
async def run_inspection_endpoint(
    payload: RunInspectionRequest, 
    background: BackgroundTasks,
) -> RunInspectionResponse:
    """Kick off vision + agent, then return immediately."""
    session = session_store.get(payload.session_id)
    
    if session.status in ("processing", "analyzing"):
        
        raise SessionStateError(
            detail="La inspeccion ya esta en curso.",
            log_message=f"run called while {session.status}",
        )

    # Raises SessionStateError when nothing was uploaded, and drops the tyre
    # step when no tyre photos exist so the SPA does not wait on it forever.
    session_store.prepare_steps(payload.session_id)
    session_store.set_status(payload.session_id, "processing")
    background.add_task(_execute_pipeline, payload.session_id)

    return RunInspectionResponse(
        session_id=payload.session_id,
        message="Analisis iniciado. Consulta el estado para ver el progreso.",
    )


@router.get("/{session_id}/status", response_model=ProcessingStatusResponse)
async def get_status(session_id: str) -> ProcessingStatusResponse:
    """Polled by the SPA while the pipeline runs."""
    session = session_store.get(session_id)
    
    return ProcessingStatusResponse(
        session_id=session.id,
        overall_status=session.status,
        steps=[
            ProcessingStepModel(
                id=s.id, label=s.label, 
                status=s.status,
                completed_at=(
                    s.completed_at.isoformat().replace("+00:00", "Z")
                    if s.completed_at else None
                ),
            )
            for s in session.steps
        ],
        error=session.error,
    )


@router.get("/{session_id}/results", response_model=InspectionResultResponse)
async def get_results(session_id: str) -> InspectionResultResponse:
    """Full vision payload plus the agent's report, once complete."""
    session = session_store.get(session_id)
    
    return InspectionResultResponse(
        session_id=session.id,
        status=session.status,
        vision=session.vision_result,  # type: ignore[arg-type]
        report=session.report,
        completed_at=(
            session.completed_at.isoformat().replace("+00:00", "Z")
            if session.completed_at else None
        ),
    )


def _image_records(session) -> dict[str, dict]:
    """image_id -> the `images_analyzed` entry the pipeline emitted.

    The pipeline names images `img_1..N` and records `filename` as the *stored*
    basename, so this is the only mapping needed. Never build a path from a
    client-supplied id: the id is looked up here and the filename comes from
    our own payload, which is what keeps `..%2Fetc%2Fpasswd` from resolving.
    """
    payload = session.vision_result or {}
    
    return {img["image_id"]: img for img in payload.get("images_analyzed", [])}


@router.get("/{session_id}/images/{image_id}")
async def get_image(session_id: str, image_id: str) -> FileResponse:
    """Serve one analysed image back to the SPA.

    The SPA draws masks over the photo, and a browser that reloaded (or a
    second device) has no object URL for the original upload -- without this
    the overlay would have nothing to sit on.
    """
    session = session_store.get(session_id)
    record = _image_records(session).get(image_id)
    
    if record is None:
        
        raise SessionStateError(
            detail="Imagen no encontrada para esta inspeccion.",
            log_message=f"unknown image_id {image_id!r} on {session_id}",
        )

    path = (session.upload_dir / record["filename"]).resolve()
    # Defence in depth: the filename came from our own payload, but a resolved
    # path must still never escape the session's upload directory.
    if not path.is_file() or session.upload_dir.resolve() not in path.parents:
        
        raise SessionStateError(
            detail="La imagen ya no esta disponible.",
            log_message=f"missing/out-of-tree image file {path}",
        )

    # Uploads are immutable for the life of the session, so let the browser
    # cache aggressively: without this every re-render re-downloads a photo
    # that can be several MB from a phone camera.
    return FileResponse(
        path,
        filename=record["filename"],
        headers={"Cache-Control": "private, max-age=3600, immutable"},
    )


@router.get("/{session_id}/overlay", response_model=OverlayResponse)
async def get_overlay(session_id: str) -> OverlayResponse:
    """Segmentation masks for rendering, without the rest of the vision payload.

    Kept separate from the agent on purpose. `to_agent_payload()` never carries
    polygons -- they are hundreds of coordinate pairs per defect, re-sent on
    every turn of the tool-use loop, and the model cannot reason over them.
    Masks are a rendering concern, so they go straight to the browser.
    """
    settings = get_settings()
    session = session_store.get(session_id)
    payload = session.vision_result or {}
    prefix = f"{settings.api_prefix}/inspections/{session.id}/images"

    shapes_by_image: dict[str, list[OverlayShape]] = {}

    for part in payload.get("parts_detected", []):
        # `object` is the parts model's catch-all and is dropped project-wide.
        if part.get("class_name") == "object":
            continue
        
        shapes_by_image.setdefault(part["image_id"], []).append(
            OverlayShape(
                detection_id=part["detection_id"], image_id=part["image_id"],
                kind="part", class_name=part["class_name"],
                confidence=part["confidence"], bbox=part["bbox"],
                polygon=part.get("segmentation_polygon"),
            )
        )

    defect_lists = (
        "surface_defects_detected", 
        "tire_defects_detected", 
        "unmatched_defects",
    )
    
    for key in defect_lists:
        
        for defect in payload.get(key, []):
            
            shapes_by_image.setdefault(defect["image_id"], []).append(
                OverlayShape(
                    detection_id=defect["detection_id"],
                    image_id=defect["image_id"],
                    kind="defect", class_name=defect["class_name"],
                    confidence=defect["confidence"], bbox=defect["bbox"],
                    polygon=defect.get("segmentation_polygon"),
                    severidad=defect.get("severidad"),
                    severidad_display=defect.get("severidad_display"),
                    matched_part_name=defect.get("matched_part_name"),
                )
            )

    return OverlayResponse(
        session_id=session.id,
        images=[
            OverlayImage(
                image_id=img["image_id"], 
                filename=img["filename"],
                role=img["role"], width=img["width"],
                height=img["height"],
                image_url=f"{prefix}/{img['image_id']}",
                shapes=shapes_by_image.get(img["image_id"], []),
            )
            for img in payload.get("images_analyzed", [])
        ],
    )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str) -> None:
    """Drop a session and its uploaded images."""
    session_store.get(session_id)  # 404 if unknown
    
    session_store.delete(session_id)
