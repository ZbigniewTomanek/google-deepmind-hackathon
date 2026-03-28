"""Tests for GraphRouter permission enforcement."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from neocortex.graph_router import GraphRouter
from neocortex.permissions.memory_service import InMemoryPermissionService
from neocortex.schemas.graph import GraphInfo

BOOTSTRAP_ADMIN = "admin"
SHARED_SCHEMA = "ncx_shared__knowledge"
SHARED_SCHEMA_2 = "ncx_shared__research"
PERSONAL_SCHEMA = "ncx_alice__personal"


def _make_graph(agent_id: str, purpose: str, schema_name: str, is_shared: bool = False) -> GraphInfo:
    return GraphInfo(
        id=1,
        agent_id=agent_id,
        purpose=purpose,
        schema_name=schema_name,
        is_shared=is_shared,
        created_at=datetime.now(UTC),
    )


@pytest_asyncio.fixture
async def permissions() -> InMemoryPermissionService:
    svc = InMemoryPermissionService(bootstrap_admin_id=BOOTSTRAP_ADMIN)
    await svc.ensure_admin(BOOTSTRAP_ADMIN)
    return svc


@pytest.fixture
def schema_mgr() -> AsyncMock:
    mgr = AsyncMock()
    # Default: alice has a personal graph, two shared graphs exist
    personal = _make_graph("alice", "personal", PERSONAL_SCHEMA)
    shared1 = _make_graph("shared", "knowledge", SHARED_SCHEMA, is_shared=True)
    shared2 = _make_graph("shared", "research", SHARED_SCHEMA_2, is_shared=True)

    async def list_graphs(agent_id: str | None = None) -> list[GraphInfo]:
        if agent_id == "alice":
            return [personal]
        if agent_id == "shared":
            return [shared1, shared2]
        return []

    mgr.list_graphs = AsyncMock(side_effect=list_graphs)
    return mgr


@pytest.fixture
def router(schema_mgr: AsyncMock, permissions: InMemoryPermissionService) -> GraphRouter:
    pool = AsyncMock()  # Not used directly in these tests
    return GraphRouter(schema_mgr, pool, permissions=permissions)


# ── route_recall tests ──


@pytest.mark.asyncio
async def test_route_recall_no_shared_permissions(router: GraphRouter) -> None:
    """Agent with no shared permissions sees only personal schemas."""
    schemas = await router.route_recall("alice")
    assert schemas == [PERSONAL_SCHEMA]


@pytest.mark.asyncio
async def test_route_recall_with_read_permission(router: GraphRouter, permissions: InMemoryPermissionService) -> None:
    """Agent with read on one shared graph sees personal + that shared graph."""
    await permissions.grant("alice", SHARED_SCHEMA, can_read=True, can_write=False, granted_by=BOOTSTRAP_ADMIN)
    schemas = await router.route_recall("alice")
    assert PERSONAL_SCHEMA in schemas
    assert SHARED_SCHEMA in schemas
    assert SHARED_SCHEMA_2 not in schemas


@pytest.mark.asyncio
async def test_route_recall_admin_bypasses_checks(permissions: InMemoryPermissionService) -> None:
    """Admin agent sees all shared schemas without explicit grants."""
    admin_personal = _make_graph(BOOTSTRAP_ADMIN, "personal", f"ncx_{BOOTSTRAP_ADMIN}__personal")
    shared1 = _make_graph("shared", "knowledge", SHARED_SCHEMA, is_shared=True)
    shared2 = _make_graph("shared", "research", SHARED_SCHEMA_2, is_shared=True)

    async def list_graphs(agent_id: str | None = None) -> list[GraphInfo]:
        if agent_id == BOOTSTRAP_ADMIN:
            return [admin_personal]
        if agent_id == "shared":
            return [shared1, shared2]
        return []

    mgr = AsyncMock()
    mgr.list_graphs = AsyncMock(side_effect=list_graphs)
    pool = AsyncMock()
    admin_router = GraphRouter(mgr, pool, permissions=permissions)

    schemas = await admin_router.route_recall(BOOTSTRAP_ADMIN)
    assert SHARED_SCHEMA in schemas
    assert SHARED_SCHEMA_2 in schemas


# ── route_discover tests ──


@pytest.mark.asyncio
async def test_route_discover_respects_read_permissions(
    router: GraphRouter, permissions: InMemoryPermissionService
) -> None:
    """route_discover filters shared schemas by read permission."""
    await permissions.grant("alice", SHARED_SCHEMA_2, can_read=True, can_write=False, granted_by=BOOTSTRAP_ADMIN)
    schemas = await router.route_discover("alice")
    assert PERSONAL_SCHEMA in schemas
    assert SHARED_SCHEMA_2 in schemas
    assert SHARED_SCHEMA not in schemas


# ── route_store_to tests ──


@pytest.mark.asyncio
async def test_route_store_to_without_write_raises(router: GraphRouter) -> None:
    """Agent without write permission gets PermissionError."""
    with pytest.raises(PermissionError, match="does not have write access"):
        await router.route_store_to("alice", SHARED_SCHEMA)


@pytest.mark.asyncio
async def test_route_store_to_with_write_succeeds(router: GraphRouter, permissions: InMemoryPermissionService) -> None:
    """Agent with write permission gets the target schema back."""
    await permissions.grant("alice", SHARED_SCHEMA, can_read=True, can_write=True, granted_by=BOOTSTRAP_ADMIN)
    result = await router.route_store_to("alice", SHARED_SCHEMA)
    assert result == SHARED_SCHEMA


@pytest.mark.asyncio
async def test_route_store_to_nonexistent_schema_raises(router: GraphRouter) -> None:
    """Targeting a non-shared schema raises PermissionError."""
    with pytest.raises(PermissionError, match="is not a shared graph"):
        await router.route_store_to("alice", "ncx_shared__nonexistent")


@pytest.mark.asyncio
async def test_route_store_to_admin_bypasses(router: GraphRouter) -> None:
    """Admin agent bypasses write permission checks."""
    result = await router.route_store_to(BOOTSTRAP_ADMIN, SHARED_SCHEMA)
    assert result == SHARED_SCHEMA
