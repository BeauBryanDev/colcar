
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.config import get_settings
from app.db.mongo import get_db
from app.models.appointment import AppointmentDocument, code_of, new_appointment_id
from app.models.inspection import InspectionDocument
from app.models.user import UserDocument, normalize_username

logger = logging.getLogger(__name__)

# How many fresh ids to try when a 6-char `codigo` collides.
_CODE_RETRIES = 5

# Reads and writes for the `inspections` and `appointments` collections.


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
        partialFilterExpression={"status": {"$in": ["programada", "confirmada"]}},
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


#  users (admin dashboard)

def _users():
    s = get_settings()
    return get_db(s)[s.users_collection]


def get_user(username: str) -> UserDocument | None:
    """By username, normalised the same way `seed_admin.py` stored it -- `_id`
    IS the normalised username, so this is a primary-key hit."""
    raw = _users().find_one({"_id": normalize_username(username)})
    
    return UserDocument.from_doc(raw) if raw else None


def touch_last_login(username: str) -> None:
    """Record a successful login. Best effort: a failed write must not turn a
    valid login into a 500, so this swallows `PyMongoError` -- unlike every
    other function here, which raises to its caller."""
    try:
        _users().update_one(
            {"_id": normalize_username(username)},
            {"$set": {"last_login_at": datetime.now(timezone.utc)}},
        )
    except PyMongoError as exc:
        logger.warning("could not update last_login_at for %s: %s", username, exc)


