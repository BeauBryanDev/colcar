
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.config import get_settings
from app.db.mongo import get_db
from app.models.appointment import (
    AppointmentDocument,
    Discount,
    code_of,
    new_appointment_id,
)
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

def _discounts():
    from app.core.config import get_settings
    from app.db.mongo import get_db
 
    s = get_settings()
    return get_db(s)[s.discounts_collection]
 

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
    # One vehicle at a time: no two ACTIVE appointments share a slot, whatever
    # inspection they belong to. THIS is the double-booking guard --
    # check_availability is only the friendly pre-check, and two callers can
    # both read "free" before either writes.
    appts.create_index(
        [("scheduled_for", ASCENDING)],
        unique=True,
        partialFilterExpression={"status": {"$in": ["programada", "confirmada"]}},
        name="uniq_active_slot",
    )
    _inspections().create_index([("created_at", ASCENDING)], name="by_created")


def _counters():
    s = get_settings()
    return get_db(s)[s.counters_collection]


#  discounts
def ensure_discount_indexes() -> None:
    """Idempotent. Call from warmup alongside ensure_indexes().
 
    A discount is granted at most once per customer. The unique index on the
    customer key is the real gate: even if the tool logic is bypassed, Mongo
    refuses a second grant for the same email/plate.
    """
    d = _discounts()
    d.create_index([("discount_id", ASCENDING)], unique=True, name="uniq_discount_id")
    d.create_index([("customer_key", ASCENDING)], unique=True, name="uniq_customer_key")
    d.create_index([("created_at", ASCENDING)], name="by_created")
    d.create_index([("ticket_number", ASCENDING)], unique=True, sparse=True,
                   name="uniq_ticket_number")

#  inspections

def save_inspection(doc: InspectionDocument) -> None:
    
    _inspections().replace_one({"_id": doc.id}, doc.to_doc(), upsert=True)


def get_inspection(inspection_id: str) -> InspectionDocument | None:
    
    raw = _inspections().find_one({"_id": inspection_id})
    
    return InspectionDocument.from_doc(raw) if raw else None


def slot_is_available(scheduled_for: datetime) -> bool:
    """True when no ACTIVE appointment occupies this exact UTC slot.
 
    'Active' = programada or confirmada. Cancelled appointments do not block.
    """
    hit = _appointments().find_one(
        {
            "scheduled_for": scheduled_for,
            "status": {"$in": ["programada", "confirmada"]},
        },
        projection={"_id": 1},
    )
    return hit is None
 

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


def find_appointment_by_email_or_plate(
    email: str | None, plate: str | None,
    exclude_inspection_id: str | None = None,
) -> bool:
    """True when a prior appointment exists for this email OR plate.
 
    Both are stored on the appointment: customer.email and
    car_info.license_plate. Plate must be passed already normalised (ABC123),
    the same form make_appointment stores.
    """
    conditions: list[dict[str, Any]] = []
    
    if email:
        conditions.append({"customer.email": email})
        
    if plate:
        conditions.append({"car_info.license_plate": plate})
        
    if not conditions:
        return False

    query: dict[str, Any] = {"$or": conditions}
    # The booking made from THIS inspection does not make its own customer a
    # returning one: otherwise bargaining after booking is impossible.
    if exclude_inspection_id:
        query["inspection_id"] = {"$ne": exclude_inspection_id}

    hit = _appointments().find_one(query, projection={"_id": 1})

    return hit is not None



def verify_appointment_owner(
    codigo: str, 
    email: str, 
    plate: str
) -> AppointmentDocument | None:
    """Return the appointment only if BOTH email and plate match its stored
    customer and vehicle. None on any mismatch, including a valid code that
    belongs to someone else.
 
    """
    doc = get_appointment(codigo)
    
    if doc is None:
        return None
    
    if doc.customer.email.strip().lower() != email.strip().lower():
        return None
    
    if doc.car_info.license_plate != plate:
        return None
    
    return doc


def reschedule_appointment(
    codigo_or_id: str, 
    new_scheduled_for: datetime, 
    new_scheduled_local: str
) -> AppointmentDocument | None:
    """Move an ACTIVE appointment to a new slot. None if there is no such
    appointment, or it is not programada/confirmada (already cancelled or
    attended appointments cannot be moved).
    """
    key = codigo_or_id.strip()
    
    raw = _appointments().find_one_and_update(
        {
            "$or": [{"_id": key}, {"codigo": key.upper()}],
            "status": {"$in": ["programada", "confirmada"]},
        },
        {
            "$set": {
                "scheduled_for": new_scheduled_for,
                "scheduled_local": new_scheduled_local,
                "updated_at": datetime.now(timezone.utc),
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    # Raises DuplicateKeyError (via the uniq_active_slot index) if another
    # active appointment already holds the new slot.
    return AppointmentDocument.from_doc(raw) if raw else None


#  Inspections

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


# Persist a grante discovered by the agent tool.
def next_ticket_number(prefix: str = "TKT", width: int = 6) -> str:
    """Mint the next ticket number, e.g. TKT-000042.

    One atomic `$inc` on a single counter document: two grants racing cannot
    read the same value, which a read-then-write would allow. Numbers can have
    gaps (a mint whose grant then fails is not reused) -- a gap is harmless,
    a duplicate ticket at the counter is not.
    """
    doc = _counters().find_one_and_update(
        {"_id": "ticket"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return f"{prefix}-{int(doc['seq']):0{width}d}"


def record_discount(doc: dict[str, Any]) -> None:
    _discounts().insert_one(doc)
 
 
def get_discount(discount_id: str) -> dict[str, Any] | None:
    
    return _discounts().find_one({"discount_id": discount_id.strip().upper()})
 
 
def get_discount_for_inspection(inspection_id: str) -> dict[str, Any] | None:
    """A discount already granted for this inspection, so a booking made AFTER
    the grant still gets it applied."""
    return _discounts().find_one({"inspection_id": inspection_id})


def apply_discount_to_appointments(
    inspection_id: str, code: str, percent: int, ticket_number: str | None = None
) -> list[AppointmentDocument]:
    """Write a granted discount onto every ACTIVE booking of this inspection.

    The stored `estimated_repair_cost_cop` becomes what the customer owes; the
    pre-discount figure moves into `discount.original_cost_cop`. Already
    discounted bookings are skipped, so a re-grant cannot compound.
    """
    updated: list[AppointmentDocument] = []
    cur = _appointments().find(
        {
            "inspection_id": inspection_id,
            "status": {"$in": ["programada", "confirmada"]},
            "discount": None,
        }
    )
    for raw in list(cur):
        
        doc = AppointmentDocument.from_doc(raw)
        original = doc.estimated_repair_cost_cop
        
        if not original or original <= 0:
            continue
        
        doc.discount = Discount(
            code=code, 
            percent=percent, 
            original_cost_cop=original,
            ticket_number=ticket_number,
        )
        
        doc.estimated_repair_cost_cop = round(original * (1 - percent / 100))
        doc.updated_at = datetime.now(timezone.utc)
        
        _appointments().update_one(
            {"_id": doc.id},
            {"$set": {
                "discount": doc.discount.model_dump(),
                "estimated_repair_cost_cop": doc.estimated_repair_cost_cop,
                "updated_at": doc.updated_at,
            }},
        )
        updated.append(doc)
        
    return updated


def get_discount_by_customer_key(customer_key: str) -> dict[str, Any] | None:
    """Used by grant_discount to return the existing code when a customer who
    already has a discount tries to get a second one."""
    return _discounts().find_one({"customer_key": customer_key})