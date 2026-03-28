"""Tests for remember tool target_graph parameter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neocortex.db.mock import InMemoryRepository
from neocortex.mcp_settings import MCPSettings
from neocortex.permissions.memory_service import InMemoryPermissionService
from neocortex.schemas.memory import RememberResult

BOOTSTRAP_ADMIN = "admin"
SHARED_SCHEMA = "ncx_shared__knowledge"


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.fixture
def settings() -> MCPSettings:
    return MCPSettings(mock_db=True, extraction_enabled=False)


@pytest.fixture
def permissions() -> InMemoryPermissionService:
    return InMemoryPermissionService(bootstrap_admin_id=BOOTSTRAP_ADMIN)


def _make_router_mock(permissions: InMemoryPermissionService) -> AsyncMock:
    """Create a mock router with route_store_to delegating to real permission checks."""
    router = AsyncMock()

    async def route_store_to(agent_id: str, target_schema: str) -> str:
        # Simulate real route_store_to behavior
        if target_schema != SHARED_SCHEMA:
            raise PermissionError(f"Schema '{target_schema}' is not a shared graph")
        if not await permissions.can_write_schema(agent_id, target_schema):
            raise PermissionError(f"Agent '{agent_id}' does not have write access to '{target_schema}'")
        return target_schema

    router.route_store_to = AsyncMock(side_effect=route_store_to)
    return router


@pytest.mark.asyncio
async def test_remember_with_target_graph_and_write_permission(
    repo: InMemoryRepository, settings: MCPSettings, permissions: InMemoryPermissionService
) -> None:
    """remember with target_graph and write permission stores in target schema."""
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)
    await permissions.grant("alice", SHARED_SCHEMA, can_read=True, can_write=True, granted_by=BOOTSTRAP_ADMIN)

    router = _make_router_mock(permissions)
    ctx = MagicMock()
    ctx.lifespan_context = {
        "repo": repo,
        "settings": settings,
        "embeddings": None,
        "job_app": None,
        "router": router,
        "permissions": permissions,
    }

    with patch("neocortex.tools.remember.get_agent_id_from_context", return_value="alice"):
        from neocortex.tools.remember import remember

        result = await remember("Shared knowledge fact", target_graph=SHARED_SCHEMA, ctx=ctx)

    assert isinstance(result, RememberResult)
    assert result.status == "stored"
    assert result.episode_id > 0
    # Verify stored in schema-bucketed storage
    assert SHARED_SCHEMA in repo._schema_episodes
    assert len(repo._schema_episodes[SHARED_SCHEMA]) == 1
    assert repo._schema_episodes[SHARED_SCHEMA][0]["content"] == "Shared knowledge fact"


@pytest.mark.asyncio
async def test_remember_with_target_graph_without_write_permission(
    repo: InMemoryRepository, settings: MCPSettings, permissions: InMemoryPermissionService
) -> None:
    """remember with target_graph without write permission raises PermissionError."""
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)
    # Alice has read but no write
    await permissions.grant("alice", SHARED_SCHEMA, can_read=True, can_write=False, granted_by=BOOTSTRAP_ADMIN)

    router = _make_router_mock(permissions)
    ctx = MagicMock()
    ctx.lifespan_context = {
        "repo": repo,
        "settings": settings,
        "embeddings": None,
        "job_app": None,
        "router": router,
        "permissions": permissions,
    }

    with patch("neocortex.tools.remember.get_agent_id_from_context", return_value="alice"):
        from neocortex.tools.remember import remember

        with pytest.raises(PermissionError, match="does not have write access"):
            await remember("Shared knowledge fact", target_graph=SHARED_SCHEMA, ctx=ctx)


@pytest.mark.asyncio
async def test_remember_without_target_graph_stores_personal(repo: InMemoryRepository, settings: MCPSettings) -> None:
    """remember without target_graph stores in personal graph (unchanged behavior)."""
    ctx = MagicMock()
    ctx.lifespan_context = {
        "repo": repo,
        "settings": settings,
        "embeddings": None,
        "job_app": None,
    }

    with patch("neocortex.tools.remember.get_agent_id_from_context", return_value="alice"):
        from neocortex.tools.remember import remember

        result = await remember("Personal memory", ctx=ctx)

    assert isinstance(result, RememberResult)
    assert result.status == "stored"
    assert result.episode_id > 0
    # No schema-bucketed episodes for personal store
    assert len(repo._schema_episodes) == 0
    # Episode stored in main list
    assert len(repo._episodes) == 1
    assert repo._episodes[0]["content"] == "Personal memory"
