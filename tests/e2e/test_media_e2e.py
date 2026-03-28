"""
End-to-end tests for the media ingestion pipeline.

Starts the ingestion app in mock mode (mock_db=True) via the
FastAPI TestClient and exercises the full request->response cycle for
audio and video endpoints, plus regression checks on existing endpoints.
"""

import io
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from neocortex.ingestion.app import create_app
from neocortex.mcp_settings import MCPSettings


@pytest.fixture()
def client(tmp_path) -> Generator[TestClient]:
    """Create a TestClient against the ingestion app in mock mode."""
    settings = MCPSettings(
        auth_mode="none",
        mock_db=True,
        media_store_path=str(tmp_path / "media_store"),
    )
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


class TestAudioEndpoint:
    def test_upload_wav_returns_stored(self, client: TestClient, synthetic_wav: str):
        with open(synthetic_wav, "rb") as f:
            resp = client.post(
                "/ingest/audio",
                files={"file": ("test.wav", f, "audio/wav")},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "stored"
        assert body["episodes_created"] >= 1
        assert body.get("media_ref") is not None
        assert body["media_ref"]["original_filename"] == "test.wav"

    def test_rejects_unsupported_content_type(self, client: TestClient, tmp_path):
        fake = tmp_path / "notes.txt"
        fake.write_text("hello")
        with open(fake, "rb") as f:
            resp = client.post(
                "/ingest/audio",
                files={"file": ("notes.txt", f, "text/plain")},
            )
        assert resp.status_code == 415

    def test_rejects_oversized_upload(self, client: TestClient, oversized_bytes: bytes):
        resp = client.post(
            "/ingest/audio",
            files={"file": ("big.wav", io.BytesIO(oversized_bytes), "audio/wav")},
        )
        assert resp.status_code == 413


class TestVideoEndpoint:
    def test_upload_mp4_returns_stored(self, client: TestClient, synthetic_mp4: str):
        with open(synthetic_mp4, "rb") as f:
            resp = client.post(
                "/ingest/video",
                files={"file": ("test.mp4", f, "video/mp4")},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "stored"
        assert body["episodes_created"] >= 1
        assert body.get("media_ref") is not None

    def test_rejects_unsupported_content_type(self, client: TestClient, tmp_path):
        fake = tmp_path / "doc.pdf"
        fake.write_bytes(b"%PDF-fake")
        with open(fake, "rb") as f:
            resp = client.post(
                "/ingest/video",
                files={"file": ("doc.pdf", f, "application/pdf")},
            )
        assert resp.status_code == 415


class TestRegressionExistingEndpoints:
    """Ensure adding media endpoints did not break text/document/events."""

    def test_health(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_ingest_text(self, client: TestClient):
        resp = client.post(
            "/ingest/text",
            json={"text": "Regression test content", "metadata": {}},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "stored"

    def test_ingest_document(self, client: TestClient):
        resp = client.post(
            "/ingest/document",
            files={"file": ("test.txt", b"doc content", "text/plain")},
        )
        assert resp.status_code == 200

    def test_ingest_events(self, client: TestClient):
        resp = client.post(
            "/ingest/events",
            json={"events": [{"type": "test", "data": "hello"}], "metadata": {}},
        )
        assert resp.status_code == 200
