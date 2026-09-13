"""Dashboard queries: role reach, status transitions, and the timezone window.

Offline: `app.db.repository` is monkeypatched, so no cluster is touched. What
is pinned here is the business logic the owner decided on 2026-09-10 --
`staff` reads everything including contact details and may cancel, but the
users collection stays admin-only -- plus the two rules whose failure is
silent: terminal statuses, and the workshop-local date window.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from pymongo.errors import DuplicateKeyError

from app.core import security
from app.core.config import get_settings
from app.models.appointment import AppointmentDocument, CarInfo, Customer
from app.models.inspection import DefectRecord, InspectionDocument
from app.models.user import UserDocument, UserRole
from tests.test_auth import PASSWORD, FakeUsers

BOGOTA = ZoneInfo("America/Bogota")


def _appointment(codigo="ABC123", *, status="programada", when=None):
    when = when or datetime(2026, 9, 12, 15, 0, tzinfo=timezone.utc)
    doc = AppointmentDocument(
        _id=codigo.lower() + "0" * 26,
        inspection_id="insp-1",
        status=status,
        customer=Customer(
            name="Ana Gomez", phone="3001234567", email="ana@example.co"
        ),
        car_info=CarInfo(brand="Renault", model="Logan", year=2018),
        scheduled_for=when,
        scheduled_local="2026-09-12 10:00",
        timezone="America/Bogota",
        estimated_repair_cost_cop=1_250_000,
        inspection_snapshot={"total_cop": 1_250_000},
    )
    doc.codigo = codigo
    return doc


def _inspection(inspection_id="insp-1", *, brand="Renault", rtm=False):
    return InspectionDocument(
        _id=inspection_id,
        status="complete",
        created_at=datetime(2026, 9, 12, 14, 0, tzinfo=timezone.utc),
        vehicle_info={"brand": brand, "model": "Logan", "year": 2018},
        defects=[DefectRecord(pieza="hood", tipo_defecto="dent", severidad="leve")],
        total_cop=1_250_000,
        rechazo_rtm_probable=rtm,
        images_analyzed=2,
    )


class FakeAdminStore:
    """Enough of the repository's admin queries to drive the routes. The
    filters are applied here so the tests exercise the ROUTER's behaviour
    (the timezone window, the transition table), not Mongo's query language."""

    def __init__(self):
        self.appointments = {"ABC123": _appointment()}
        self.inspections = {"insp-1": _inspection()}
        self.status_calls = []
        self.reschedule_calls = []
        self.slot_taken = False

    def _appt_matches(self, a, date_from, date_to, status, codigo):
        if date_from and a.scheduled_for < date_from:
            return False
        if date_to and a.scheduled_for > date_to:
            return False
        if status and a.status != status:
            return False
        if codigo and a.codigo != codigo.strip().upper():
            return False
        return True

    def query_appointments(
        self, *, date_from=None, date_to=None, status=None, codigo=None, limit=100
    ):
        return [
            a
            for a in self.appointments.values()
            if self._appt_matches(a, date_from, date_to, status, codigo)
        ][:limit]

    def count_appointments(self, *, date_from=None, date_to=None, status=None, codigo=None):
        return len(
            self.query_appointments(
                date_from=date_from, date_to=date_to, status=status, codigo=codigo
            )
        )

    def get_appointment(self, codigo_or_id):
        key = codigo_or_id.strip().upper()
        for a in self.appointments.values():
            if a.codigo == key or a.id == codigo_or_id:
                return a
        return None

    def set_appointment_status(self, codigo_or_id, new_status, *, notes=None):
        self.status_calls.append((codigo_or_id, new_status))
        a = self.get_appointment(codigo_or_id)
        if a is None:
            return None
        a.status = new_status
        if notes is not None:
            a.notes = notes
        return a

    def reschedule_appointment(self, codigo_or_id, new_scheduled_for, new_scheduled_local):
        self.reschedule_calls.append((codigo_or_id, new_scheduled_for, new_scheduled_local))
        if self.slot_taken:
            # What `uniq_active_slot` raises when another ACTIVE booking holds
            # the hour. DuplicateKeyError needs the 11000 code to be built.
            raise DuplicateKeyError("E11000 duplicate key error: uniq_active_slot")
        a = self.get_appointment(codigo_or_id)
        if a is None or a.status not in ("programada", "confirmada"):
            # The real query filters on status, so a terminal booking simply
            # does not match and findAndModify returns nothing.
            return None
        a.scheduled_for = new_scheduled_for
        a.scheduled_local = new_scheduled_local
        return a

    def query_inspections(
        self, *, date_from=None, date_to=None, brand=None, rechazo_rtm_probable=None, limit=100
    ):
        out = []
        for i in self.inspections.values():
            if date_from and i.created_at < date_from:
                continue
            if date_to and i.created_at > date_to:
                continue
            if brand and (i.vehicle_info.get("brand", "").lower() != brand.lower()):
                continue
            if (
                rechazo_rtm_probable is not None
                and i.rechazo_rtm_probable != rechazo_rtm_probable
            ):
                continue
            out.append(i)
        return out[:limit]

    def count_inspections(self, **kwargs):
        kwargs.pop("limit", None)
        return len(self.query_inspections(**kwargs))

    def get_inspection(self, inspection_id):
        return self.inspections.get(inspection_id)


