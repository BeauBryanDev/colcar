"""Rate limits on the public endpoints that spend Claude tokens."""

from __future__ import annotations

from app.agent import reschedule_and_cancel as rc
from app.core.rate_limit import limiter

INPUT = {"codigo_cita": "ABC123", "email": "ana@correo.co", "placa": "xyz-123"}


def test_session_start_is_refused_with_429_and_retry_after(client, settings):
    for _ in range(settings.rate_session_start_per_10min):
        assert client.post("/api/inspections/start").status_code == 201

    refused = client.post("/api/inspections/appointment-chat/start")

    # Both starters share one per-IP bucket, so switching endpoints is no bypass.
    assert refused.status_code == 429
    assert refused.json()["code"] == "demasiadas_solicitudes"
    assert int(refused.headers["Retry-After"]) > 0


def test_booking_lookup_locks_after_repeated_failures(settings, monkeypatch):
    calls = []
    monkeypatch.setattr(rc.mongo, "is_configured", lambda: True)
    monkeypatch.setattr(
        rc.repository, "verify_appointment_owner",
        lambda *a: calls.append(a),  # always a mismatch
    )
    ctx = {"session_id": "sess-1"}

    for _ in range(settings.verify_max_failures):
        assert rc._verify(INPUT, ctx)["campo"] == "verificacion"

    locked = rc._verify(INPUT, ctx)

    # Locked before the database is asked again, and still non-specific.
    assert len(calls) == settings.verify_max_failures
    assert locked["recuperable"] is False
    assert "placa" not in locked["error"] and "correo" not in locked["error"]
    # Another conversation is not affected.
    assert limiter.count("verify:sess-2", 60) == 0
