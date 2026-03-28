"""Tests for the Admin REST API."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from neocortex.mcp_settings import MCPSettings
from neocortex.permissions.memory_service import InMemoryPermissionService

BOOTSTRAP_ADMIN = "admin"
SHARED_SCHEMA = "ncx_shared__knowledge"


@pytest.fixture
def settings() -> MCPSettings:
    return MCPSettings(mock_db=True, extraction_enabled=False, auth_mode="dev_token")


@pytest.fixture
def permissions() -> InMemoryPermissionService:
    svc = InMemoryPermissionService(bootstrap_admin_id=BOOTSTRAP_ADMIN)
    return svc


@pytest.fixture
def app(settings: MCPSettings, permissions: InMemoryPermissionService):
    from fastapi import FastAPI

    from neocortex.admin.routes import router as admin_router
    from neocortex.ingestion.routes import router as ingest_router

    app = FastAPI()
    app.state.settings = settings
    app.state.permissions = permissions
    app.state.schema_mgr = None  # mock mode — no graph management
    app.state.token_map = {
        "admin-token": BOOTSTRAP_ADMIN,
        "alice-token": "alice",
        "bob-token": "bob",
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


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_admin_gets_403_on_permissions(client: AsyncClient) -> None:
    resp = await client.get("/admin/permissions", headers=ALICE_HEADERS)
    assert resp.status_code == 403
    assert "Admin access required" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_non_admin_gets_403_on_agents(client: AsyncClient) -> None:
    resp = await client.get("/admin/agents", headers=ALICE_HEADERS)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_gets_403_on_grant(client: AsyncClient) -> None:
    resp = await client.post(
        "/admin/permissions",
        json={"agent_id": "alice", "schema_name": SHARED_SCHEMA, "can_read": True},
        headers=ALICE_HEADERS,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Permission grant / list / revoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_grants_permission(client: AsyncClient, permissions: InMemoryPermissionService) -> None:
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)

    resp = await client.post(
        "/admin/permissions",
        json={"agent_id": "alice", "schema_name": SHARED_SCHEMA, "can_read": True, "can_write": False},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == "alice"
    assert data["schema_name"] == SHARED_SCHEMA
    assert data["can_read"] is True
    assert data["can_write"] is False
    assert data["granted_by"] == BOOTSTRAP_ADMIN


@pytest.mark.asyncio
async def test_admin_lists_permissions_for_agent(client: AsyncClient, permissions: InMemoryPermissionService) -> None:
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)
    await permissions.grant("alice", SHARED_SCHEMA, can_read=True, can_write=True, granted_by=BOOTSTRAP_ADMIN)

    resp = await client.get("/admin/permissions/alice", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["agent_id"] == "alice"


@pytest.mark.asyncio
async def test_admin_lists_permissions_with_agent_filter(
    client: AsyncClient, permissions: InMemoryPermissionService
) -> None:
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)
    await permissions.grant("alice", SHARED_SCHEMA, can_read=True, can_write=True, granted_by=BOOTSTRAP_ADMIN)

    resp = await client.get("/admin/permissions", params={"agent_id": "alice"}, headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1


@pytest.mark.asyncio
async def test_admin_lists_permissions_with_schema_filter(
    client: AsyncClient, permissions: InMemoryPermissionService
) -> None:
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)
    await permissions.grant("alice", SHARED_SCHEMA, can_read=True, can_write=True, granted_by=BOOTSTRAP_ADMIN)
    await permissions.grant("bob", SHARED_SCHEMA, can_read=True, can_write=False, granted_by=BOOTSTRAP_ADMIN)

    resp = await client.get("/admin/permissions", params={"schema_name": SHARED_SCHEMA}, headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_admin_revokes_permission(client: AsyncClient, permissions: InMemoryPermissionService) -> None:
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)
    await permissions.grant("alice", SHARED_SCHEMA, can_read=True, can_write=True, granted_by=BOOTSTRAP_ADMIN)

    resp = await client.delete(f"/admin/permissions/alice/{SHARED_SCHEMA}", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"

    # Verify permission is gone
    assert not await permissions.can_read_schema("alice", SHARED_SCHEMA)


@pytest.mark.asyncio
async def test_admin_revoke_nonexistent_returns_404(
    client: AsyncClient, permissions: InMemoryPermissionService
) -> None:
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)

    resp = await client.delete(f"/admin/permissions/alice/{SHARED_SCHEMA}", headers=ADMIN_HEADERS)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_updates_permission(client: AsyncClient, permissions: InMemoryPermissionService) -> None:
    """Grant with changed flags reflects new state."""
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)
    await permissions.grant("alice", SHARED_SCHEMA, can_read=True, can_write=False, granted_by=BOOTSTRAP_ADMIN)

    # Update to add write
    resp = await client.post(
        "/admin/permissions",
        json={"agent_id": "alice", "schema_name": SHARED_SCHEMA, "can_read": True, "can_write": True},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["can_write"] is True

    # Verify in service
    assert await permissions.can_write_schema("alice", SHARED_SCHEMA)


# ---------------------------------------------------------------------------
# Agent management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_lists_agents(client: AsyncClient, permissions: InMemoryPermissionService) -> None:
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)

    resp = await client.get("/admin/agents", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert any(a["agent_id"] == BOOTSTRAP_ADMIN for a in data)


@pytest.mark.asyncio
async def test_admin_promotes_agent(client: AsyncClient, permissions: InMemoryPermissionService) -> None:
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)

    resp = await client.put(
        "/admin/agents/alice/admin",
        json={"is_admin": True},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "promoted"

    # Alice is now admin and can access admin endpoints
    resp2 = await client.get("/admin/agents", headers=ALICE_HEADERS)
    assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_admin_demotes_agent(client: AsyncClient, permissions: InMemoryPermissionService) -> None:
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)
    await permissions.set_admin("alice", is_admin=True)

    resp = await client.delete("/admin/agents/alice/admin", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "demoted"

    # Alice is no longer admin
    resp2 = await client.get("/admin/agents", headers=ALICE_HEADERS)
    assert resp2.status_code == 403


@pytest.mark.asyncio
async def test_bootstrap_admin_demotion_returns_400(
    client: AsyncClient, permissions: InMemoryPermissionService
) -> None:
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)

    resp = await client.delete(f"/admin/agents/{BOOTSTRAP_ADMIN}/admin", headers=ADMIN_HEADERS)
    assert resp.status_code == 400
    assert "bootstrap" in resp.json()["detail"].lower() or "Cannot" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_bootstrap_admin_demotion_via_put_returns_400(
    client: AsyncClient, permissions: InMemoryPermissionService
) -> None:
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)

    resp = await client.put(
        f"/admin/agents/{BOOTSTRAP_ADMIN}/admin",
        json={"is_admin": False},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Graph management (mock mode — schema_mgr is None)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_create_returns_501_in_mock_mode(
    client: AsyncClient, permissions: InMemoryPermissionService
) -> None:
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)

    resp = await client.post(
        "/admin/graphs",
        json={"purpose": "test"},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 501


@pytest.mark.asyncio
async def test_graph_list_returns_501_in_mock_mode(client: AsyncClient, permissions: InMemoryPermissionService) -> None:
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)

    resp = await client.get("/admin/graphs", headers=ADMIN_HEADERS)
    assert resp.status_code == 501


@pytest.mark.asyncio
async def test_graph_delete_returns_501_in_mock_mode(
    client: AsyncClient, permissions: InMemoryPermissionService
) -> None:
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)

    resp = await client.delete("/admin/graphs/ncx_shared__test", headers=ADMIN_HEADERS)
    assert resp.status_code == 501
