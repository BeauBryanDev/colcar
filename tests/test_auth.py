"""Admin auth: hashing, JWT, the role guard, and the users CRUD rules.

Offline like the rest of the suite. Mongo is never reached: every test that
needs the `users` collection monkeypatches `app.db.repository` and
`app.db.mongo.is_configured` instead, which is also what proves the routes go
through the repository rather than touching a collection directly.

The rules pinned here are the ones whose failure is silent:
  - the stored document never carries the clear-text password
  - a wrong username and a wrong password are indistinguishable, in body and
    in cost
  - `alg` is pinned, so a `none`-algorithm token is rejected
  - the last active admin cannot be deleted, deactivated or demoted
  - a PATCH that omits a field leaves it alone
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core import security
from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    AuthUnavailableError,
    TokenExpiredError,
)
from app.models.user import UserDocument, UserRole, normalize_username

PASSWORD = "Beau.Test.Owner*1945"


#  fixtures: an in-memory stand-in for the users collection

class FakeUsers:
    """Just enough of `app.db.repository`'s user functions to drive the
    routes. Keyed by normalised username, exactly like `_id` in Mongo."""

    def __init__(self, users: list[UserDocument]):
        self._by_name = {u.username: u for u in users}

    def get_user(self, username):
        return self._by_name.get(normalize_username(username))

    def list_users(self, *, role=None, active=None, limit=100):
        out = [
            u
            for u in self._by_name.values()
            if (role is None or u.role.value == role)
            and (active is None or u.active == active)
        ]
        return sorted(out, key=lambda u: u.username)[:limit]

    def count_users(self, *, role=None, active=None):
        return len(self.list_users(role=role, active=active))

    def create_user(self, doc):
        from pymongo.errors import DuplicateKeyError

        if doc.username in self._by_name:
            raise DuplicateKeyError("uniq_username")
        self._by_name[doc.username] = doc
        return doc

    def update_user(self, username, changes):
        user = self.get_user(username)
        if user is None:
            return None
        data = user.model_dump()
        data.update({k: v for k, v in changes.items() if k != "updated_at"})
        updated = UserDocument(**data)
        self._by_name[updated.username] = updated
        return updated

    def delete_user(self, username):
        return self._by_name.pop(normalize_username(username), None) is not None

    def touch_last_login(self, username):
        return None

    def update_password_hash(self, username, password_hash):
        self.update_user(username, {"password_hash": password_hash})


def _user(name, role=UserRole.ADMIN, *, active=True, password=PASSWORD):
    return UserDocument(
        username=name,
        password_hash=security.hash_password(password),
        role=role,
        active=active,
    )


@pytest.fixture
def fake_users(monkeypatch):
    store = FakeUsers([_user("beauman", UserRole.ADMIN)])

    monkeypatch.setattr("app.db.mongo.is_configured", lambda *a, **k: True)
    for fn in (
        "get_user",
        "list_users",
        "count_users",
        "create_user",
        "update_user",
        "delete_user",
        "touch_last_login",
        "update_password_hash",
    ):
        monkeypatch.setattr(f"app.db.repository.{fn}", getattr(store, fn))
    return store


@pytest.fixture
def auth_client(client, fake_users):
    """The app's TestClient with the users collection stubbed."""
    return client


def _login(client, username="beauman", password=PASSWORD):
    return client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )


def _bearer(client, username="beauman", password=PASSWORD):
    r = _login(client, username, password)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['accessToken']}"}


#  password hashing

def test_hash_is_argon2id_and_verifies():
    h = security.hash_password(PASSWORD)
    assert h.startswith("$argon2id$")
    assert PASSWORD not in h
    assert security.verify_password(PASSWORD, h)
    assert not security.verify_password(PASSWORD + "x", h)


def test_hash_is_salted_so_two_hashes_differ():
    # Why seed_admin.py must not re-hash on a re-run: same password, different
    # digest, so a ReplaceOne would churn the document every time.
    assert security.hash_password(PASSWORD) != security.hash_password(PASSWORD)