@pytest.fixture
def admin_store(monkeypatch):
    users = FakeUsers(
        [
            UserDocument(
                username="beauman",
                password_hash=security.hash_password(PASSWORD),
                role=UserRole.ADMIN,
            ),
            UserDocument(
                username="secretaria",
                password_hash=security.hash_password(PASSWORD),
                role=UserRole.STAFF,
            ),
        ]
    )
    store = FakeAdminStore()

    monkeypatch.setattr("app.db.mongo.is_configured", lambda *a, **k: True)
    for fn in ("get_user", "touch_last_login", "update_password_hash"):
        monkeypatch.setattr(f"app.db.repository.{fn}", getattr(users, fn))
    for fn in (
        "query_appointments",
        "count_appointments",
        "get_appointment",
        "set_appointment_status",
        "reschedule_appointment",
        "query_inspections",
        "count_inspections",
        "get_inspection",
    ):
        monkeypatch.setattr(f"app.db.repository.{fn}", getattr(store, fn))
    return store


def _headers(client, username):
    r = client.post(
        "/api/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['accessToken']}"}


#  role reach -- the owner's decisions

def test_staff_can_read_appointments_with_contact_details(client, admin_store):
    """Owner's decision: the secretary phones customers, so email and phone
    are required on the dashboard for `staff` too."""
    r = client.get("/api/admin/appointments", headers=_headers(client, "secretaria"))
    assert r.status_code == 200

    row = r.json()["appointments"][0]
    assert row["customerPhone"] == "3001234567"
    assert row["customerEmail"] == "ana@example.co"
    assert row["codigo"] == "ABC123"


