"""Core: session lifecycle, exceptions, log redaction, wire casing."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import pytest

from app.core.exceptions import (
    AgentLoopLimitError,
    AppError,
    SessionNotFoundError,
    SessionStateError,
)
from app.core.logging import RedactingFilter
from app.core.session import STEP_DEFINITIONS
from app.schemas.common import ApiRequest, ApiResponse, to_camel


def test_create_and_get_round_trip(store):
    session = store.create({"brand": "Kia"})
    assert store.get(session.id) is session
    assert session.vehicle_info["brand"] == "Kia"
    with pytest.raises(SessionNotFoundError):
        store.get("no-such-session")


def test_expired_sessions_are_purged_with_their_uploads(store):
    session = store.create()
    upload_dir = session.upload_dir
    assert upload_dir.is_dir()

    session.updated_at -= timedelta(minutes=store.ttl_minutes + 1)
    assert session.is_expired(store.ttl_minutes) is True
    assert store.purge_expired() == 1
    assert len(store) == 0
    assert not upload_dir.exists()


def test_tyre_uploads_flag_the_tyre_flow(store, tmp_path):
    session = store.create()
    store.add_file(
        session.id, name="t.jpg", size=10, content_type="image/jpeg",
        model="tires_wheels", path=tmp_path / "t.jpg",
    )
    assert session.tires_inspection_requested is True
    assert len(session.files_for("tires_wheels")) == 1
    assert session.files_for("surface_defects") == []
    assert session.status == "uploading"


def test_prepare_steps_matches_the_step_ids_the_spa_expects(store, tmp_path):
    session = store.create()
    with pytest.raises(SessionStateError):
        store.prepare_steps(session.id)

    store.add_file(
        session.id, name="s.jpg", size=10, content_type="image/jpeg",
        model="surface_defects", path=tmp_path / "s.jpg",
    )
    prepared = store.prepare_steps(session.id)
    ids = [s.id for s in prepared.steps]
    assert ids == [i for i, _ in STEP_DEFINITIONS if i != "vision_tires"]

    store.set_step(session.id, "upload", "done")
    assert prepared.steps[0].status == "done"
    assert prepared.steps[0].completed_at is not None


def test_app_errors_carry_a_customer_payload_and_a_private_log():
    error = AppError(detail="Algo fallo.", log_message="stack detail")
    assert error.to_payload() == {"detail": "Algo fallo.", "code": "error_interno"}

    limit = AgentLoopLimitError()
    assert limit.code == "limite_iteraciones_agente"
    assert limit.status_code == 502
    assert "stack detail" not in limit.detail


def test_redacting_filter_scrubs_secrets_from_message_and_args():
    secret = "sk-ant-super-secret-value"
    log_filter = RedactingFilter([secret, "short"])
    record = logging.LogRecord(
        "t", logging.INFO, "f", 1,
        f"key={secret}", (f"https://x.cloud?api={secret}",), None,
    )
    log_filter.filter(record)
    assert secret not in record.msg
    assert secret not in record.args[0]
    assert "***REDACTED***" in record.msg


def test_mongo_uri_and_its_password_are_both_redacted(settings, monkeypatch):
    from pydantic import SecretStr

    from app.core.logging import _secret_values

    uri = "mongodb+srv://dbuser:Sup3rS3cretPw@cluster0.example.net/?w=majority"
    monkeypatch.setattr(settings, "mongodb_uri", SecretStr(uri))
    secrets = _secret_values(settings)
    assert uri in secrets
    ## pymongo errors quote fragments, not the whole URI: the password alone
    ## must be scrubbed too.
    assert "Sup3rS3cretPw" in secrets

    log_filter = RedactingFilter(secrets)
    record = logging.LogRecord(
        "t", logging.ERROR, "f", 1, "auth failed for Sup3rS3cretPw", (), None
    )
    log_filter.filter(record)
    assert "Sup3rS3cretPw" not in record.msg


def test_requests_are_snake_case_and_responses_camel_case():
    class Req(ApiRequest):
        session_id: str

    class Res(ApiResponse):
        session_id: str
        report: dict[str, Any]

    assert to_camel("overall_status") == "overallStatus"
    assert Req(session_id="s1").session_id == "s1"

    dumped = Res(
        session_id="s1", report={"pricing": {"total_cop": 100}}
    ).model_dump(by_alias=True)
    assert "sessionId" in dumped
    ## Dict contents are not renamed, the documented exception.
    assert dumped["report"]["pricing"]["total_cop"] == 100
