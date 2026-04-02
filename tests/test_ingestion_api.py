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
    return MCPSettings(
        auth_mode="dev_token", mock_db=True, dev_token="test-token", dev_user_id="test-agent", dev_tokens_file=""
    )


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


def test_text_ingestion_empty_text_rejected(anon_client):
    resp = anon_client.post("/ingest/text", json={"text": ""})
    assert resp.status_code == 422


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


def test_events_ingestion_empty_list_rejected(anon_client):
    resp = anon_client.post("/ingest/events", json={"events": []})
    assert resp.status_code == 422


def test_events_ingestion_with_metadata(anon_client):
    resp = anon_client.post(
        "/ingest/events",
        json={"events": [{"e": 1}], "metadata": {"batch_id": "abc"}},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "stored"


# --- Dedup: text ingestion ---


def test_text_ingestion_returns_content_hash(anon_client):
    resp = anon_client.post("/ingest/text", json={"text": "hash me"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "stored"
    assert data["content_hash"] is not None
    assert len(data["content_hash"]) == 64


def test_text_ingestion_duplicate_returns_skipped(anon_client):
    text = "dedup test content"
    r1 = anon_client.post("/ingest/text", json={"text": text})
    assert r1.status_code == 200
    assert r1.json()["status"] == "stored"

    r2 = anon_client.post("/ingest/text", json={"text": text})
    assert r2.status_code == 200
    data = r2.json()
    assert data["status"] == "skipped"
    assert data["episodes_created"] == 0
    assert data["existing_episode_id"] is not None
    assert data["content_hash"] == r1.json()["content_hash"]


def test_text_ingestion_force_always_stores(anon_client):
    text = "force test content"
    r1 = anon_client.post("/ingest/text", json={"text": text})
    assert r1.json()["status"] == "stored"

    r2 = anon_client.post("/ingest/text", json={"text": text, "force": True})
    assert r2.status_code == 200
    assert r2.json()["status"] == "stored"
    assert r2.json()["episodes_created"] == 1


# --- Check endpoint ---


def test_check_unknown_hashes_returns_missing(anon_client):
    resp = anon_client.post("/ingest/check", json={"hashes": ["abc123", "def456"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["existing"] == {}
    assert set(data["missing"]) == {"abc123", "def456"}


def test_check_after_ingestion_hash_exists(anon_client):
    # Ingest some text
    r1 = anon_client.post("/ingest/text", json={"text": "check me"})
    content_hash = r1.json()["content_hash"]

    # Check: the hash should now exist
    r2 = anon_client.post("/ingest/check", json={"hashes": [content_hash, "unknown"]})
    assert r2.status_code == 200
    data = r2.json()
    assert content_hash in data["existing"]
    assert data["missing"] == ["unknown"]


def test_check_batch_mixed(anon_client):
    # Ingest two texts
    r1 = anon_client.post("/ingest/text", json={"text": "first"})
    r2 = anon_client.post("/ingest/text", json={"text": "second"})
    h1 = r1.json()["content_hash"]
    h2 = r2.json()["content_hash"]

    # Check: both should exist, plus one unknown
    resp = anon_client.post("/ingest/check", json={"hashes": [h1, h2, "nope"]})
    data = resp.json()
    assert h1 in data["existing"]
    assert h2 in data["existing"]
    assert data["missing"] == ["nope"]


def test_check_agent_isolation(auth_client):
    # Ingest as test-agent (mapped from test-token)
    r1 = auth_client.post(
        "/ingest/text",
        json={"text": "agent-specific"},
        headers={"Authorization": "Bearer test-token"},
    )
    content_hash = r1.json()["content_hash"]

    # Check with same token — should find it
    r2 = auth_client.post(
        "/ingest/check",
        json={"hashes": [content_hash]},
        headers={"Authorization": "Bearer test-token"},
    )
    assert content_hash in r2.json()["existing"]


def test_check_missing_token_returns_401(auth_client):
    resp = auth_client.post("/ingest/check", json={"hashes": ["abc"]})
    assert resp.status_code == 401


def test_check_empty_hashes_returns_422(anon_client):
    resp = anon_client.post("/ingest/check", json={"hashes": []})
    assert resp.status_code == 422