def test_unknown_user_still_pays_the_argon2_cost():
    """No early return for a missing user: the timing must not say which
    usernames exist. Both paths run a real verification."""
    h = security.hash_password(PASSWORD)

    t0 = time.perf_counter()
    security.verify_password(PASSWORD, h)
    real = time.perf_counter() - t0

    t0 = time.perf_counter()
    assert security.verify_password(PASSWORD, None) is False
    missing = time.perf_counter() - t0

    # Same order of magnitude -- not a strict bound, which would be flaky on a
    # loaded box, but enough to catch an early `return False`.
    assert missing > real / 5


#  JWT

def test_token_round_trips_with_expected_claims():
    token, expires_at = security.create_access_token("beauman", "admin")
    claims = security.decode_access_token(token)

    assert claims["sub"] == "beauman"
    assert claims["role"] == "admin"
    assert claims["iss"] == get_settings().jwt_issuer
    assert claims["exp"] == int(expires_at.timestamp())


def test_expired_token_raises_token_expired():
    token, _ = security.create_access_token("beauman", "admin", expires_minutes=-1)
    with pytest.raises(TokenExpiredError):
        security.decode_access_token(token)


def test_token_signed_with_another_key_is_rejected():
    forged = jwt.encode(
        {
            "sub": "beauman",
            "role": "admin",
            "iss": get_settings().jwt_issuer,
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        },
        "a-different-secret-that-is-long-enough-0123456789",
        algorithm="HS256",
    )
    with pytest.raises(AuthenticationError):
        security.decode_access_token(forged)


