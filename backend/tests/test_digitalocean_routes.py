from fastapi.testclient import TestClient


def test_backend_accepts_preserved_and_stripped_api_paths(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    from app.main import app

    with TestClient(app) as client:
        api_response = client.get("/api/status")
        stripped_response = client.get("/status")

    assert api_response.status_code == 200
    assert stripped_response.status_code == 200
