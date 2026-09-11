

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from app.core.config import get_settings
from app.db.mongo import get_db
from app.models.appointment import AppointmentDocument, code_of, new_appointment_id
from app.models.inspection import InspectionDocument

logger = logging.getLogger(__name__)

# How many fresh ids to try when a 6-char `codigo` collides.
_CODE_RETRIES = 5

# Reads and writes for the `inspections` and `appointments` collections.

# Thin and synchronous, like the catalog loaders. Every function raises
# `PyMongoError` to its caller (the pipeline's persist step and the
# `make_appointment` tool), which decide how to degrade -- neither the
# inspection run nor the agent loop may die because Atlas blinked.

def _inspections():
    s = get_settings()
    return get_db(s)[s.inspections_collection]


def _appointments():
    s = get_settings()
    return get_db(s)[s.appointments_collection]


def ensure_indexes() -> None:
    """Idempotent. Called from warmup so a fresh cluster is ready to book."""
    appts = _appointments()
    appts.create_index([("codigo", ASCENDING)], unique=True, name="uniq_codigo")
    appts.create_index([("inspection_id", ASCENDING)], name="by_inspection")
    # Idempotency key: the agent loop can retry, and a double booking is
    # visible to a real customer.
    appts.create_index(
        [("inspection_id", ASCENDING), 
         ("scheduled_for", ASCENDING)],
        unique=True,
        name="uniq_inspection_slot",
    )
    _inspections().create_index([("created_at", ASCENDING)], name="by_created")


#  inspections

def save_inspection(doc: InspectionDocument) -> None:
    
    _inspections().replace_one({"_id": doc.id}, doc.to_doc(), upsert=True)


def get_inspection(inspection_id: str) -> InspectionDocument | None:
    
    raw = _inspections().find_one({"_id": inspection_id})
    
    return InspectionDocument.from_doc(raw) if raw else None


#  appointments

def find_appointment_for_slot(
    inspection_id: str, 
    scheduled_for: datetime
) -> AppointmentDocument | None:
    
    raw = _appointments().find_one(
        {"inspection_id": inspection_id, 
         "scheduled_for": scheduled_for}
    )
    return AppointmentDocument.from_doc(raw) if raw else None


def create_appointment(doc: AppointmentDocument) -> AppointmentDocument:
    """Insert, minting a fresh id/code if the short code collides.

    A collision on the *slot* index is not retried: that is the idempotency
    key, and the caller resolves it by returning the existing booking.
    """
    code_len = get_settings().appointment_code_length
    
    for attempt in range(_CODE_RETRIES):
        try:
            _appointments().insert_one(doc.to_doc())
            return doc
        
        except DuplicateKeyError as exc:
            
            if "uniq_codigo" not in str(exc):
                raise
            
            logger.warning("Appointment code %s collided; reminting", doc.codigo)
            doc.id = new_appointment_id()
            doc.codigo = code_of(doc.id, code_len)
            
    raise RuntimeError("could not mint a unique appointment code")


def get_appointment(codigo_or_id: str) -> AppointmentDocument | None:
    
    key = codigo_or_id.strip()
    
    raw = _appointments().find_one(
        
        {"$or": [{"_id": key},
                 {"codigo": key.upper()}]
         }
    )
    return AppointmentDocument.from_doc(raw) if raw else None


def appointments_for_inspection(inspection_id: str) -> list[AppointmentDocument]:
    
    cur = _appointments().find({"inspection_id": inspection_id}).sort(
        
        "scheduled_for", ASCENDING
    )
    return [AppointmentDocument.from_doc(r) for r in cur]



def list_appointments(limit: int = 50) -> list[dict[str, Any]]:
    
    cur = _appointments().find().sort("scheduled_for", ASCENDING).limit(limit)
    
    return list(cur)
