
from __future__ import annotations

from datetime import datetime

from pydantic import Field, SecretStr

from app.models.user import UserRole
from app.schemas.common import ApiRequest, ApiResponse

# Request/response shapes for POST /api/auth/login. 

class LoginRequest(ApiRequest):
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1)


class UserResponse(ApiResponse):
    """The authenticated account -- `UserDocument.to_public()`, never the
    hash. Also what `GET /api/auth/me` returns."""

    username: str
    role: str
    full_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    active: bool = True


class TokenResponse(ApiResponse):
    """`expiresAt` is the exact `exp` that was signed, so the SPA never has to
    re-derive it from `expiresIn` and drift by a round trip."""

    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    expires_in: int  # seconds, for a client that prefers a duration
    user: UserResponse


#  admin CRUD over the users collection

class UserCreateRequest(ApiRequest):
    """`ApiRequest` forbids extra keys, so a client cannot smuggle
    `password_hash`, `_id` or `last_login_at` into a create."""

    username: str = Field(min_length=3, max_length=64)
    password: SecretStr = Field(min_length=8)
    role: UserRole = UserRole.USER
    full_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    active: bool = True


class UserUpdateRequest(ApiRequest):
    """Partial update [[patch]] every field optional, and **`None` means "not
    supplied", not "set to null"**. The router only writes the fields that
    were explicitly present in the body (`model_dump(exclude_unset=True)`),
    so omitting `email` leaves it alone rather than erasing it.

    `password` is here so an admin can reset one; it is hashed by the router
    and the clear text never reaches the document.
    """
    password: SecretStr | None = Field(default=None, min_length=8)
    role: UserRole | None = None
    full_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    active: bool | None = None


class UserListResponse(ApiResponse):
    users: list[UserResponse]
    total: int


class DeletedResponse(ApiResponse):
    username: str
    deleted: bool