def test_staff_can_cancel_a_booking(client, admin_store):
    """Also the owner's decision: cancelling is day-to-day secretary work."""
    r = client.patch(
        "/api/admin/appointments/ABC123",
        headers=_headers(client, "secretaria"),
        json={"status": "cancelada"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "cancelada"


def test_staff_still_cannot_touch_the_users_collection(client, admin_store):
    """The line the owner drew: staff runs the diary, not the accounts."""
    headers = _headers(client, "secretaria")
    assert client.get("/api/admin/users", headers=headers).status_code == 403
    assert (
        client.post(
            "/api/admin/users",
            headers=headers,
            json={"username": "colado", "password": "una-clave-larga-1"},
        ).status_code
        == 403
    )


def test_admin_passes_the_staff_guard_too(client, admin_store):
    r = client.get("/api/admin/appointments", headers=_headers(client, "beauman"))
    assert r.status_code == 200


def test_dashboard_needs_a_token(client, admin_store):
    assert client.get("/api/admin/appointments").status_code == 401
    assert client.get("/api/admin/inspections").status_code == 401


#  status transitions

@pytest.mark.parametrize(
    "start,target,ok",
    [
        ("programada", "confirmada", True),
        ("programada", "cancelada", True),
        ("confirmada", "atendida", True),
        ("confirmada", "cancelada", True),
        # A booking must be confirmed before it can be served.
        ("programada", "atendida", False),
        # Terminal: a served or cancelled booking must not reopen, or the
        # history stops meaning anything.
        ("atendida", "programada", False),
        ("atendida", "cancelada", False),
        ("cancelada", "confirmada", False),
    ],
)
def test_status_transition_table(client, admin_store, start, target, ok):
    admin_store.appointments["ABC123"].status = start
    r = client.patch(
        "/api/admin/appointments/ABC123",
        headers=_headers(client, "secretaria"),
        json={"status": target},
    )
    if ok:
        assert r.status_code == 200
        assert r.json()["status"] == target
    else:
        assert r.status_code == 409
        assert r.json()["code"] == "transicion_invalida"


def test_setting_the_same_status_is_not_a_transition(client, admin_store):
    """Re-confirming an already-confirmed booking is a no-op, not a 409 --
    a dashboard that double-submits must not show an error."""
    admin_store.appointments["ABC123"].status = "atendida"
    r = client.patch(
        "/api/admin/appointments/ABC123",
        headers=_headers(client, "secretaria"),
        json={"status": "atendida"},
    )
    assert r.status_code == 200


def test_patching_an_unknown_code_is_404(client, admin_store):
    r = client.patch(
        "/api/admin/appointments/ZZZZZZ",
        headers=_headers(client, "secretaria"),
        json={"status": "cancelada"},
    )
    assert r.status_code == 404


#  the timezone window

def test_a_bare_date_covers_the_whole_workshop_day(client, admin_store):
    """The booking is 15:00 UTC = 10:00 in Bogota on the 12th. Filtering for
    the 12th must find it: a naive date means the WORKSHOP's day, and UTC-5
    puts five hours of every evening on the wrong date otherwise."""
    r = client.get(
        "/api/admin/appointments?date_from=2026-09-12&date_to=2026-09-12",
        headers=_headers(client, "secretaria"),
    )
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_the_previous_day_does_not_match(client, admin_store):
    r = client.get(
        "/api/admin/appointments?date_from=2026-09-11&date_to=2026-09-11",
        headers=_headers(client, "secretaria"),
    )
    assert r.json()["total"] == 0


def test_a_late_evening_local_slot_stays_on_its_local_day(client, admin_store):
    """23:00 in Bogota on the 12th is 04:00 UTC on the 13th. Filtering the
    workshop's 12th must still find it -- this is the case a naive UTC window
    gets wrong."""
    admin_store.appointments["ABC123"].scheduled_for = datetime(
        2026, 9, 12, 23, 0, tzinfo=BOGOTA
    ).astimezone(timezone.utc)

    r = client.get(
        "/api/admin/appointments?date_from=2026-09-12&date_to=2026-09-12",
        headers=_headers(client, "secretaria"),
    )
    assert r.json()["total"] == 1


def test_an_explicit_time_is_respected(client, admin_store):
    r = client.get(
        "/api/admin/appointments?date_from=2026-09-12T11:00:00",
        headers=_headers(client, "secretaria"),
    )
    # 10:00 local is before an 11:00 local floor.
    assert r.json()["total"] == 0


#  inspections

def test_inspection_list_is_a_summary_not_the_whole_report(client, admin_store):
    """Rows are kilobytes cheaper without pricing/compliance; the full record
    is one GET away."""
    r = client.get("/api/admin/inspections", headers=_headers(client, "secretaria"))
    assert r.status_code == 200

    row = r.json()["inspections"][0]
    assert row["totalCop"] == 1_250_000
    assert row["defectCount"] == 1
    assert row["brand"] == "Renault"
    assert "pricing" not in row and "compliance" not in row


def test_inspection_filters_by_brand_case_insensitively(client, admin_store):
    headers = _headers(client, "secretaria")
    assert client.get("/api/admin/inspections?brand=renault", headers=headers).json()[
        "total"
    ] == 1
    assert client.get("/api/admin/inspections?brand=Kia", headers=headers).json()[
        "total"
    ] == 0


def test_inspection_filters_by_rtm_verdict(client, admin_store):
    headers = _headers(client, "secretaria")
    admin_store.inspections["insp-2"] = _inspection("insp-2", rtm=True)

    r = client.get("/api/admin/inspections?rechazo_rtm_probable=true", headers=headers)
    assert r.json()["total"] == 1
    assert r.json()["inspections"][0]["inspectionId"] == "insp-2"


def test_inspection_detail_keeps_report_internals_snake_case(client, admin_store):
    """Same camel/snake exception as the customer-facing /results: model
    fields are renamed, bare dict contents are not."""
    admin_store.inspections["insp-1"].pricing = {"total_cop": 1_250_000, "items": []}
    r = client.get(
        "/api/admin/inspections/insp-1", headers=_headers(client, "secretaria")
    )
    assert r.status_code == 200
    body = r.json()

    assert body["inspectionId"] == "insp-1"  # model field -> camelCase
    assert body["pricing"]["total_cop"] == 1_250_000  # dict content -> untouched


def test_unknown_inspection_is_404(client, admin_store):
    r = client.get(
        "/api/admin/inspections/nope", headers=_headers(client, "secretaria")
    )
    assert r.status_code == 404
    assert r.json()["code"] == "inspeccion_no_encontrada"


def test_dashboard_without_mongo_is_503_not_a_500(client, admin_store, monkeypatch):
    """Auth fails closed, so the token has to be minted while Mongo is still
    'configured' -- then the collection goes away under it."""
    headers = _headers(client, "secretaria")
    monkeypatch.setattr("app.db.mongo.is_configured", lambda *a, **k: False)

    r = client.get("/api/admin/appointments", headers=headers)
    assert r.status_code == 503
    # The guard itself notices first: no users collection, no authentication.
    assert r.json()["code"] in {
        "autenticacion_no_disponible",
        "appointment_unavailable",
    }


def test_stored_datetimes_come_back_utc_aware(client, admin_store):
    """pymongo returns naive datetimes (BSON stores UTC but drops tzinfo). If
    they reach the wire without a `Z`, `new Date(...)` reads them as LOCAL
    time -- five hours wrong in America/Bogota. The models re-attach UTC."""
    from datetime import datetime as dt

    naive = dt(2026, 9, 12, 15, 0)  # what Mongo hands back
    admin_store.appointments["ABC123"].scheduled_for = naive
    admin_store.appointments["ABC123"] = AppointmentDocument.from_doc(
        {**admin_store.appointments["ABC123"].to_doc(), "scheduled_for": naive}
    )

    r = client.get("/api/admin/appointments", headers=_headers(client, "secretaria"))
    scheduled = r.json()["appointments"][0]["scheduledFor"]
    assert scheduled.endswith("Z") or "+00:00" in scheduled, scheduled


#  rescheduling from the calendar

def _next_working_slot(days_ahead=3, hour=10):
    """A slot parse_slot will accept: a future weekday inside workshop hours.

    Computed rather than hardcoded -- parse_slot compares against
    datetime.now(), so a fixed date silently starts failing once it is in the
    past, and the failure would look like a router bug.
    """
    when = datetime.now(BOGOTA) + timedelta(days=days_ahead)
    while when.weekday() not in get_settings().workshop_days:
        when += timedelta(days=1)
    return when.strftime("%Y-%m-%d"), f"{hour:02d}:00"


def test_staff_can_move_a_booking_to_another_slot(client, admin_store):
    """The happy path, and that the router resolves the code to the document's
    own `_id` before writing -- the repository matches on either, so passing
    the code through would still work today and quietly break if that `$or`
    were ever narrowed."""
    fecha, hora = _next_working_slot()
    r = client.patch(
        "/api/admin/appointments/ABC123/schedule",
        json={"fecha": fecha, "hora": hora},
        headers=_headers(client, "secretaria"),
    )
    assert r.status_code == 200, r.text
    assert fecha in r.json()["scheduledLocal"]

    key, _, local = admin_store.reschedule_calls[-1]
    assert key == admin_store.appointments["ABC123"].id
    assert fecha in local


def test_an_occupied_slot_is_409_not_a_503_outage(client, admin_store):
    """`uniq_active_slot` raises DuplicateKeyError, which subclasses
    PyMongoError. Routed through the module's `_call` helper it would surface
    as a 503 and tell the secretary the database is down when the hour is
    simply taken."""
    admin_store.slot_taken = True
    fecha, hora = _next_working_slot()
    r = client.patch(
        "/api/admin/appointments/ABC123/schedule",
        json={"fecha": fecha, "hora": hora},
        headers=_headers(client, "secretaria"),
    )
    assert r.status_code == 409
    assert r.json()["code"] == "horario_ocupado"


def test_a_terminal_booking_cannot_be_rescheduled(client, admin_store):
    """Same rule as the status table: `cancelada` and `atendida` are final.
    The repository returns None for both "no such booking" and "not active",
    so the router must read first and not report this as a 404."""
    admin_store.appointments["ABC123"].status = "cancelada"
    fecha, hora = _next_working_slot()
    r = client.patch(
        "/api/admin/appointments/ABC123/schedule",
        json={"fecha": fecha, "hora": hora},
        headers=_headers(client, "secretaria"),
    )
    assert r.status_code == 409
    assert r.json()["code"] == "transicion_invalida"


@pytest.mark.parametrize(
    "fecha, hora",
    [
        ("2020-01-06", "10:00"),   # a Monday, but in the past
        ("2026-09-13", "10:00"),   # a Sunday
        ("nope", "10:00"),         # unparseable
    ],
)
def test_parse_slot_rules_apply_to_the_calendar_too(client, admin_store, fecha, hora):
    """The same workshop-hours / future-date rules the agent tool enforces --
    one `parse_slot` for both callers. Nothing reaches the repository."""
    r = client.patch(
        "/api/admin/appointments/ABC123/schedule",
        json={"fecha": fecha, "hora": hora},
        headers=_headers(client, "secretaria"),
    )
    assert r.status_code == 400
    assert r.json()["code"] == "horario_invalido"
    assert admin_store.reschedule_calls == []


def test_rescheduling_needs_a_token(client, admin_store):
    """The reason this route moved out of the public appointments router: it
    was reachable there with no credentials at all."""
    fecha, hora = _next_working_slot()
    r = client.patch(
        "/api/admin/appointments/ABC123/schedule", json={"fecha": fecha, "hora": hora}
    )
    assert r.status_code == 401
    assert admin_store.reschedule_calls == []
