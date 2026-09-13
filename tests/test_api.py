"""HTTP layer. Vision and the agent are stubbed, so nothing leaves the box."""

from __future__ import annotations

from app.core.session import session_store
from app.routers import inspection as inspection_router


def start_session(client) -> str:
    response = client.post("/api/inspections/start", json={})
    assert response.status_code == 201
    return response.json()["sessionId"]


def test_health_is_up_and_readiness_loads_no_model(client, monkeypatch):
    from app.vision import onnx_infer

    def fail(*args, **kwargs):
        raise AssertionError("readiness must not load a model")

    monkeypatch.setattr(onnx_infer.OnnxModel, "__init__", fail)

    assert client.get("/health").status_code == 200
    ready = client.get("/health/ready")
    assert ready.status_code in (200, 503)
    assert ready.json()["checks"]["vision"]["loaded_count"] == 0


def test_start_returns_a_camel_case_session_id(client):
    session_id = start_session(client)
    assert session_store.get(session_id).id == session_id


def test_upload_enforces_the_cap_and_the_format(client, jpeg_bytes):
    session_id = start_session(client)

    ok = client.post(
        "/api/inspections/upload",
        data={"session_id": session_id, "model": "tires_wheels", "brand": "Kia"},
        files=[("files", ("t.jpg", jpeg_bytes, "image/jpeg"))],
    )
    assert ok.status_code == 200
    assert ok.json()["uploadedCount"] == 1
    assert session_store.get(session_id).vehicle_info["brand"] == "Kia"

    over_cap = client.post(
        "/api/inspections/upload",
        data={"session_id": session_id, "model": "tires_wheels"},
        files=[("files", ("t2.jpg", jpeg_bytes, "image/jpeg"))],
    )
    assert over_cap.status_code == 400
    assert over_cap.json()["code"]

    bad_type = client.post(
        "/api/inspections/upload",
        data={"session_id": session_id, "model": "surface_defects"},
        files=[("files", ("clip.mp4", b"0000", "video/mp4"))],
    )
    assert bad_type.status_code == 400


def test_run_returns_immediately_and_status_reports_the_steps(
    client, jpeg_bytes, monkeypatch
):
    monkeypatch.setattr(
        inspection_router, "_execute_pipeline", lambda session_id: None
    )
    session_id = start_session(client)
    client.post(
        "/api/inspections/upload",
        data={"session_id": session_id, "model": "surface_defects"},
        files=[("files", ("s.jpg", jpeg_bytes, "image/jpeg"))],
    )

    run = client.post("/api/inspections/run", json={"session_id": session_id})
    assert run.status_code == 200

    status = client.get(f"/api/inspections/{session_id}/status").json()
    step_ids = [s["id"] for s in status["steps"]]
    assert status["overallStatus"] == "processing"
    assert "vision_tires" not in step_ids
    assert step_ids[0] == "upload"


def test_results_keep_report_contents_snake_case(client):
    session_id = start_session(client)
    session = session_store.get(session_id)
    session.report = {
        "resumen": "texto",
        "pricing": {"resumen": {"total_cop": 577_500}},
        "compliance": {"rechazo_rtm_probable": False},
        "tools_used": ["query_pricing_batch"],
    }

    body = client.get(f"/api/inspections/{session_id}/results").json()
    assert body["report"]["pricing"]["resumen"]["total_cop"] == 577_500
    assert client.get("/api/inspections/unknown-id/results").status_code == 404


def test_image_id_is_validated_and_delete_drops_the_session(client):
    session_id = start_session(client)
    session = session_store.get(session_id)
    session.vision_result = {"images_analyzed": []}

    traversal = client.get(
        f"/api/inspections/{session_id}/images/..%2F..%2Fetc%2Fpasswd"
    )
    assert traversal.status_code in (404, 409)

    assert client.delete(f"/api/inspections/{session_id}").status_code == 204
    assert client.get(f"/api/inspections/{session_id}/status").status_code == 404
