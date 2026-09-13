"""make_appointment + the two collection models. Offline: the repository and
API Ninjas are monkeypatched; Mongo is "configured" with a fake URI only so
the tool proceeds past its gate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from pydantic import SecretStr
from pymongo.errors import ServerSelectionTimeoutError

from app.agent import make_appointment as ma
from app.agent.tools_iml import execute_tool
from app.core.exceptions import AppointmentUnavailableError
from app.core.session import InspectionSession
from app.models.appointment import AppointmentDocument, code_of
from app.models.inspection import InspectionDocument

BOGOTA = ZoneInfo("America/Bogota")


def _next_weekday_slot(hour: int = 10) -> tuple[str, str]:
    """A future Monday..Saturday at `hour`, workshop-local."""
    d = datetime.now(BOGOTA) + timedelta(days=2)
    while d.weekday() == 6:
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d"), f"{hour:02d}:00"


def _next_sunday() -> str:
    d = datetime.now(BOGOTA) + timedelta(days=1)
    while d.weekday() != 6:
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d")


GOOD_INPUT = {
    "confirmado": True,
    "nombre_cliente": "Ana Perez",
    "telefono": "+57 300 123 4567",
    "email": "ana@example.com",
    "placa": "abc-123",
}
CTX = {
    "brand": "Renault", "model": "Logan", "year": 2018,
    "inspection_id": "sess-abc", "total_cop": 577500, "rechazo_rtm_probable": False,
}


@pytest.fixture
def fake_store(settings, monkeypatch):
    """In-memory stand-in for the repository, with the slot idempotency key."""
    monkeypatch.setattr(settings, "mongodb_uri", SecretStr("mongodb://u:p@x.invalid/"))
    rows: list[AppointmentDocument] = []

    def find_slot(inspection_id, when):
        return next(
            (r for r in rows
             if r.inspection_id == inspection_id and r.scheduled_for == when),
            None,
        )

    monkeypatch.setattr(ma.repository, "get_inspection", lambda _id: None)
    monkeypatch.setattr(ma.repository, "get_discount_for_inspection", lambda _id: None)
    monkeypatch.setattr(ma.repository, "find_appointment_for_slot", find_slot)
    monkeypatch.setattr(ma.repository, "create_appointment", lambda d: (rows.append(d), d)[1])
    monkeypatch.setattr(ma, "get_car_specs", lambda *a, **k: [{"cilindros": 4}])
    return rows


#  session -> inspection document

def _completed_session() -> InspectionSession:
    s = InspectionSession(id="sess-abc", status="complete")
    s.vehicle_info = {"brand": "Renault", "model": "Logan", "year": 2018}
    s.agent_payload = {
        "defects": [{"pieza": "hood", "tipo_defecto": "dent", "severidad": "moderado",
                     "confidence": 0.81, "severity_basis": "area_ratio:0.18"}],
        "defectos_sin_ubicar": 0,
    }
    s.report = {
        "resumen": "texto",
        "pricing": {"items": [{"pieza": "hood", "tipo_defecto": "dent",
                               "precio_exacto": True, "fallback_level": "exact",
                               "entry": {"total_cost_cop": 539000}}],
                    "resumen": {"total_cop": 539000, "items_sin_precio": []}},
        "compliance": {"resultados": [{"pieza": "hood", "tipo_defecto": "dent",
                                        "causal_rechazo": False, "clase_rechazo": None}],
                       "rechazo_rtm_probable": False},
        "tools_used": ["query_pricing_batch", "query_compliance"],
    }
    return s


def test_inspection_document_joins_vision_pricing_and_compliance():
    doc = InspectionDocument.from_session(_completed_session(), catalog_source="mongo")
    assert doc.id == "sess-abc"
    assert doc.total_cop == 539000 and doc.rechazo_rtm_probable is False
    d = doc.defects[0]
    assert (d.total_cost_cop, d.precio_exacto, d.causal_rechazo) == (539000, True, False)
    assert d.severity_basis == "area_ratio:0.18"
    ## The wire doc uses `_id`, and the snapshot is the compact copy.
    assert doc.to_doc()["_id"] == "sess-abc"
    assert doc.snapshot()["defects"][0]["pieza"] == "hood"


def test_agent_context_carries_server_side_facts_only():
    ctx = _completed_session().agent_context()
    assert ctx["inspection_id"] == "sess-abc"
    assert ctx["total_cop"] == 539000
    assert ctx["brand"] == "Renault"


#  codes

def test_code_is_six_upper_hex_from_a_random_id():
    a, b = AppointmentDocument.model_construct(), None
    doc = AppointmentDocument(
        inspection_id="x", customer={"name": "a", "phone": "1234567", "email": "a@b.co"},
        car_info={}, scheduled_for=datetime.now(timezone.utc), scheduled_local="", timezone="UTC",
    )
    assert len(doc.codigo) == 6 and doc.codigo == doc.id[:6].upper()
    assert code_of("abcdef0123", 6) == "ABCDEF"


#  validation, all before any store access

@pytest.mark.parametrize("bad, campo", [
    ({"confirmado": False}, "confirmado"),
    ({"nombre_cliente": ""}, "nombre_cliente"),
    ({"telefono": "12"}, "telefono"),
    ({"email": "not-an-email"}, "email"),
    ({"placa": ""}, "placa"),
    ({"placa": "AB1234"}, "placa"),
    ({"placa": "ABC12D"}, "placa"),                                # motorcycle, not yet
    ({"placa": "ABCD123"}, "placa"),
    ({"fecha": "ayer", "hora": "10:00"}, "fecha_hora"),
    ({"fecha": "2020-01-06", "hora": "10:00"}, "fecha_hora"),      # past
    ({"fecha": _next_sunday(), "hora": "10:00"}, "fecha"),         # closed day
    ({"fecha": _next_weekday_slot()[0], "hora": "19:30"}, "hora"), # after close
])
def test_rejections_are_results_not_exceptions(fake_store, bad, campo):
    fecha, hora = _next_weekday_slot()
    tool_input = {**GOOD_INPUT, "fecha": fecha, "hora": hora, **bad}
    result = execute_tool("make_appointment", tool_input, context=CTX)
    assert result["cita_creada"] is False
    assert result["campo"] == campo
    assert "codigo" not in result
    assert fake_store == []


def test_no_inspection_in_context_cannot_book(fake_store):
    fecha, hora = _next_weekday_slot()
    r = execute_tool("make_appointment", {**GOOD_INPUT, "fecha": fecha, "hora": hora}, context={})
    assert r["cita_creada"] is False and r["campo"] == "inspection_id"


#  booking

def test_booking_uses_context_facts_and_returns_the_code(fake_store):
    fecha, hora = _next_weekday_slot(14)
    r = execute_tool(
        "make_appointment",
        {**GOOD_INPUT, "fecha": fecha, "hora": hora, "notas": "llegar temprano",
         ## Must be ignored: the model never supplies these.
         "inspection_id": "WRONG", "costo": 1},
        context=CTX,
    )
    assert r["cita_creada"] is True
    assert len(r["codigo"]) == 6
    assert r["inspection_id"] == "sess-abc"
    assert r["costo_estimado_cop"] == 577500
    assert r["vehiculo"]["brand"] == "Renault"
    doc = fake_store[0]
    assert doc.car_info.specs == {"cilindros": 4}
    assert doc.car_info.license_plate == "ABC123"     # normalised, uppercase
    assert r["vehiculo"]["license_plate"] == "ABC123"
    assert doc.scheduled_for.tzinfo is not None
    assert doc.scheduled_for.astimezone(BOGOTA).hour == 14
    assert doc.notes == "llegar temprano"


def test_same_slot_twice_returns_the_existing_booking(fake_store):
    fecha, hora = _next_weekday_slot(9)
    first = execute_tool("make_appointment", {**GOOD_INPUT, "fecha": fecha, "hora": hora}, context=CTX)
    second = execute_tool("make_appointment", {**GOOD_INPUT, "fecha": fecha, "hora": hora}, context=CTX)
    assert second["ya_existia"] is True
    assert second["codigo"] == first["codigo"]
    assert len(fake_store) == 1


def test_unreachable_store_degrades_as_a_recoverable_tool_error(fake_store, monkeypatch):
    def down(*a, **k):
        raise ServerSelectionTimeoutError("no primary")

    monkeypatch.setattr(ma.repository, "get_inspection", down)
    fecha, hora = _next_weekday_slot()
    with pytest.raises(AppointmentUnavailableError):
        execute_tool("make_appointment", {**GOOD_INPUT, "fecha": fecha, "hora": hora}, context=CTX)


def test_specs_failure_does_not_block_the_booking(fake_store, monkeypatch):
    from app.core.exceptions import CarSpecsUnavailableError

    def no_specs(*a, **k):
        raise CarSpecsUnavailableError(log_message="quota")

    monkeypatch.setattr(ma, "get_car_specs", no_specs)
    fecha, hora = _next_weekday_slot(11)
    r = execute_tool("make_appointment", {**GOOD_INPUT, "fecha": fecha, "hora": hora}, context=CTX)
    assert r["cita_creada"] is True
    assert fake_store[0].car_info.specs is None
