from fastapi.testclient import TestClient


def test_backend_accepts_preserved_and_stripped_api_paths(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from app.main import app

    with TestClient(app) as client:
        api_response = client.get("/api/status")
        stripped_response = client.get("/status")

    assert api_response.status_code == 200
    assert stripped_response.status_code == 200


def test_backend_serves_captures_when_images_prefix_is_stripped(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from app.config import get_settings
    from app.main import app

    settings = get_settings()
    capture_path = settings.captures_dir / "static-route-test.jpg"
    capture_path.write_bytes(b"fake-jpeg-bytes")

    try:
        with TestClient(app) as client:
            response = client.get("/captures/static-route-test.jpg")
    finally:
        capture_path.unlink(missing_ok=True)

    assert response.status_code == 200
    assert response.content == b"fake-jpeg-bytes"
