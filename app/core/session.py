"""In-memory inspection session store.
"""

from __future__ import annotations

import logging
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from app.core.config import get_settings
from app.core.exceptions import SessionNotFoundError, SessionStateError

logger = logging.getLogger(__name__)

# Mirrors DetectionModel in src/types/inspection.ts -- the three upload panels.
DetectionModel = Literal["vehicle_parts", "surface_defects", "tires_wheels"]
DETECTION_MODELS: tuple[DetectionModel, ...] = (
    "vehicle_parts", "surface_defects", "tires_wheels",
                )

# Mirrors InspectionStatus.
InspectionStatus = Literal[
    "idle", "uploading", "processing", "analyzing", "complete", "error"
]
StepStatus = Literal["pending", "running", "done", "error"]

# The pipeline the SPA renders. Labels are user-facing, hence Spanish.
# `tires` is created only when tyre photos were uploaded -- showing a step that
# never runs reads as a stall.
STEP_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("upload", "Carga de imagenes"),
    ("vision_parts", "Deteccion de piezas del vehiculo"),
    ("vision_defects", "Deteccion de defectos en superficie"),
    ("vision_tires", "Analisis de llantas"),
    ("spatial_match", "Cruce de defectos con piezas"),
    ("agent", "Diagnostico, cotizacion y normativa"),
)
_TIRE_STEP = "vision_tires"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat().replace("+00:00", "Z") if dt else None


@dataclass
class ProcessingStep:
    id: str
    label: str
    status: StepStatus = "pending"
    completed_at: datetime | None = None

    def to_payload(self) -> dict[str, Any]:
        
        payload: dict[str, Any] = {
            
            "id": self.id, 
            "label": self.label,
            "status": self.status,
        }
        
        if self.completed_at:
            
            payload["completedAt"] = _iso(self.completed_at)
            
        return payload


@dataclass
class UploadedFile:
    id: str
    name: str
    size: int
    type: str
    model: DetectionModel
    path: Path
    uploaded_at: datetime = field(default_factory=_now)

    def to_payload(self) -> dict[str, Any]:
        
        return {
            "id": self.id, 
            "name": self.name, 
            "size": self.size,
            "type": self.type, 
            "model": self.model,
            "uploadedAt": _iso(self.uploaded_at),
        }


@dataclass
class InspectionSession:
    id: str
    status: InspectionStatus = "idle"
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    completed_at: datetime | None = None
    error: str | None = None

    files: list[UploadedFile] = field(default_factory=list)
    steps: list[ProcessingStep] = field(default_factory=list)

    # Filled by the vision pipeline, then consumed by the agent.
    vision_result: dict[str, Any] | None = None   # full payload, for the SPA
    agent_payload: dict[str, Any] | None = None   # compact JSON seeded to Claude

    # Tool-use conversation, kept so /chat continues the same thread.
    messages: list[dict[str, Any]] = field(default_factory=list)
    report: dict[str, Any] | None = None

    vehicle_info: dict[str, Any] = field(default_factory=dict)

    # derived  
    @property
    def tires_inspection_requested(self) -> bool:
        """
        Drives `pipeline_flags.tires_inspection_requested`.

        Inferred from what was uploaded rather than asked for separately: the
        SPA has a tyre upload panel, and using it *is* the request.
        """
        return any(f.model == "tires_wheels" for f in self.files)

    def files_for(self, model: DetectionModel) -> list[UploadedFile]:
        
        return [f for f in self.files if f.model == model]

    @property
    def upload_dir(self) -> Path:
        
        return get_settings().upload_dir / self.id

    def is_expired(self, ttl_minutes: int) -> bool:
        
        return _now() - self.updated_at > timedelta(minutes=ttl_minutes)

    #  payloads  
    def to_status_payload(self) -> dict[str, Any]:
        """Shape returned by GET /api/inspections/{id}/status."""
        
        return {
            "sessionId": self.id,
            "overallStatus": self.status,
            "steps": [s.to_payload() for s in self.steps],
            **({"error": self.error} if self.error else {}),
        }

    def to_summary(self) -> dict[str, Any]:
        
        return {
            "sessionId": self.id,
            "status": self.status,
            "createdAt": _iso(self.created_at),
            "completedAt": _iso(self.completed_at),
            "files": [f.to_payload() for f in self.files],
            "tiresInspectionRequested": self.tires_inspection_requested,
        }


