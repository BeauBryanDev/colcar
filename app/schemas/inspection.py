
from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.common import (
    ApiRequest, ApiResponse, DetectionModel, InspectionStatus, StepStatus,
)
from app.schemas.detections import VisionResult
# Request/response models for the five inspection endpoints.

# The contract is defined by `frontend/src/services/inspectionService.ts`:
# Because I decided to build first the Frontend, I did not bother with
# TypeScript types. The SPA is written in React, so the frontend/src/types
# folder is a copy of the backend's app/schemas.

#   POST /api/inspections/start    -> {sessionId, message}
#   POST /api/inspections/upload  multipart: session_id, model, files[]
#   POST /api/inspections/run     {session_id} -> {message}
#   GET  /api/inspections/{id}/status    -> {sessionId, overallStatus, steps[]}
#   POST /api/inspections/chat     {session_id, message} -> {reply, timestamp}

# Requests are snake_case and responses camelCase because that is what the SPA
# already sends and reads -- see `app/schemas/common.py`.

# START: the SPA's request shapes, for the agent's response.
class VehicleInfo(ApiRequest):
    """
    Optional vehicle details, used only to personalise the agent's replies.

    `brand` (not `make`): the backend is the source of truth and the agent
    payload has always used `brand`.
    """

    brand: str | None = None
    model: str | None = None
    year: int | None = Field(default=None, ge=1900, le=2100)
    color: str | None = None
    license_plate: str | None = None


class StartInspectionRequest(ApiRequest):
    vehicle_info: VehicleInfo | None = None


class StartInspectionResponse(ApiResponse):
    session_id: str
    message: str


# The body is multipart/form-data (session_id + model + files), so FastAPI
# parses it with Form()/UploadFile parameters rather than a pydantic model.
class UploadedFileInfo(ApiResponse):
    id: str
    name: str
    size: int
    type: str
    model: DetectionModel
    uploaded_at: str


class UploadFilesResponse(ApiResponse):
    session_id: str
    uploaded_count: int
    message: str
    files: list[UploadedFileInfo] = Field(default_factory=list)


class RunInspectionRequest(ApiRequest):
    session_id: str


class RunInspectionResponse(ApiResponse):
    session_id: str
    message: str
    # The pipeline runs in the background (~1 s per surface image plus the
    # agent loop), so this returns immediately and the SPA polls /status.
    status: InspectionStatus = "processing"


## Startup ""
class ProcessingStepModel(ApiResponse):
    id: str
    label: str
    status: StepStatus
    completed_at: str | None = None


class ProcessingStatusResponse(ApiResponse):
    session_id: str
    overall_status: InspectionStatus
    steps: list[ProcessingStepModel] = Field(default_factory=list)
    error: str | None = None


## Results
class InspectionResultResponse(ApiResponse):
    """Everything the SPA needs to render the report once /status is complete."""

    session_id: str
    status: InspectionStatus
    vision: VisionResult | None = None
    report: dict[str, Any] | None = None
    completed_at: str | None = None
