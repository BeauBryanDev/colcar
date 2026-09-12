
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings, get_settings

_DUMMY_PASSWORD = "not-a-real-password"


@lru_cache
def _hasher() -> PasswordHasher:
    s: Settings = get_settings()
    return PasswordHasher(
        time_cost=s.argon2_time_cost,
        memory_cost=s.argon2_memory_cost,
        parallelism=s.argon2_parallelism,
    )


@lru_cache
def _dummy_hash() -> str:
    return _hasher().hash(_DUMMY_PASSWORD)

# Password hashing and JWT minting for the admin dashboard.

def hash_password(password: str) -> str:
    """argon2id digest, self-describing (`$argon2id$v=19$m=...`)."""
    if not password:
        raise ValueError("password must not be empty")
    
    return _hasher().hash(password)


def verify_password(password: str, 
                    password_hash: str | None
                    ) -> bool:
    """False, never an exception, for a wrong password, a corrupt hash, or a
    user that does not exist (`password_hash=None`) -- and the None case still
    pays the full argon2 cost, so login timing does not leak which usernames
    are real."""
    target = password_hash or _dummy_hash()
    try:
        _hasher().verify(target, password)
        
    except (VerifyMismatchError, 
            VerificationError, 
            InvalidHashError):
        return False
    
    return password_hash is not None


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash was minted with weaker parameters than the
    current settings -- re-hash on the next successful login."""
    try:
        return _hasher().check_needs_rehash(password_hash)
    
    except InvalidHashError:
        return True


#  JWT

def _signing_key(s: Settings | None = None) -> str:
    """The HS256 secret, or a 503.
    """
    from app.core.exceptions import AuthUnavailableError

    settings = s or get_settings()
    
    if settings.jwt_secret is None:
        raise AuthUnavailableError(log_message="JWT_SECRET is not set")
    
    key = settings.jwt_secret.get_secret_value()
    
    if len(key) < 32:
        raise AuthUnavailableError(
            log_message=f"JWT_SECRET is too short ({len(key)} chars, need >= 32)"
        )
    return key


def create_access_token(
    username: str,
    role: str,
    *,
    expires_minutes: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, datetime]:
    """Sign an access token. Returns `(token, expires_at)`.

    The expiry is returned rather than left for the caller to recompute, so
    the value the SPA is told matches the one in the signature exactly.

    Claims: `sub` (username), `role`, `iss`, `iat`, `exp`. Nothing sensitive --
    a JWT is signed, not encrypted, and anyone holding it can read the payload.
    """
    s = get_settings()
    key = _signing_key(s)

    now = datetime.now(timezone.utc)
    minutes = s.jwt_access_token_minutes if expires_minutes is None else expires_minutes
    expires_at = now + timedelta(minutes=minutes)

    payload: dict[str, Any] = {
        "sub": username,
        "role": role,
        "iss": s.jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if extra_claims:
        # Never let a caller overwrite the claims the guard trusts.
        reserved = payload.keys()
        
        payload.update(
            {k: v for k, v in extra_claims.items() if k not in reserved}
        )

    token = jwt.encode(payload, key, algorithm=s.jwt_algorithm)
    return token, expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify signature, expiry and issuer; return the claims.

    Raises `TokenExpiredError` or `AuthenticationError` -- never returns a
    partially trusted payload. The algorithm is pinned to the configured one:
    accepting whatever the token's own header asks for is the classic JWT
    forgery (`alg: none`, or HS256 verified against an RS256 public key).
    """
    from app.core.exceptions import AuthenticationError, TokenExpiredError

    s = get_settings()
    key = _signing_key(s)
    
    try:
        return jwt.decode(
            token,
            key,
            algorithms=[s.jwt_algorithm],
            issuer=s.jwt_issuer,
            options={"require": ["exp", "sub", "role"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError(log_message="token expired") from exc
    
    except jwt.InvalidTokenError as exc:
        # Bad signature, wrong issuer, missing claim, malformed -- all the
        # same 401 to the caller; the reason stays in the log.
        raise AuthenticationError(
            
            detail="Token invalido.",
            code="token_invalido",
            log_message=f"invalid token: {exc}",
            
        ) from exc
