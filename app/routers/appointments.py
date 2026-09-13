
from __future__ import annotations

import logging

from fastapi.concurrency import run_in_threadpool
from fastapi import APIRouter
from pymongo.errors import PyMongoError

from app.core.exceptions import AppointmentNotFoundError, AppointmentUnavailableError
from app.db import mongo, repository
from app.schemas.appointments import AppointmentResponse, AppointmentListResponse

router = APIRouter(tags=["appointments"])

logger = logging.getLogger(__name__)

# Customer-facing appointment reads. Read-only by design.

# Bookings are created/moved/cancelled by the agent tools (behind a code+email+
# plate ownership check) or by the admin dashboard (behind StaffUser) -- both
# call the repository directly, in-process, never through HTTP. A write
# endpoint here would be a third door with no guard on it: this router is
# mounted public and the SPA's customer flow sends no token.

def _require_mongo() -> None:
    
    if not mongo.is_configured():
        raise AppointmentUnavailableError(log_message="MONGODB_URI is not set")


@router.get("/appointments/{codigo}", response_model=AppointmentResponse)
async def get_appointment(codigo: str) -> AppointmentResponse:
    _require_mongo()
    try:
        doc = await run_in_threadpool(repository.get_appointment, codigo)
        
    except PyMongoError as exc:
        
        raise AppointmentUnavailableError(log_message=str(exc)) from exc
    
    if doc is None:
        raise AppointmentNotFoundError(log_message=f"appointment {codigo!r} not found")
    
    return AppointmentResponse.from_document(doc)


@router.get(
    "/inspections/{inspection_id}/appointments",
    response_model=AppointmentListResponse,
)
async def appointments_for_inspection(inspection_id: str) -> AppointmentListResponse:
    _require_mongo()
    try:
        docs = await run_in_threadpool(
            repository.appointments_for_inspection, inspection_id
        )
    except PyMongoError as exc:
        raise AppointmentUnavailableError(log_message=str(exc)) from exc
    
    return AppointmentListResponse(
        
        inspection_id=inspection_id,
        appointments=[AppointmentResponse.from_document(d) for d in docs],
    )
