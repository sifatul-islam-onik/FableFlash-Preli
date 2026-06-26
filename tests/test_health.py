"""Test GET /health endpoint."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    """GET /health must return {"status": "ok"} with 200."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "ok"}


def test_health_response_time():
    """GET /health should respond quickly."""
    import time
    start = time.time()
    response = client.get("/health")
    elapsed = time.time() - start
    assert response.status_code == 200
    assert elapsed < 1.0  # well within 60s requirement
