
from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pymongo.errors import PyMongoError

from app.core.auth import CurrentUser
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, AuthUnavailableError
from app.core.security import (
    create_access_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.db import mongo, repository
from app.models.user import UserDocument
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# Only the dashboard uses these. The customer-facing inspection and chat
# endpoints stay public -- the SPA never sends a token.
#  CyberSec Concerns:  
# Every failure path returns the same 401 body. // Unknown user, wrong
# password and disabled account are indistinguishable to the caller, and the
# wrong-username path still pays the full argon2 cost (`verify_password` burns a
# dummy hash), so neither the response nor its timing says which usernames
# exist. `log_message` records which it really was, for use in the logs.

def _user_response(user: UserDocument) -> UserResponse:
    # to_public() is the single place that decides what leaves the backend;
    # building the response from it means the hash cannot be added by accident.
    return UserResponse(**user.to_public())


def _authenticate(username: str, password: str) -> UserDocument:
    """Blocking: password verification is ~50 ms of argon2 by design. Called
    through `run_in_threadpool` so it cannot stall the event loop."""
    # I do not want Pentesting on my SPA. 
    user = repository.get_user(username)

    # Note the ordering: verify FIRST, decide SECOND. Returning early on an
    # unknown user would make a wrong username measurably faster than a wrong
    # password. `verify_password(pw, None)` hashes against a dummy instead.
    stored_hash = user.password_hash if user else None # preventuser enumeration
    password_ok = verify_password(password, stored_hash) # not timing attackable

    if user is None:
        raise AuthenticationError(log_message=f"unknown user {username!r}")
    
    if not password_ok:
        raise AuthenticationError(log_message=f"bad password for {username!r}")
    
    if not user.active:
        raise AuthenticationError(log_message=f"user {username!r} is inactive")

    # The stored hash predates a cost increase: re-hash now, while we hold the
    # only clear-text copy we will ever see. Best effort, a failed write must
    # not fail an otherwise valid login.
    if needs_rehash(user.password_hash):
        
        try:
            repository.update_password_hash(user.username, hash_password(password))
            logger.info("rehashed password for %s at current argon2 cost",
                        user.username)
            
        except PyMongoError as exc:
            logger.warning("could not rehash password for %s: %s", user.username, exc)

    repository.touch_last_login(user.username)
    
    return user


# Auth Admin endpoints

# POST /api/auth/login   username + password -> JWT
@router.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    if not mongo.is_configured():
        raise AuthUnavailableError(log_message="MONGODB_URI is not set")

    try:
        user = await run_in_threadpool(
            _authenticate, payload.username, payload.password.get_secret_value()
        )
    except PyMongoError as exc:
        # Fail closed -- an unreachable users collection is not a login.
        raise AuthUnavailableError(log_message=str(exc)) from exc

    token, expires_at = create_access_token(user.username, 
                                            user.role.value)
    
    logger.info("login ok: %s (%s)", 
                user.username, 
                user.role.value)

    return TokenResponse(
        access_token=token,
        expires_at=expires_at,
        expires_in=get_settings().jwt_access_token_minutes * 60,
        user=_user_response(user),
    )


# GET  /api/auth/me      the account behind the bearer token
@router.get("/auth/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    """Who the bearer token belongs to. The SPA calls this on load to decide
    whether a stored token is still good before rendering the dashboard."""
    return _user_response(user)



