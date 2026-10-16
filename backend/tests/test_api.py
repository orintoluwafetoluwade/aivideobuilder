import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    # Enter TestClient as a context manager so FastAPI startup hooks initialize SQLite.
    with TestClient(app) as test_client:
        yield test_client

def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "gemini" in response.json()["integrations"]

def test_create_and_read_project(client):
    response = client.post("/api/projects", json={
        "topic": "A story about courage", "style": "Animated story",
        "format": "YouTube Shorts", "duration_minutes": 1
    })
    assert response.status_code == 201
    project = response.json()
    assert project["topic"] == "A story about courage"
    assert project["scenes"] == []
    assert client.get("/api/projects/" + project["id"]).json()["id"] == project["id"]

def test_invalid_topic_rejected(client):
    assert client.post("/api/projects", json={"topic": "x", "duration_minutes": 1}).status_code == 422

def test_render_requires_scenes(client):
    project = client.post("/api/projects", json={"topic": "Render validation example", "duration_minutes": 1}).json()
    assert client.post("/api/projects/" + project["id"] + "/render").status_code == 409
