"""Integration test: full permission lifecycle using in-memory implementations.

Covers the end-to-end flow:
1. Admin grants/revokes permissions via the admin API
2. Agents respect read/write enforcement on ingestion
3. Router filters shared schemas by read permission
4. Unauthorized agents are denied access
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from neocortex.db.mock import InMemoryRepository
from neocortex.graph_router import GraphRouter
from neocortex.ingestion.episode_processor import EpisodeProcessor
from neocortex.mcp_settings import MCPSettings
from neocortex.permissions.memory_service import InMemoryPermissionService
from neocortex.schemas.graph import GraphInfo

BOOTSTRAP_ADMIN = "admin"
SHARED_SCHEMA = "ncx_shared__research"


def _make_graph(agent_id: str, purpose: str, schema_name: str, is_shared: bool = False) -> GraphInfo:
    return GraphInfo(
        id=1,
        agent_id=agent_id,
        purpose=purpose,
        schema_name=schema_name,
        is_shared=is_shared,
        created_at=datetime.now(UTC),
    )


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
def schema_mgr() -> AsyncMock:
    """Mock schema manager with one shared graph."""
    mgr = AsyncMock()
    shared = _make_graph("shared", "research", SHARED_SCHEMA, is_shared=True)

    async def list_graphs(agent_id: str | None = None) -> list[GraphInfo]:
        if agent_id == "shared":
            return [shared]
        if agent_id is not None:
            return [_make_graph(agent_id, "personal", f"ncx_{agent_id}__personal")]
        return [shared]

    mgr.list_graphs = AsyncMock(side_effect=list_graphs)
    return mgr


@pytest.fixture
def router(schema_mgr: AsyncMock, permissions: InMemoryPermissionService) -> GraphRouter:
    pool = AsyncMock()
    return GraphRouter(schema_mgr, pool, permissions=permissions)


@pytest.fixture
def app(
    settings: MCPSettings,
    repo: InMemoryRepository,
    permissions: InMemoryPermissionService,
    processor: EpisodeProcessor,
):
    from fastapi import FastAPI

    from neocortex.admin.routes import router as admin_router
    from neocortex.ingestion.routes import router as ingest_router

    app = FastAPI()
    app.state.settings = settings
    app.state.permissions = permissions
    app.state.processor = processor
    app.state.schema_mgr = None  # mock mode
    app.state.token_map = {
        "admin-token": BOOTSTRAP_ADMIN,
        "alice-token": "alice",
        "bob-token": "bob",
        "eve-token": "eve",
    }

    app.include_router(ingest_router)
    app.include_router(admin_router)
    return app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


ADMIN_HEADERS = {"Authorization": "Bearer admin-token"}
ALICE_HEADERS = {"Authorization": "Bearer alice-token"}
BOB_HEADERS = {"Authorization": "Bearer bob-token"}
EVE_HEADERS = {"Authorization": "Bearer eve-token"}


# ---------------------------------------------------------------------------
# Full permission lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_permission_lifecycle(
    client: AsyncClient,
    permissions: InMemoryPermissionService,
    repo: InMemoryRepository,
    router: GraphRouter,
) -> None:
    """End-to-end permission flow covering admin grant/revoke, ingestion enforcement,
    and router filtering."""

    # ── Step 1: Bootstrap admin exists ──
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)

    # ── Step 2: Admin grants alice read+write on shared research ──
    resp = await client.post(
        "/admin/permissions",
        json={
            "agent_id": "alice",
            "schema_name": SHARED_SCHEMA,
            "can_read": True,
            "can_write": True,
        },
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["agent_id"] == "alice"
    assert resp.json()["can_write"] is True

    # ── Step 3: Admin grants bob read-only on shared research ──
    resp = await client.post(
        "/admin/permissions",
        json={
            "agent_id": "bob",
            "schema_name": SHARED_SCHEMA,
            "can_read": True,
            "can_write": False,
        },
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["can_write"] is False

    # ── Step 4: Alice ingests text with target_graph -> success ──
    resp = await client.post(
        "/ingest/text",
        json={"text": "Research finding A", "target_graph": SHARED_SCHEMA},
        headers=ALICE_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "stored"
    assert SHARED_SCHEMA in repo._schema_episodes
    assert len(repo._schema_episodes[SHARED_SCHEMA]) == 1

    # ── Step 5: Bob ingests text with target_graph -> 403 (read-only) ──
    resp = await client.post(
        "/ingest/text",
        json={"text": "Bob's contribution", "target_graph": SHARED_SCHEMA},
        headers=BOB_HEADERS,
    )
    assert resp.status_code == 403
    assert "does not have write access" in resp.json()["detail"]

    # ── Step 6: Alice recalls -> sees shared research schema ──
    schemas = await router.route_recall("alice")
    assert "ncx_alice__personal" in schemas
    assert SHARED_SCHEMA in schemas

    # ── Step 7: Bob recalls -> sees shared research schema (read OK) ──
    schemas = await router.route_recall("bob")
    assert "ncx_bob__personal" in schemas
    assert SHARED_SCHEMA in schemas

    # ── Step 8: Unauthorized agent "eve" -> does NOT see shared research ──
    schemas = await router.route_recall("eve")
    assert "ncx_eve__personal" in schemas
    assert SHARED_SCHEMA not in schemas

    # ── Step 9: Admin revokes alice's write -> alice ingestion now 403 ──
    resp = await client.delete(
        f"/admin/permissions/alice/{SHARED_SCHEMA}",
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200

    resp = await client.post(
        "/ingest/text",
        json={"text": "Alice tries again", "target_graph": SHARED_SCHEMA},
        headers=ALICE_HEADERS,
    )
    assert resp.status_code == 403

    # Alice also no longer sees the shared schema in recall
    schemas = await router.route_recall("alice")
    assert SHARED_SCHEMA not in schemas

    # ── Step 10: Verify permissions list reflects changes ──
    # Use schema_name filter since unfiltered list iterates registered agents only
    resp = await client.get("/admin/permissions", params={"schema_name": SHARED_SCHEMA}, headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    remaining = resp.json()
    # Only bob's permission remains
    assert len(remaining) == 1
    assert remaining[0]["agent_id"] == "bob"


# ---------------------------------------------------------------------------
# Admin agent management lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_lifecycle(
    client: AsyncClient,
    permissions: InMemoryPermissionService,
) -> None:
    """Admin promotes/demotes agents; bootstrap admin cannot be demoted."""
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)

    # Promote alice to admin
    resp = await client.put(
        "/admin/agents/alice/admin",
        json={"is_admin": True},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200

    # Alice can now access admin endpoints
    resp = await client.get("/admin/agents", headers=ALICE_HEADERS)
    assert resp.status_code == 200

    # Demote alice
    resp = await client.delete("/admin/agents/alice/admin", headers=ADMIN_HEADERS)
    assert resp.status_code == 200

    # Alice can no longer access admin endpoints
    resp = await client.get("/admin/agents", headers=ALICE_HEADERS)
    assert resp.status_code == 403

    # Bootstrap admin cannot be demoted
    resp = await client.delete(f"/admin/agents/{BOOTSTRAP_ADMIN}/admin", headers=ADMIN_HEADERS)
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Route discover respects permissions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_discover_filters_by_permission(
    permissions: InMemoryPermissionService,
    router: GraphRouter,
) -> None:
    """route_discover only returns schemas the agent can read."""
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)

    # Alice has no permissions -> discover sees only personal
    schemas = await router.route_discover("alice")
    assert "ncx_alice__personal" in schemas
    assert SHARED_SCHEMA not in schemas

    # Grant read permission
    await permissions.grant("alice", SHARED_SCHEMA, can_read=True, can_write=False, granted_by=BOOTSTRAP_ADMIN)

    # Now alice discovers the shared schema
    schemas = await router.route_discover("alice")
    assert SHARED_SCHEMA in schemas


# ---------------------------------------------------------------------------
# Admin bypasses all permission checks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_bypasses_all_checks(
    client: AsyncClient,
    permissions: InMemoryPermissionService,
    repo: InMemoryRepository,
    router: GraphRouter,
) -> None:
    """Admin agent bypasses permission checks for ingestion and recall."""
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)

    # Admin can ingest to shared schema without explicit grant
    resp = await client.post(
        "/ingest/text",
        json={"text": "Admin knowledge", "target_graph": SHARED_SCHEMA},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200

    # Admin sees all shared schemas in recall
    schemas = await router.route_recall(BOOTSTRAP_ADMIN)
    assert SHARED_SCHEMA in schemas