def test_alg_none_token_is_rejected():
    """The classic JWT forgery: an unsigned token asking to be trusted.
    `decode_access_token` pins the algorithm instead of reading the header."""
    unsigned = jwt.encode(
        {"sub": "beauman", "role": "admin", "iss": get_settings().jwt_issuer,
         "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())},
        key="",
        algorithm="none",
    )
    with pytest.raises(AuthenticationError):
        security.decode_access_token(unsigned)


def test_wrong_issuer_is_rejected(monkeypatch):
    token, _ = security.create_access_token("beauman", "admin")
    monkeypatch.setattr(get_settings(), "jwt_issuer", "someone-else")
    with pytest.raises(AuthenticationError):
        security.decode_access_token(token)


def test_extra_claims_cannot_overwrite_role():
    token, _ = security.create_access_token(
        "beauman", "user", extra_claims={"role": "admin", "sub": "someone"}
    )
    claims = security.decode_access_token(token)
    assert claims["role"] == "user"
    assert claims["sub"] == "beauman"


def test_missing_jwt_secret_refuses_to_sign(monkeypatch):
    """No default signing key: a repo-known secret would let anyone mint an
    admin token."""
    monkeypatch.setattr(get_settings(), "jwt_secret", None)
    with pytest.raises(AuthUnavailableError):
        security.create_access_token("beauman", "admin")


#  login endpoint

def test_login_returns_camelcase_token_and_no_hash(auth_client):
    r = _login(auth_client)
    assert r.status_code == 200
    body = r.json()

    assert body["tokenType"] == "bearer"
    assert body["expiresIn"] == get_settings().jwt_access_token_minutes * 60
    assert body["user"]["username"] == "beauman"
    assert body["user"]["role"] == "admin"
    # The wire is camelCase (app/schemas/common.py) ...
    assert "accessToken" in body and "access_token" not in body
    # ... and the hash never leaves the backend.
    assert "passwordHash" not in body["user"]
    assert PASSWORD not in r.text


@pytest.mark.parametrize(
    "username,password",
    [
        ("beauman", "wrong-password"),
        ("nobody", PASSWORD),
        ("nobody", "wrong-password"),
    ],
)
def test_every_bad_login_returns_the_same_401(auth_client, username, password):
    """A wrong password and an unknown user must be indistinguishable, or the
    endpoint enumerates usernames."""
    r = _login(auth_client, username, password)
    assert r.status_code == 401
    assert r.json()["code"] == "credenciales_invalidas"


def test_inactive_account_cannot_log_in(auth_client, fake_users):
    fake_users.create_user(_user("expleado", UserRole.STAFF, active=False))
    r = _login(auth_client, "expleado")
    assert r.status_code == 401
    assert r.json()["code"] == "credenciales_invalidas"


def test_login_is_case_insensitive_on_username(auth_client):
    assert _login(auth_client, "BeauMan").status_code == 200


def test_login_without_mongo_is_503_not_a_500(client, monkeypatch):
    monkeypatch.setattr("app.db.mongo.is_configured", lambda *a, **k: False)
    r = _login(client)
    assert r.status_code == 503
    assert r.json()["code"] == "autenticacion_no_disponible"


#  the guard

def test_me_returns_the_token_holder(auth_client):
    r = auth_client.get("/api/auth/me", headers=_bearer(auth_client))
    assert r.status_code == 200
    assert r.json()["username"] == "beauman"


def test_guarded_route_without_a_token_is_401(auth_client):
    r = auth_client.get("/api/admin/users")
    assert r.status_code == 401
    assert r.json()["code"] == "token_faltante"


def test_staff_token_cannot_reach_an_admin_route(auth_client, fake_users):
    fake_users.create_user(_user("secretaria", UserRole.STAFF))
    headers = _bearer(auth_client, "secretaria")

    assert auth_client.get("/api/auth/me", headers=headers).status_code == 200
    r = auth_client.get("/api/admin/users", headers=headers)
    assert r.status_code == 403
    assert r.json()["code"] == "permiso_denegado"


def test_deactivated_after_the_token_was_issued_loses_access(auth_client, fake_users):
    """The role rides in the claim, but `active` is re-read from the database
    on every request -- so disabling an account takes effect immediately, not
    when the token expires."""
    headers = _bearer(auth_client)
    fake_users.update_user("beauman", {"active": False})

    r = auth_client.get("/api/auth/me", headers=headers)
    assert r.status_code == 401
    assert r.json()["code"] == "cuenta_inactiva"


def test_token_for_a_deleted_user_is_rejected(auth_client, fake_users):
    headers = _bearer(auth_client)
    fake_users.delete_user("beauman")
    assert auth_client.get("/api/auth/me", headers=headers).status_code == 401


def test_role_guard_is_ranked_not_equality():
    admin = _user("a", UserRole.ADMIN)
    staff = _user("s", UserRole.STAFF)
    plain = _user("u", UserRole.USER)

    assert admin.has_at_least(UserRole.STAFF)  # an owner never needs 2 accounts
    assert staff.has_at_least(UserRole.STAFF)
    assert not plain.has_at_least(UserRole.STAFF)
    assert not staff.has_at_least(UserRole.ADMIN)


#  users CRUD

def test_create_hashes_the_password_and_never_echoes_it(auth_client, fake_users):
    r = auth_client.post(
        "/api/admin/users",
        headers=_bearer(auth_client),
        json={
            "username": "Secretaria",
            "password": "una-clave-larga-123",
            "role": "staff",
            "full_name": "La secretaria",
        },
    )
    assert r.status_code == 201
    assert "una-clave-larga-123" not in r.text
    assert "passwordHash" not in r.text

    stored = fake_users.get_user("secretaria")
    assert stored.username == "secretaria"  # normalised
    assert stored.password_hash.startswith("$argon2id$")
    assert security.verify_password("una-clave-larga-123", stored.password_hash)


def test_create_rejects_a_duplicate_username(auth_client):
    r = auth_client.post(
        "/api/admin/users",
        headers=_bearer(auth_client),
        json={"username": "beauman", "password": "otra-clave-larga-1"},
    )
    assert r.status_code == 409
    assert r.json()["code"] == "usuario_ya_existe"


def test_create_forbids_smuggling_a_password_hash(auth_client):
    """ApiRequest sets extra='forbid', so a client cannot set fields the
    router is supposed to compute."""
    r = auth_client.post(
        "/api/admin/users",
        headers=_bearer(auth_client),
        json={
            "username": "colado",
            "password": "una-clave-larga-123",
            "password_hash": "$argon2id$fake",
        },
    )
    assert r.status_code == 422


def test_patch_leaves_omitted_fields_alone(auth_client, fake_users):
    fake_users.create_user(
        UserDocument(
            username="secretaria",
            password_hash=security.hash_password(PASSWORD),
            role=UserRole.STAFF,
            email="secre@taller.co",
            full_name="La secretaria",
        )
    )
    r = auth_client.patch(
        "/api/admin/users/secretaria",
        headers=_bearer(auth_client),
        json={"phone_number": "3001234567"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["phoneNumber"] == "3001234567"
    assert body["email"] == "secre@taller.co"  # not blanked by omission
    assert body["fullName"] == "La secretaria"


def test_patch_can_reset_a_password(auth_client, fake_users):
    fake_users.create_user(_user("secretaria", UserRole.STAFF))
    r = auth_client.patch(
        "/api/admin/users/secretaria",
        headers=_bearer(auth_client),
        json={"password": "nueva-clave-larga-9"},
    )
    assert r.status_code == 200
    assert "nueva-clave-larga-9" not in r.text
    assert security.verify_password(
        "nueva-clave-larga-9", fake_users.get_user("secretaria").password_hash
    )


def test_patch_can_change_a_role(auth_client, fake_users):
    fake_users.create_user(_user("secretaria", UserRole.USER))
    r = auth_client.patch(
        "/api/admin/users/secretaria",
        headers=_bearer(auth_client),
        json={"role": "staff"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "staff"
    assert fake_users.get_user("secretaria").role is UserRole.STAFF


def test_last_active_admin_cannot_be_deleted(auth_client, fake_users):
    """A users collection with no reachable admin locks everyone out of the
    dashboard, with no recovery short of re-running the seed script."""
    fake_users.create_user(_user("otro", UserRole.ADMIN))
    headers = _bearer(auth_client, "otro")

    # beauman is not the last admin while `otro` exists -- deletion is allowed.
    assert auth_client.delete(
        "/api/admin/users/beauman", headers=headers
    ).status_code == 200

    # `otro` is now the only admin, and is also acting on itself.
    r = auth_client.delete("/api/admin/users/otro", headers=headers)
    assert r.status_code == 409


def test_last_active_admin_cannot_be_demoted(auth_client, fake_users):
    fake_users.create_user(_user("otro", UserRole.ADMIN))
    headers = _bearer(auth_client, "otro")
    r = auth_client.patch(
        "/api/admin/users/beauman", headers=headers, json={"role": "staff"}
    )
    assert r.status_code == 200  # two admins: fine

    r = auth_client.patch(
        "/api/admin/users/otro", headers=headers, json={"role": "staff"}
    )
    assert r.status_code == 409
    assert r.json()["code"] in {"ultimo_administrador", "auto_modificacion"}


def test_admin_cannot_deactivate_itself(auth_client, fake_users):
    fake_users.create_user(_user("otro", UserRole.ADMIN))
    r = auth_client.patch(
        "/api/admin/users/beauman",
        headers=_bearer(auth_client),
        json={"active": False},
    )
    assert r.status_code == 409
    assert r.json()["code"] == "auto_modificacion"


def test_list_filters_by_role_and_hides_hashes(auth_client, fake_users):
    fake_users.create_user(_user("secretaria", UserRole.STAFF))
    r = auth_client.get("/api/admin/users?role=staff", headers=_bearer(auth_client))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["users"][0]["username"] == "secretaria"
    assert "passwordHash" not in r.text
    assert "$argon2id$" not in r.text


def test_get_unknown_user_is_404(auth_client):
    r = auth_client.get("/api/admin/users/nadie", headers=_bearer(auth_client))
    assert r.status_code == 404
    assert r.json()["code"] == "usuario_no_encontrado"


def test_customer_endpoints_stay_public(auth_client):
    """The guard is applied per-route, never globally: the SPA sends no token
    and must keep working."""
    r = auth_client.post("/api/inspections/start", json={})
    assert r.status_code < 400
