"""Tests for ingestion API permission enforcement with target_graph."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from neocortex.db.mock import InMemoryRepository
from neocortex.ingestion.episode_processor import EpisodeProcessor
from neocortex.mcp_settings import MCPSettings
from neocortex.permissions.memory_service import InMemoryPermissionService

BOOTSTRAP_ADMIN = "admin"
SHARED_SCHEMA = "ncx_shared__research"


@pytest.fixture
def settings() -> MCPSettings:
    return MCPSettings(mock_db=True, extraction_enabled=False, auth_mode="dev_token")


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.fixture
def permissions() -> InMemoryPermissionService:
    return InMemoryPermissionService(bootstrap_admin_id=BOOTSTRAP_ADMIN)


@pytest.fixture
def processor(repo: InMemoryRepository) -> EpisodeProcessor:
    return EpisodeProcessor(repo=repo, extraction_enabled=False)


@pytest.fixture
def app(
    settings: MCPSettings, repo: InMemoryRepository, permissions: InMemoryPermissionService, processor: EpisodeProcessor
):
    """Create a FastAPI app with mocked services."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    from neocortex.ingestion.routes import router

    app = FastAPI()
    app.state.settings = settings
    app.state.processor = processor
    app.state.permissions = permissions
    app.state.token_map = {
        "admin-token": BOOTSTRAP_ADMIN,
        "alice-token": "alice",
        "bob-token": "bob",
        "eve-token": "eve",
    }

    @app.get("/health")
    async def health():
        return JSONResponse({"status": "ok"})

    app.include_router(router)
    return app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_ingest_text_no_target_graph(client: AsyncClient, repo: InMemoryRepository) -> None:
    """Ingest text without target_graph stores to personal (unchanged behavior)."""
    resp = await client.post(
        "/ingest/text",
        json={"text": "Hello world"},
        headers={"Authorization": "Bearer alice-token"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "stored"
    assert data["episodes_created"] == 1
    assert len(repo._episodes) == 1
    assert len(repo._schema_episodes) == 0


@pytest.mark.asyncio
async def test_ingest_text_with_target_graph_no_permission(
    client: AsyncClient, permissions: InMemoryPermissionService
) -> None:
    """Agent without write permission gets 403 when target_graph is set."""
    resp = await client.post(
        "/ingest/text",
        json={"text": "Shared fact", "target_graph": SHARED_SCHEMA},
        headers={"Authorization": "Bearer alice-token"},
    )
    assert resp.status_code == 403
    assert "does not have write access" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_ingest_text_with_target_graph_read_only(
    client: AsyncClient, permissions: InMemoryPermissionService
) -> None:
    """Agent with read-only permission gets 403 when target_graph is set."""
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)
    await permissions.grant("alice", SHARED_SCHEMA, can_read=True, can_write=False, granted_by=BOOTSTRAP_ADMIN)

    resp = await client.post(
        "/ingest/text",
        json={"text": "Shared fact", "target_graph": SHARED_SCHEMA},
        headers={"Authorization": "Bearer alice-token"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_ingest_text_with_target_graph_write_permission(
    client: AsyncClient, permissions: InMemoryPermissionService, repo: InMemoryRepository
) -> None:
    """Agent with write permission can ingest to target_graph."""
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)
    await permissions.grant("alice", SHARED_SCHEMA, can_read=True, can_write=True, granted_by=BOOTSTRAP_ADMIN)

    resp = await client.post(
        "/ingest/text",
        json={"text": "Shared research fact", "target_graph": SHARED_SCHEMA},
        headers={"Authorization": "Bearer alice-token"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "stored"
    # Episode stored in target schema bucket
    assert SHARED_SCHEMA in repo._schema_episodes
    assert len(repo._schema_episodes[SHARED_SCHEMA]) == 1


@pytest.mark.asyncio
async def test_ingest_text_admin_bypasses_permission(
    client: AsyncClient, permissions: InMemoryPermissionService, repo: InMemoryRepository
) -> None:
    """Admin agent bypasses permission checks."""
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)

    resp = await client.post(
        "/ingest/text",
        json={"text": "Admin shared fact", "target_graph": SHARED_SCHEMA},
        headers={"Authorization": "Bearer admin-token"},
    )
    assert resp.status_code == 200
    assert SHARED_SCHEMA in repo._schema_episodes


@pytest.mark.asyncio
async def test_ingest_events_with_target_graph_no_permission(
    client: AsyncClient, permissions: InMemoryPermissionService
) -> None:
    """Events ingestion respects permissions."""
    resp = await client.post(
        "/ingest/events",
        json={"events": [{"type": "test"}], "target_graph": SHARED_SCHEMA},
        headers={"Authorization": "Bearer alice-token"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_ingest_events_with_target_graph_write_permission(
    client: AsyncClient, permissions: InMemoryPermissionService, repo: InMemoryRepository
) -> None:
    """Events ingestion with write permission succeeds."""
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)
    await permissions.grant("alice", SHARED_SCHEMA, can_read=True, can_write=True, granted_by=BOOTSTRAP_ADMIN)

    resp = await client.post(
        "/ingest/events",
        json={"events": [{"type": "test"}], "target_graph": SHARED_SCHEMA},
        headers={"Authorization": "Bearer alice-token"},
    )
    assert resp.status_code == 200
    assert SHARED_SCHEMA in repo._schema_episodes


@pytest.mark.asyncio
async def test_ingest_document_with_target_graph_no_permission(
    client: AsyncClient, permissions: InMemoryPermissionService
) -> None:
    """Document ingestion respects permissions."""
    resp = await client.post(
        "/ingest/document",
        files={"file": ("test.txt", b"hello", "text/plain")},
        data={"target_graph": SHARED_SCHEMA},
        headers={"Authorization": "Bearer alice-token"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_ingest_document_with_target_graph_write_permission(
    client: AsyncClient, permissions: InMemoryPermissionService, repo: InMemoryRepository
) -> None:
    """Document ingestion with write permission succeeds."""
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)
    await permissions.grant("alice", SHARED_SCHEMA, can_read=True, can_write=True, granted_by=BOOTSTRAP_ADMIN)

    resp = await client.post(
        "/ingest/document",
        files={"file": ("test.txt", b"shared research content", "text/plain")},
        data={"target_graph": SHARED_SCHEMA},
        headers={"Authorization": "Bearer alice-token"},
    )
    assert resp.status_code == 200
    assert SHARED_SCHEMA in repo._schema_episodes
