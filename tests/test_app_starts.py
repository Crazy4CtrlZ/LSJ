"""CI-required test #1: the app starts and serves /health (rubric §8)."""
import os

os.environ.setdefault("BUILD_INDEX_ON_START", "0")  # keep CI fast; index tested separately

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_health_and_home():
    with TestClient(app) as client:  # context manager runs the lifespan (MCP spawn included)
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "mcp_connected" in body and "index_size" in body

        r = client.get("/")
        assert r.status_code == 200
        assert b"LSJ HR Copilot" in r.content


def test_chat_validates_input():
    with TestClient(app) as client:
        assert client.post("/chat", json={}).status_code == 422  # message required
