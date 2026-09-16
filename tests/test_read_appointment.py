"""read_appointment: same gate as reschedule/cancel, terminal bookings still read."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import SecretStr

from app.agent import reschedule_and_cancel as rc
from app.agent.tools_iml import execute_tool
from app.models.appointment import AppointmentDocument

pytestmark = pytest.mark.skip(reason="read_appointment tool not released yet")

INPUT = {"codigo_cita": "ABC123", "email": "ana@correo.co", "placa": "xyz-123"}


@pytest.fixture
def configured(settings, monkeypatch):
    monkeypatch.setattr(settings, "mongodb_uri", SecretStr("mongodb://u:p@x.invalid/"))


def test_cancelled_booking_reads_back_its_stored_facts(configured, monkeypatch):
    appt = AppointmentDocument(
        inspection_id="sess-1", status="cancelada",
        customer={"name": "Ana", "phone": "3001234567", "email": "ana@correo.co"},
        car_info={"license_plate": "XYZ123"},
        scheduled_for=datetime(2026, 10, 1, 15, tzinfo=timezone.utc),
        scheduled_local="2026-10-01 10:00", timezone="America/Bogota",
        estimated_repair_cost_cop=519750,
    )
    monkeypatch.setattr(rc.repository, "verify_appointment_owner", lambda *a: appt)
    r = execute_tool("read_appointment", INPUT)
    assert r["estado"] == "cancelada"
    assert r["fecha_hora_local"] == "2026-10-01 10:00"


def test_mismatch_rejects_without_naming_the_field(configured, monkeypatch):
    monkeypatch.setattr(rc.repository, "verify_appointment_owner", lambda *a: None)
    r = execute_tool("read_appointment", INPUT)
    assert r["campo"] == "verificacion" and "fecha_hora_local" not in r