def update_password_hash(username: str, password_hash: str) -> None:
    """Used when a successful login finds the stored hash was minted with
    weaker argon2 parameters than the current settings."""
    _users().update_one(
        {"_id": normalize_username(username)},
        {
            "$set": {
                "password_hash": password_hash,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )


#  users CRUD (admin dashboard)

def ensure_user_indexes() -> None:
    """Same indexes `scripts/seed_admin.py` creates, so a cluster that has
    only ever been written by the API is shaped identically to a seeded one."""
    users = _users()
    users.create_index([("username", ASCENDING)], unique=True, name="uniq_username")
    users.create_index([("role", ASCENDING)], name="by_role")


def list_users(
    *,
    role: str | None = None,
    active: bool | None = None,
    limit: int = 100,
) -> list[UserDocument]:
    
    query: dict[str, Any] = {}
    
    if role is not None:
        query["role"] = role
        
    if active is not None:
        query["active"] = active
        
    cur = _users().find(query).sort("username", ASCENDING).limit(limit)
    
    return [UserDocument.from_doc(r) for r in cur]


def count_users(*, role: str | None = None, 
                active: bool | None = None
                ) -> int:
    
    query: dict[str, Any] = {}
    
    if role is not None:
        
        query["role"] = role
        
    if active is not None:
        query["active"] = active
        
    return _users().count_documents(query)


def create_user(doc: UserDocument) -> UserDocument:
    """Insert. `DuplicateKeyError` reaches the caller, which turns it into a
    409 -- an upsert here would silently overwrite an existing account's
    password, which is an update, not a create."""
    _users().insert_one(doc.to_doc())
    
    return doc


def update_user(username: str, 
                changes: dict[str, Any]
                ) -> UserDocument | None:
    """
    Partial update. Returns the document as it is AFTER the write, or None
    when there is no such user.

    `changes` is built by the router from validated fields only -- never a raw
    request body, or a caller could set `password_hash`, `role` or `_id`
    directly.
    """
    if not changes:
        return get_user(username)

    changes = dict(changes)
    changes["updated_at"] = datetime.now(timezone.utc)
    
    raw = _users().find_one_and_update(
        {"_id": normalize_username(username)},
        {"$set": changes},
        return_document=ReturnDocument.AFTER,
    )
    
    return UserDocument.from_doc(raw) if raw else None


#  admin queries (dashboard)

def ensure_admin_indexes() -> None:
    """Indexes the dashboard filters need.

    `inspections.created_at` already exists from `ensure_indexes()`; Qdrant
    taught us to add an index before filtering on a field, not after.
    """
    _appointments().create_index([("scheduled_for", ASCENDING)], name="by_scheduled")
    _appointments().create_index([("status", ASCENDING)], name="by_status")
    _inspections().create_index(
        [("rechazo_rtm_probable", ASCENDING)], 
        name="by_rtm_verdict"
    )


def query_appointments(
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    status: str | None = None,
    codigo: str | None = None,
    limit: int = 100,
) -> list[AppointmentDocument]:
    """Slots are stored in UTC, so `date_from`/`date_to` are compared in UTC --
    the router converts the workshop-local day it was asked about."""
    query: dict[str, Any] = {}
    
    if date_from or date_to:
        window: dict[str, datetime] = {}
        
        if date_from:
            window["$gte"] = date_from
            
        if date_to:
            window["$lte"] = date_to
            
        query["scheduled_for"] = window
        
    if status:
        query["status"] = status
        
    if codigo:
        query["codigo"] = codigo.strip().upper()

    cur = _appointments().find(query).sort("scheduled_for", ASCENDING).limit(limit)
    
    return [AppointmentDocument.from_doc(r) for r in cur]


def count_appointments(
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    status: str | None = None,
    codigo: str | None = None,
) -> int:
    
    query: dict[str, Any] = {}
    
    if date_from or date_to:
        
        window: dict[str, datetime] = {}
        
        if date_from:
            window["$gte"] = date_from
            
        if date_to:
            window["$lte"] = date_to
            
        query["scheduled_for"] = window
        
    if status:
        query["status"] = status
        
    if codigo:
        query["codigo"] = codigo.strip().upper()
        
    return _appointments().count_documents(query)


def set_appointment_status(
    codigo_or_id: str,
    new_status: str, 
    *, 
    notes: str | None = None
) -> AppointmentDocument | None:
    """Move a booking through its lifecycle. None when there is no such
    booking. The *legal* transitions are decided in the router -- the
    repository writes what it is told."""
    changes: dict[str, Any] = {
        "status": new_status,
        "updated_at": datetime.now(timezone.utc),
    }
    if notes is not None:
        changes["notes"] = notes

    key = codigo_or_id.strip()
    
    raw = _appointments().find_one_and_update(
        {"$or": [{"_id": key},
                 {"codigo": key.upper()}
                 ]},
        {"$set": changes},
        return_document=ReturnDocument.AFTER,
    )
    return AppointmentDocument.from_doc(raw) if raw else None


def query_inspections(
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    brand: str | None = None,
    rechazo_rtm_probable: bool | None = None,
    limit: int = 100,
) -> list[InspectionDocument]:
    
    query: dict[str, Any] = {}
    
    if date_from or date_to:
        
        window: dict[str, datetime] = {}
        
        if date_from:
            window["$gte"] = date_from
            
        if date_to:
            window["$lte"] = date_to
            
        query["created_at"] = window
        
    if brand:

        query["vehicle_info.brand"] = {"$regex": f"^{re.escape(brand)}$", "$options": "i"}
        
    if rechazo_rtm_probable is not None:
        
        query["rechazo_rtm_probable"] = rechazo_rtm_probable

    cur = _inspections().find(query).sort("created_at", -1).limit(limit)
    
    return [InspectionDocument.from_doc(r) for r in cur]


def count_inspections(
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    brand: str | None = None,
    rechazo_rtm_probable: bool | None = None,
) -> int:
    
    query: dict[str, Any] = {}
    
    if date_from or date_to:
        window: dict[str, datetime] = {}
        
        if date_from:
            window["$gte"] = date_from
            
        if date_to:
            window["$lte"] = date_to
            
        query["created_at"] = window
        
    if brand:
        query["vehicle_info.brand"] = {"$regex": f"^{re.escape(brand)}$", "$options": "i"}
        
    if rechazo_rtm_probable is not None:
        query["rechazo_rtm_probable"] = rechazo_rtm_probable
        
    return _inspections().count_documents(query)


def delete_user(username: str) -> bool:
    """Hard delete. False when there was nothing to delete.

    The router prefers deactivation (`active: false`) and guards this against
    removing the last admin -- a users collection with no admin locks everyone
    out of the dashboard permanently, with no recovery short of re-running the
    seed script.
    """
    result = _users().delete_one({"_id": normalize_username(username)})
    
    return result.deleted_count > 0
