
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query, status
from fastapi.concurrency import run_in_threadpool
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.auth import AdminUser
from app.core.exceptions import AppError, AuthUnavailableError
from app.core.security import hash_password
from app.db import mongo, repository
from app.models.user import UserDocument, UserRole, normalize_username
from app.schemas.auth import (
    DeletedResponse,
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)

# Admin CRUD over the `users` collection. Every route is admin-only --
# managing accounts is not a `staff` capability, or the role split would be
# decorative.
# Three invariants the routes enforce, none of which the database can:

# - **The password never round-trips.** It comes in as a `SecretStr`, is
#   hashed, and only the hash is stored. Responses are built from
#   `UserDocument.to_public()`, which never carries `password_hash`.
# - **The last active admin cannot be deleted, deactivated, or demoted.** A
#   users collection with no reachable admin locks everyone out permanently;
#   recovery means re-running `seed_admin.py` by hand against the cluster.
# - **An admin cannot demote, deactivate or delete themselves.** Same failure
#   mode, easier to hit by accident, needs a second admin to undo.

# Updates are `exclude_unset`: a field absent from the body is left alone, so
# a PATCH that only flips `active` cannot blank out an email by omission.


logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin:users"])

#  errors specific to this router

class UserNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "usuario_no_encontrado"
    detail = "El usuario no existe."


class UserAlreadyExistsError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "usuario_ya_existe"
    detail = "Ya existe un usuario con ese nombre."


class LastAdminError(AppError):
    """Refusing to remove the last way into the dashboard."""

    status_code = status.HTTP_409_CONFLICT
    code = "ultimo_administrador"
    detail = (
        "No se puede eliminar, desactivar ni degradar al unico administrador "
        "activo. Crea otro administrador primero."
    )


class SelfModificationError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "auto_modificacion"
    detail = (
        "No puedes eliminar, desactivar ni cambiar tu propio rol. "
        "Pidelo a otro administrador."
    )


#  helpers

def _require_mongo() -> None:
    
    if not mongo.is_configured():
        
        raise AuthUnavailableError(log_message="MONGODB_URI is not set")


def _response(user: UserDocument) -> UserResponse:
    
    return UserResponse(**user.to_public())


async def _call(fn, *args, **kwargs):
    """Run a blocking repository call off the event loop and turn a Mongo
    outage into a 503 rather than a 500."""
    try:
        return await run_in_threadpool(fn, *args, **kwargs)
    
    except DuplicateKeyError:
        raise
    
    except PyMongoError as exc:
        raise AuthUnavailableError(log_message=str(exc)) from exc


async def _would_orphan_admins(target: UserDocument) -> bool:
    """True when `target` is the only active admin left.
    """
    if not (target.is_admin and target.active):
        return False
    
    remaining = await _call(
        repository.count_users, 
        role=UserRole.ADMIN.value, 
        active=True
    )
    
    return remaining <= 1


#  routes

# GET    /api/admin/users ->  list, filterable by role / active
@router.get("/admin/users", 
            response_model=UserListResponse)
async def list_users(
    _: AdminUser,
    role: UserRole | None = Query(default=None),
    active: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> UserListResponse:
    _require_mongo()
    
    role_value = role.value if role else None
    
    users = await _call(
        repository.list_users, 
        role=role_value, 
        active=active, 
        limit=limit
    )
    
    total = await _call(repository.count_users, 
                        role=role_value, 
                        active=active)
    
    return UserListResponse(users=[_response(u) for u in users], total=total)


# POST   /api/admin/users -> create new users by admin role.
@router.post(
    "/admin/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(payload: UserCreateRequest, 
                      actor: AdminUser
                      ) -> UserResponse:
    _require_mongo()

    doc = UserDocument(
        username=payload.username,  # normalised by the model's validator
        password_hash=hash_password(payload.password.get_secret_value()),
        role=payload.role,
        full_name=payload.full_name,
        email=payload.email,
        phone_number=payload.phone_number,
        active=payload.active,
    )
    try:
        await _call(repository.create_user, doc)
        
    except DuplicateKeyError as exc:
        
        raise UserAlreadyExistsError(
            log_message=f"username {doc.username!r} already exists"
        ) from exc

    logger.info("%s created user %s (%s)", 
                actor.username, 
                doc.username, 
                doc.role.value)
    
    return _response(doc)

# GET    /api/admin/users/{username} read one
@router.get("/admin/users/{username}", 
            response_model=UserResponse)
async def get_user(username: str, _: AdminUser) -> UserResponse:
    _require_mongo()
    
    user = await _call(repository.get_user, username)
    if user is None:
        
        raise UserNotFoundError(log_message=f"user {username!r} not found")
    
    return _response(user)


# PATCH  /api/admin/users/{username} update any field, including the password
@router.patch("/admin/users/{username}", 
              response_model=UserResponse)
async def update_user(
    username: str, 
    payload: UserUpdateRequest, 
    actor: AdminUser
) -> UserResponse:
    _require_mongo()

    target = await _call(repository.get_user, username)
    if target is None:
        
        raise UserNotFoundError(log_message=f"user {username!r} not found")

    # exclude_unset, not exclude_none: an omitted field is left alone, while an
    # explicit full_name": null really does clear it.
    supplied = payload.model_dump(exclude_unset=True)
    is_self = target.username == actor.username

    demoting = "role" in supplied and payload.role is not UserRole.ADMIN
    deactivating = supplied.get("active") is False

    if is_self and (demoting or deactivating):
        raise SelfModificationError(
            log_message=f"{actor.username!r} tried to demote/deactivate itself"
        )
    if (demoting or deactivating) and await _would_orphan_admins(target):
        raise LastAdminError(
            log_message=f"{target.username!r} is the last active admin"
        )

    changes: dict[str, Any] = {}
    
    for field in ("full_name", "email", "phone_number", "active"):
        
        if field in supplied:
            
            changes[field] = supplied[field]
            
    if "role" in supplied and payload.role is not None:
        changes["role"] = payload.role.value
        
    if "password" in supplied and payload.password is not None:
        # Hashed here; the clear text never reaches the document or a log.
        changes["password_hash"] = hash_password(payload.password.get_secret_value())

    updated = await _call(repository.update_user, target.username, changes)
    
    if updated is None:  # deleted between the read and the write
        raise UserNotFoundError(log_message=f"user {username!r} disappeared mid-update")

    logger.info(
        "%s updated user %s: %s",
        actor.username,
        updated.username,
        sorted(k for k in changes if k != "password_hash") # complain about password
        + (["password"] if "password_hash" in changes else []), # never show password 
                                                                # enen in the log
    )
    return _response(updated)


#  DELETE /api/admin/users/{username} hard delete
@router.delete("/admin/users/{username}", 
               response_model=DeletedResponse)
async def delete_user(username: str,
                      actor: AdminUser
                      ) -> DeletedResponse:
    """Hard delete. Prefer PATCH {"active": false} -> a deactivated account
    keeps its `last_login_at` and stays auditable."""
    _require_mongo()

    target = await _call(repository.get_user, username)
    
    if target is None:
        raise UserNotFoundError(log_message=f"user {username!r} not found")
    
    if target.username == actor.username:
        raise SelfModificationError(
            log_message=f"{actor.username!r} tried to delete itself"
        )
        
    if await _would_orphan_admins(target):
        raise LastAdminError(log_message=f"{target.username!r} is the last active admin")

    deleted = await _call(repository.delete_user, 
                          target.username)
    
    logger.info("%s deleted user %s", 
                actor.username, 
                
                target.username)
    
    return DeletedResponse(username=normalize_username(username), 
                           deleted=bool(deleted))
