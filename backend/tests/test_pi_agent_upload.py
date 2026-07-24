from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.inspection import router
from app.schemas import ExecutionMode, ImageSource, InspectionResult


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
    app.state.settings = SimpleNamespace(raspberry_pi_agent_token_value=token)
    app.state.inspection_service = service
    app.include_router(router)
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
