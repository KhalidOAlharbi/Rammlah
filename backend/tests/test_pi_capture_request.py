from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.inspection import router
from app.state import StateService


def make_client(tmp_path) -> TestClient:
    app = FastAPI()
    app.state.settings = SimpleNamespace(raspberry_pi_agent_token_value="secret-token")
    app.state.state_service = StateService(
        tmp_path,
        robot_enabled=False,
        camera_enabled=False,
        openai_configured=True,
    )
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_dashboard_capture_request_can_be_claimed_and_completed(tmp_path):
    client = make_client(tmp_path)

    requested = client.post("/api/pi-capture/request")

    assert requested.status_code == 200
    request_body = requested.json()
    assert request_body["state"] == "pending"
    assert request_body["countdown_seconds"] == 10
    assert request_body["request_id"]
    assert request_body["capture_at"]

    blocked = client.get("/api/pi-agent/capture-request")

    assert blocked.status_code == 401

    claimed = client.get(
        "/api/pi-agent/capture-request",
        headers={"X-Rammlah-Agent-Token": "secret-token"},
    )

    assert claimed.status_code == 200
    assert claimed.json()["state"] == "capturing"
    assert claimed.json()["request_id"] == request_body["request_id"]

    second_claim = client.get(
        "/api/pi-agent/capture-request",
        headers={"X-Rammlah-Agent-Token": "secret-token"},
    )

    assert second_claim.status_code == 204

    completed = client.post(
        f"/api/pi-agent/capture-request/{request_body['request_id']}/complete",
        headers={"X-Rammlah-Agent-Token": "secret-token"},
        json={
            "success": True,
            "image_url": "/images/captures/pi_capture_test.jpg",
            "prediction": "Clean",
        },
    )

    assert completed.status_code == 200
    assert completed.json()["state"] == "completed"
    assert completed.json()["image_url"] == "/images/captures/pi_capture_test.jpg"
    assert completed.json()["prediction"] == "Clean"


def test_dashboard_reuses_active_capture_request(tmp_path):
    client = make_client(tmp_path)

    first = client.post("/api/pi-capture/request").json()
    second = client.post("/api/pi-capture/request").json()

    assert second["state"] == "pending"
    assert second["request_id"] == first["request_id"]
