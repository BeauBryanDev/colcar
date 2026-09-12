
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pymongo.errors import PyMongoError

from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    AuthUnavailableError,
)
from app.core.security import decode_access_token
from app.db import mongo, repository
from app.models.user import UserDocument, UserRole

logger = logging.getLogger(__name__)

# auto_error=False so a missing header raises OUR 401 (Spanish detail, the
# app's error envelope) instead of FastAPI's bare {"detail": "Not authenticated"}.
_bearer = HTTPBearer(auto_error=False, scheme_name="AdminBearer")

_Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]

# FastAPI dependencies that guard the admin routes

async def get_current_user(credentials: _Credentials) -> UserDocument:
    """Decode the bearer token and load the account behind it."""
    if credentials is None or not credentials.credentials:
        raise AuthenticationError(
            detail="Falta el token de autenticacion.",
            code="token_faltante",
            log_message="no Authorization: Bearer header",
        )

    claims = decode_access_token(credentials.credentials)
    username = str(claims.get("sub") or "")

    if not mongo.is_configured():
        raise AuthUnavailableError(log_message="MONGODB_URI is not set")
    
    try:
        user = await run_in_threadpool(repository.get_user, username)
        
    except PyMongoError as exc:
        # Fail closed: an unreachable users collection must not be treated as
        # "the token looked fine, let them in".
        raise AuthUnavailableError(log_message=str(exc)) from exc

    if user is None:
        # A validly signed token for an account that has since been deleted.
        raise AuthenticationError(
            log_message=f"token for unknown user {username!r}"
        )
    if not user.active:
        raise AuthenticationError(
            detail="La cuenta esta desactivada.",
            code="cuenta_inactiva",
            log_message=f"user {username!r} is inactive",
        )

    # The claim is the authority for the role only while it matches the stored
    # one; a demotion since the token was signed wins immediately.
    claim_role = str(claims.get("role") or "")
    if claim_role != user.role.value:
        logger.info(
            "role in token (%s) differs from stored (%s) for %s; using stored",
            claim_role,
            user.role.value,
            username,
        )
    return user


CurrentUser = Annotated[UserDocument, Depends(get_current_user)]


def require_role(minimum: UserRole):
    """Dependency factory: 403 unless the account is at least `minimum`.

    Ranked, not equality -- `require_role(UserRole.STAFF)` admits an admin
    too, so an owner never has to hold a second account to use a staff screen.
    """

    async def _guard(user: CurrentUser) -> UserDocument:
        
        if not user.has_at_least(minimum):
            
            raise AuthorizationError(
                log_message=(
                    f"user {user.username!r} has role {user.role.value}, "
                    f"needs at least {minimum.value}"
                )
            )
        return user

    return _guard


# The two guards the admin routes actually use.
AdminUser = Annotated[UserDocument, Depends(require_role(UserRole.ADMIN))]
StaffUser = Annotated[UserDocument, Depends(require_role(UserRole.STAFF))]
