
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class UserRole(str, Enum):
    """Ordered least- to most-privileged; compare with `has_at_least()`, never
    with `<` on the enum itself (str Enum compares alphabetically)."""

    USER = "user"
    STAFF = "staff"
    ADMIN = "admin"


_ROLE_RANK: dict[UserRole, int] = {
    UserRole.USER: 0,
    UserRole.STAFF: 1,
    UserRole.ADMIN: 2,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_username(username: str) -> str:
    """Usernames are matched case- and whitespace-insensitively, the same way
    defect labels are normalised project-wide."""
    return username.strip().lower()

# User  collection::the accounts behind the admin dashboard.

class UserDocument(BaseModel):
    id: str = Field(default="", alias="_id")
    username: str
    password_hash: str
    role: UserRole = UserRole.USER

    full_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    active: bool = True

    last_login_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    model_config = {"populate_by_name": True, "use_enum_values": False}

    @field_validator("username", mode="before")
    @classmethod
    def _normalize(cls, v: object) -> object:
        return normalize_username(v) if isinstance(v, str) else v

    def model_post_init(self, __context: Any) -> None:
        if not self.id:
            self.id = self.username

    def has_at_least(self, role: UserRole) -> bool:
        return _ROLE_RANK[self.role] >= _ROLE_RANK[role]

    @property
    def is_admin(self) -> bool:
        return self.role is UserRole.ADMIN

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "UserDocument":
        return cls.model_validate(doc)

    def to_doc(self) -> dict[str, Any]:
        doc = self.model_dump(by_alias=True)
        doc["role"] = self.role.value
        return doc

    def to_public(self) -> dict[str, Any]:
        """Safe to return over HTTP or put in a JWT payload -- no hash."""
        return {
            "username": self.username,
            "role": self.role.value,
            "full_name": self.full_name,
            "email": self.email,
            "phone_number": self.phone_number,
            "active": self.active,
        }
