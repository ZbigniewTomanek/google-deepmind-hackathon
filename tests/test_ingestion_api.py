import io
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from neocortex.ingestion.app import create_app
from neocortex.mcp_settings import MCPSettings


@pytest.fixture
def anon_settings() -> MCPSettings:
    return MCPSettings(auth_mode="none", mock_db=True)


@pytest.fixture
def token_settings() -> MCPSettings:
    return MCPSettings(auth_mode="dev_token", mock_db=True, dev_token="test-token", dev_user_id="test-agent")


@pytest.fixture
def anon_client(anon_settings) -> Generator[TestClient]:
    app = create_app(anon_settings)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def auth_client(token_settings) -> Generator[TestClient]:
    app = create_app(token_settings)
    with TestClient(app) as client:
        yield client


# --- Health ---


def test_health(anon_client):
    resp = anon_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


# --- Text ingestion ---


def test_text_ingestion_anonymous(anon_client):
    resp = anon_client.post("/ingest/text", json={"text": "hello world"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "stored"
    assert data["episodes_created"] == 1


def test_text_ingestion_with_valid_token(auth_client):
    resp = auth_client.post(
        "/ingest/text",
        json={"text": "authenticated text"},
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "stored"


def test_text_ingestion_missing_token(auth_client):
    resp = auth_client.post("/ingest/text", json={"text": "no token"})
    assert resp.status_code == 401


def test_text_ingestion_invalid_token(auth_client):
    resp = auth_client.post(
        "/ingest/text",
        json={"text": "bad token"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401


# --- Document upload ---


def test_document_upload_valid(anon_client):
    file_content = b"Hello from a text file"
    resp = anon_client.post(
        "/ingest/document",
        files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "stored"
    assert data["episodes_created"] == 1


def test_document_upload_rejected_content_type(anon_client):
    resp = anon_client.post(
        "/ingest/document",
        files={"file": ("test.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
    )
    assert resp.status_code == 415


def test_document_upload_oversized(anon_client):
    big_content = b"x" * (10 * 1024 * 1024 + 1)  # Just over 10 MB
    resp = anon_client.post(
        "/ingest/document",
        files={"file": ("big.txt", io.BytesIO(big_content), "text/plain")},
    )
    assert resp.status_code == 413


def test_document_upload_markdown(anon_client):
    resp = anon_client.post(
        "/ingest/document",
        files={"file": ("doc.md", io.BytesIO(b"# Title\nBody"), "text/markdown")},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "stored"


def test_document_upload_csv(anon_client):
    resp = anon_client.post(
        "/ingest/document",
        files={"file": ("data.csv", io.BytesIO(b"a,b\n1,2"), "text/csv")},
    )
    assert resp.status_code == 200


def test_document_upload_json(anon_client):
    resp = anon_client.post(
        "/ingest/document",
        files={"file": ("data.json", io.BytesIO(b'{"key": "value"}'), "application/json")},
    )
    assert resp.status_code == 200


# --- Events ingestion ---


def test_events_ingestion(anon_client):
    events = [{"type": "click"}, {"type": "view"}]
    resp = anon_client.post("/ingest/events", json={"events": events})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "stored"
    assert data["episodes_created"] == 2


def test_events_ingestion_with_metadata(anon_client):
    resp = anon_client.post(
        "/ingest/events",
        json={"events": [{"e": 1}], "metadata": {"batch_id": "abc"}},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "stored"
