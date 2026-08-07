import tempfile
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.inspection import router
from app.schemas import ExecutionMode, ImageSource, InspectionResult
from app.state import StateService


class FakeInspectionService:
    def __init__(self):
        self.source = None

    async def analyze_and_decide(self, image_bytes: bytes, image_source: ImageSource) -> InspectionResult:
        self.source = image_source
        return InspectionResult(
            success=True,
            image_source=image_source,
            execution_mode=ExecutionMode.prototype,
            prediction="Clean",
            confidence=0.9,
            dust_coverage_percent=0,
            reason="Panel appears clean.",
        )


def make_client(token: str = "secret-token") -> tuple[TestClient, FakeInspectionService]:
    app = FastAPI()
    service = FakeInspectionService()
    data_dir = Path(tempfile.mkdtemp(prefix="rammlah-test-"))
    app.state.settings = SimpleNamespace(raspberry_pi_agent_token_value=token, camera_enabled=False)
    app.state.inspection_service = service
    app.state.state_service = StateService(
        data_dir=data_dir,
        robot_enabled=False,
        camera_enabled=False,
        openai_configured=True,
    )
    app.include_router(router, prefix="/api")
    return TestClient(app), service


def test_pi_upload_requires_agent_token(image_bytes):
    client, _ = make_client()

    response = client.post(
        "/api/predict/pi-upload",
        files={"image": ("capture.jpg", image_bytes, "image/jpeg")},
    )

    assert response.status_code == 401


def test_pi_upload_uses_raspberry_pi_camera_source(image_bytes):
    client, service = make_client()

    response = client.post(
        "/api/predict/pi-upload",
        headers={"X-Rammlah-Agent-Token": "secret-token"},
        files={"image": ("capture.jpg", image_bytes, "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json()["image_source"] == "raspberry_pi_camera"
    assert service.source == ImageSource.raspberry_pi_camera


def test_dashboard_scan_creates_pi_capture_request():
    client, _ = make_client()

    response = client.post("/api/scan")

    assert response.status_code == 200
    body = response.json()
    assert body["image_source"] == "raspberry_pi_camera"
    assert body["robot_action"] == "Waiting for Raspberry Pi Capture"

    request_response = client.get(
        "/api/pi-agent/capture-request",
        headers={"X-Rammlah-Agent-Token": "secret-token"},
    )

    assert request_response.status_code == 200
    assert request_response.json()["request_id"]


def test_dashboard_scan_requires_configured_pi_agent_token():
    client, _ = make_client(token="")

    response = client.post("/api/scan")

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["error"] == "RASPBERRY_PI_AGENT_TOKEN is not configured."


def test_pi_capture_request_requires_agent_token():
    client, _ = make_client()

    response = client.get("/api/pi-agent/capture-request")

    assert response.status_code == 401


def test_pi_capture_completion_failure_updates_latest_result():
    client, _ = make_client()
    client.post("/api/scan")
    request_response = client.get(
        "/api/pi-agent/capture-request",
        headers={"X-Rammlah-Agent-Token": "secret-token"},
    )
    request_id = request_response.json()["request_id"]

    complete_response = client.post(
        f"/api/pi-agent/capture-request/{request_id}/complete",
        headers={"X-Rammlah-Agent-Token": "secret-token"},
        json={"success": False, "error": "camera disconnected"},
    )
    latest_response = client.get("/api/latest")

    assert complete_response.status_code == 200
    assert latest_response.json()["success"] is False
    assert latest_response.json()["error"] == "camera disconnected"
    assert (
        client.get(
            "/api/pi-agent/capture-request",
            headers={"X-Rammlah-Agent-Token": "secret-token"},
        ).status_code
        == 204
    )
