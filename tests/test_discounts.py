"""check_availability + the new-user discount pair, and the two index rules
they depend on. Offline: the repository is monkeypatched and Mongo is
"configured" with a fake URI only so the tools proceed past their gate."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import SecretStr
from pymongo.errors import DuplicateKeyError

from app.agent import check_availability as ca
from app.agent import discount as dsc
from app.agent import make_appointment as ma
from app.agent.tools_iml import execute_tool
from app.db import repository

BOGOTA = ZoneInfo("America/Bogota")

CTX = {"inspection_id": "sess-abc", "total_cop": 577500}


def _next_weekday_slot(hour: int = 10) -> tuple[str, str]:
    d = datetime.now(BOGOTA) + timedelta(days=2)
    while d.weekday() == 6:
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d"), f"{hour:02d}:00"


@pytest.fixture
def configured(settings, monkeypatch):
    monkeypatch.setattr(settings, "mongodb_uri", SecretStr("mongodb://u:p@x.invalid/"))


#  check_availability

def test_free_slot_is_reported_available(configured, monkeypatch):
    monkeypatch.setattr(ca.repository, "slot_is_available", lambda when: True)
    fecha, hora = _next_weekday_slot()
    r = execute_tool("check_availability", {"fecha": fecha, "hora": hora}, context=CTX)
    assert r["disponible"] is True


def test_taken_slot_is_reported_unavailable(configured, monkeypatch):
    monkeypatch.setattr(ca.repository, "slot_is_available", lambda when: False)
    fecha, hora = _next_weekday_slot()
    r = execute_tool("check_availability", {"fecha": fecha, "hora": hora}, context=CTX)
    assert r["disponible"] is False


def test_a_closed_day_is_rejected_before_the_store_is_touched(configured, monkeypatch):
    def boom(*a, **k):  # pragma: no cover - must not run
        pytest.fail("slot_is_available called for an invalid slot")

    monkeypatch.setattr(ca.repository, "slot_is_available", boom)
    d = datetime.now(BOGOTA) + timedelta(days=1)
    while d.weekday() != 6:
        d += timedelta(days=1)
    r = execute_tool(
        "check_availability", {"fecha": d.strftime("%Y-%m-%d"), "hora": "10:00"}, context=CTX
    )
    assert r["cita_creada"] is False and r["campo"] == "fecha"


#  the two unique indexes are different failures

@pytest.mark.parametrize(
    "index_name, expect_rejection",
    [
        # A different inspection holds the slot: the customer needs another hour.
        ("uniq_active_slot", True),
        # This inspection retrying its own slot: hand back the same booking.
        ("uniq_inspection_slot", False),
    ],
)
def test_duplicate_key_tells_the_two_indexes_apart(
    configured, monkeypatch, index_name, expect_rejection
):
    """Regression: the handler read `exc` without binding it, so every
    DuplicateKeyError raised NameError instead of either branch."""
    monkeypatch.setattr(ma.repository, "get_inspection", lambda _id: None)
    monkeypatch.setattr(ma.repository, "get_discount_for_inspection", lambda _id: None)
    monkeypatch.setattr(ma, "get_car_specs", lambda *a, **k: [])
    monkeypatch.setattr(
        ma.repository, "create_appointment",
        lambda d: (_ for _ in ()).throw(DuplicateKeyError(f"E11000 ... {index_name} dup key")),
    )
    monkeypatch.setattr(
        ma.repository, "find_appointment_for_slot",
        lambda *a: None if expect_rejection else _stub_booking(),
    )
    fecha, hora = _next_weekday_slot(11)
    r = execute_tool(
        "make_appointment",
        {"confirmado": True, "nombre_cliente": "Ana Perez", "telefono": "+57 300 123 4567",
         "email": "ana@example.com", "placa": "ABC123", "fecha": fecha, "hora": hora},
        context=CTX,
    )
    if expect_rejection:
        assert r["slot_ocupado"] is True and r["campo"] == "fecha_hora"
    else:
        assert r["ya_existia"] is True and r["cita_creada"] is False


def _stub_booking():
    from app.models.appointment import AppointmentDocument, CarInfo, Customer

    return AppointmentDocument(
        inspection_id="sess-abc",
        customer=Customer(name="Ana Perez", phone="+57 300", email="ana@example.com"),
        car_info=CarInfo(license_plate="ABC123"),
        scheduled_for=datetime.now(BOGOTA),
        scheduled_local="lunes 10:00",
        timezone="America/Bogota",
    )


def test_active_slot_index_exists_so_two_cars_cannot_share_an_hour(monkeypatch):
    """check_availability is look-then-leap; the unique index is the guard."""
    created: list[dict] = []

    class FakeCollection:
        def create_index(self, keys, **kw):
            created.append(kw)

    monkeypatch.setattr(repository, "_appointments", lambda: FakeCollection())
    monkeypatch.setattr(repository, "_inspections", lambda: FakeCollection())
    repository.ensure_indexes()

    active = next(i for i in created if i.get("name") == "uniq_active_slot")
    assert active["unique"] is True
    assert active["partialFilterExpression"] == {
        "status": {"$in": ["programada", "confirmada"]}
    }


#  discount eligibility + grant

def test_a_new_customer_qualifies_and_a_returning_one_does_not(configured, monkeypatch):
    monkeypatch.setattr(dsc.repository, "find_appointment_by_email_or_plate", lambda e, p, **kw: False)
    new = execute_tool(
        "query_email_and_plate_number",
        {"email": "ana@example.com", "placa": "abc-123"}, context=CTX,
    )
    monkeypatch.setattr(dsc.repository, "find_appointment_by_email_or_plate", lambda e, p, **kw: True)
    old = execute_tool(
        "query_email_and_plate_number",
        {"email": "ana@example.com", "placa": "abc-123"}, context=CTX,
    )
    assert new["es_usuario_nuevo"] is True
    assert old["es_usuario_nuevo"] is False


def test_grant_applies_ten_percent_and_records_it(configured, monkeypatch):
    saved: list[dict] = []
    monkeypatch.setattr(dsc.repository, "find_appointment_by_email_or_plate", lambda e, p, **kw: False)
    monkeypatch.setattr(dsc.repository, "next_ticket_number", lambda **k: "TKT-000042")
    monkeypatch.setattr(dsc.repository, "record_discount", lambda doc: saved.append(doc))
    monkeypatch.setattr(dsc.repository, "apply_discount_to_appointments",
                        lambda *a, **k: [])

    r = execute_tool(
        "grant_discount", {"email": "ana@example.com", "placa": "abc-123"}, context=CTX,
    )
    assert r["descuento_aplicado"] is True
    assert r["porcentaje"] == 10
    # 577500 * 0.9, computed in Python -- the model never does the arithmetic.
    assert r["total_con_descuento_cop"] == 519750
    assert len(r["codigo_descuento"]) == 5
    assert saved[0]["license_plate"] == "ABC123"      # normalised before storing


def test_grant_rechecks_eligibility_and_refuses_a_returning_customer(configured, monkeypatch):
    """The model does not get to assert eligibility, whatever it passes in."""
    def boom(doc):  # pragma: no cover - must not run
        pytest.fail("record_discount called for a returning customer")

    monkeypatch.setattr(dsc.repository, "find_appointment_by_email_or_plate", lambda e, p, **kw: True)
    monkeypatch.setattr(dsc.repository, "next_ticket_number", lambda **k: "TKT-000042")
    monkeypatch.setattr(dsc.repository, "record_discount", boom)

    r = execute_tool(
        "grant_discount",
        {"email": "ana@example.com", "placa": "ABC123", "is_new_user_confirmed": True},
        context=CTX,
    )
    assert r["descuento_aplicado"] is False


def test_no_quote_in_the_session_means_no_discount(configured, monkeypatch):
    monkeypatch.setattr(dsc.repository, "find_appointment_by_email_or_plate", lambda e, p, **kw: False)
    monkeypatch.setattr(dsc.repository, "next_ticket_number", lambda **k: "TKT-000042")
    monkeypatch.setattr(dsc.repository, "record_discount", lambda doc: None)
    monkeypatch.setattr(dsc.repository, "apply_discount_to_appointments",
                        lambda *a, **k: [])
    r = execute_tool(
        "grant_discount", {"email": "ana@example.com", "placa": "ABC123"},
        context={"inspection_id": "sess-abc"},
    )
    assert r["descuento_aplicado"] is False


#  the discount reaches the booking, whichever order it happens in

def test_a_grant_rewrites_an_existing_booking(configured, monkeypatch):
    """Bargaining after booking: the stored cost becomes what is owed."""
    booking = _stub_booking()
    booking.estimated_repair_cost_cop = 577500
    saved: list[dict] = []
    written: list[dict] = []

    monkeypatch.setattr(dsc.repository, "find_appointment_by_email_or_plate",
                        lambda e, p, **kw: False)
    monkeypatch.setattr(dsc.repository, "next_ticket_number", lambda **k: "TKT-000042")
    monkeypatch.setattr(dsc.repository, "record_discount", lambda doc: saved.append(doc))

    def apply(inspection_id, code, percent, ticket_number=None):
        written.append({"inspection_id": inspection_id, "code": code, "percent": percent})
        booking.estimated_repair_cost_cop = round(577500 * 0.9)
        return [booking]

    monkeypatch.setattr(dsc.repository, "apply_discount_to_appointments", apply)

    r = execute_tool(
        "grant_discount", {"email": "ana@example.com", "placa": "ABC123"}, context=CTX,
    )
    assert r["descuento_aplicado"] is True
    assert written[0]["percent"] == 10
    assert booking.estimated_repair_cost_cop == 519750
    assert r["citas_actualizadas"] == [booking.codigo]


def test_a_booking_made_after_the_grant_is_discounted(configured, monkeypatch):
    """The other order: the discount is on file before the booking exists."""
    rows = []
    monkeypatch.setattr(ma.repository, "get_inspection", lambda _id: None)
    monkeypatch.setattr(ma, "get_car_specs", lambda *a, **k: [])
    monkeypatch.setattr(ma.repository, "find_appointment_for_slot", lambda *a: None)
    monkeypatch.setattr(ma.repository, "create_appointment", lambda d: (rows.append(d), d)[1])
    monkeypatch.setattr(
        ma.repository, "get_discount_for_inspection",
        lambda _id: {"discount_id": "A1B2C", "percent": 10},
    )

    fecha, hora = _next_weekday_slot(15)
    r = execute_tool(
        "make_appointment",
        {"confirmado": True, "nombre_cliente": "Ana Perez", "telefono": "+57 300 123 4567",
         "email": "ana@example.com", "placa": "ABC123", "fecha": fecha, "hora": hora},
        context=CTX,
    )
    assert r["cita_creada"] is True
    # Stored cost is what the customer owes; the original is kept beside it.
    assert rows[0].estimated_repair_cost_cop == 519750
    assert rows[0].discount.original_cost_cop == 577500
    assert r["descuento"]["codigo"] == "A1B2C"


def test_the_customers_own_booking_does_not_make_them_a_returning_customer(
    configured, monkeypatch
):
    seen: dict = {}

    def lookup(email, plate, exclude_inspection_id=None):
        seen["excluded"] = exclude_inspection_id
        return False

    monkeypatch.setattr(dsc.repository, "find_appointment_by_email_or_plate", lookup)
    execute_tool(
        "query_email_and_plate_number",
        {"email": "ana@example.com", "placa": "ABC123"}, context=CTX,
    )
    assert seen["excluded"] == "sess-abc"


#  ticket numbers

def test_a_grant_returns_a_ticket_number_and_stores_it(configured, monkeypatch):
    saved: list[dict] = []
    monkeypatch.setattr(dsc.repository, "find_appointment_by_email_or_plate",
                        lambda e, p, **kw: False)
    monkeypatch.setattr(dsc.repository, "next_ticket_number", lambda **k: "TKT-000042")
    monkeypatch.setattr(dsc.repository, "record_discount", lambda doc: saved.append(doc))
    monkeypatch.setattr(dsc.repository, "apply_discount_to_appointments",
                        lambda *a, **k: [])

    r = execute_tool(
        "grant_discount", {"email": "ana@example.com", "placa": "ABC123"}, context=CTX,
    )
    assert r["numero_ticket"] == "TKT-000042"
    assert saved[0]["ticket_number"] == "TKT-000042"


def test_the_ticket_number_reaches_the_booking(configured, monkeypatch):
    rows = []
    monkeypatch.setattr(ma.repository, "get_inspection", lambda _id: None)
    monkeypatch.setattr(ma, "get_car_specs", lambda *a, **k: [])
    monkeypatch.setattr(ma.repository, "find_appointment_for_slot", lambda *a: None)
    monkeypatch.setattr(ma.repository, "create_appointment", lambda d: (rows.append(d), d)[1])
    monkeypatch.setattr(
        ma.repository, "get_discount_for_inspection",
        lambda _id: {"discount_id": "A1B2C", "percent": 10, "ticket_number": "TKT-000042"},
    )

    fecha, hora = _next_weekday_slot(16)
    r = execute_tool(
        "make_appointment",
        {"confirmado": True, "nombre_cliente": "Ana Perez", "telefono": "+57 300 123 4567",
         "email": "ana@example.com", "placa": "ABC123", "fecha": fecha, "hora": hora},
        context=CTX,
    )
    assert rows[0].discount.ticket_number == "TKT-000042"
    assert r["descuento"]["numero_ticket"] == "TKT-000042"


def test_ticket_numbers_are_minted_by_one_atomic_increment(monkeypatch):
    """A read-then-write would hand two racing grants the same number."""
    calls: list[dict] = []

    class FakeCounters:
        def find_one_and_update(self, flt, update, **kw):
            calls.append({"filter": flt, "update": update, **kw})
            return {"_id": "ticket", "seq": 42}

    monkeypatch.setattr(repository, "_counters", lambda: FakeCounters())
    assert repository.next_ticket_number() == "TKT-000042"
    assert calls[0]["update"] == {"$inc": {"seq": 1}}
    assert calls[0]["upsert"] is True