class SessionStore:
    """Process-wide store. Use the module-level `session_store` singleton."""

    def __init__(self, ttl_minutes: int | None = None) -> None:
        self._sessions: dict[str, InspectionSession] = {}
        self._lock = threading.RLock()
        self._ttl_minutes = ttl_minutes

    @property
    def ttl_minutes(self) -> int:
        
        return self._ttl_minutes or get_settings().session_ttl_minutes

    #  lifecycle  
    def create(self, 
               vehicle_info: dict[str, Any] | None = None
               ) -> InspectionSession:
        
        session = InspectionSession(id=str(uuid.uuid4()))
        session.vehicle_info = vehicle_info or {}
        session.steps = [ProcessingStep(id=i, label=l) for i, l in STEP_DEFINITIONS]
        
        with self._lock:
            
            self._purge_expired_locked()
            self._sessions[session.id] = session
            
        session.upload_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Session created: %s", session.id)
        
        return session

    def get(self, session_id: str) -> InspectionSession:
        """Fetch a live session. Raises `SessionNotFoundError` if absent/expired."""
        with self._lock:
            session = self._sessions.get(session_id)
            
            if session is None:
                
                raise SessionNotFoundError(
                    log_message=f"session {session_id} not found",
                )
                
            if session.is_expired(self.ttl_minutes):
                self._delete_locked(session_id)
                
                raise SessionNotFoundError(
                    log_message=f"session {session_id} expired",
                )
                
            return session


    def delete(self, session_id: str) -> None:
        
        with self._lock:
            self._delete_locked(session_id)


    def _delete_locked(self, session_id: str) -> None:
        
        session = self._sessions.pop(session_id, None)
        
        if session is None:
            return
        
        shutil.rmtree(session.upload_dir, ignore_errors=True)
        logger.info("Session removed: %s", session_id)

    def purge_expired(self) -> int:
        
        with self._lock:
            return self._purge_expired_locked()


    def _purge_expired_locked(self) -> int:
        
        ttl = self.ttl_minutes
        stale = [i for i, s in self._sessions.items() if s.is_expired(ttl)]
        
        for session_id in stale:
            
            self._delete_locked(session_id)
            
        if stale:
            
            logger.info("Purged %d expired session(s).", len(stale))
            
        return len(stale)

    #   mutation  
    def add_file(
        self,
        session_id: str,
        *,
        name: str,
        size: int,
        content_type: str,
        model: DetectionModel,
        path: Path,
    ) -> UploadedFile:
        
        with self._lock:
            
            session = self.get(session_id)
            
            uploaded = UploadedFile(
                
                id=str(uuid.uuid4()), 
                name=name, 
                size=size,
                type=content_type, 
                model=model, 
                path=path,
            )
            
            session.files.append(uploaded)
            session.status = "uploading"
            self._touch(session)
            
            return uploaded
        

    def set_status(
        self, 
        session_id: str, 
        status: InspectionStatus, 
        *, 
        error: str | None = None
        
    ) -> InspectionSession:
        
        with self._lock:
            session = self.get(session_id)
            session.status = status
            
            if status == "complete":
                session.completed_at = _now()
                
            if error is not None:
                
                session.error = error
                
            self._touch(session)
            
            return session

    def set_step(
        self, 
        session_id: str,
        step_id: str, 
        status: StepStatus
    ) -> InspectionSession:
        """Advance one pipeline step. Unknown ids are ignored, not fatal --
        a mislabelled step must never abort a running inspection."""
        with self._lock:
            session = self.get(session_id)
            
            for step in session.steps:
                
                if step.id == step_id:
                    
                    step.status = status
                    
                    step.completed_at = _now() if status == "done" else None
                    break
                
            else:
                
                logger.warning("Unknown step %r for session %s", step_id, session_id)
            self._touch(session)
            
            return session

    def prepare_steps(self, session_id: str) -> InspectionSession:
        """Drop steps that will not run, before the pipeline starts.

        Called by /run: without tyre photos the tyre model never executes, and
        leaving its step `pending` forever looks like a hang to the SPA.
        """
        with self._lock:
            session = self.get(session_id)
            
            if not session.files:
                
                raise SessionStateError(
                    detail="No hay imagenes cargadas para analizar.",
                    log_message=f"session {session_id} has no uploads",
                )
                
            if not session.tires_inspection_requested:
                
                session.steps = [s for s in session.steps if s.id != _TIRE_STEP]
                
            self._touch(session)
            
            return session
        

    def append_messages(
        self, 
        session_id: str, 
        messages: list[dict[str, Any]]
    ) -> InspectionSession:
        """Extend the agent conversation so /chat continues the same thread."""
        with self._lock:
            session = self.get(session_id)
            session.messages.extend(messages)
            self._touch(session)
            
            return session

    def _touch(self, session: InspectionSession) -> None:
        session.updated_at = _now()

    # introspection
    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)

    @property
    def active_ids(self) -> list[str]:
        with self._lock:
            return list(self._sessions)


session_store = SessionStore()
