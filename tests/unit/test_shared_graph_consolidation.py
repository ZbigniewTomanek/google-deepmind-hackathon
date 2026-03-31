"""Tests for shared graph consolidation fixes (Plan 23).

Covers: cross-agent upsert, UPDATE-zero-rows fallback, tool_calls_limit
configuration, and recall type resolution.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neocortex.db.mock import InMemoryRepository
from neocortex.mcp_settings import MCPSettings

# ── Cross-agent upsert ──


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.mark.asyncio
async def test_cross_agent_upsert(repo: InMemoryRepository) -> None:
    """Agent A creates a node, Agent B upserts same name — single node, B's content wins."""
    # Register a node type
    nt = await repo.get_or_create_node_type("alice", "Concept", "A general concept")

    # Agent A creates "Python"
    node_a = await repo.upsert_node(
        agent_id="alice",
        name="Python",
        type_id=nt.id,
        content="A programming language",
    )
    assert node_a.content == "A programming language"

    # Agent B upserts the same node with updated content
    node_b = await repo.upsert_node(
        agent_id="bob",
        name="Python",
        type_id=nt.id,
        content="A versatile programming language used in ML",
    )

    # Should be the same node (dedup by name)
    assert node_b.id == node_a.id
    # B's content replaces A's (librarian is expected to merge before calling upsert)
    assert node_b.content == "A versatile programming language used in ML"

    # Only one node with this name exists
    nodes = await repo.find_nodes_by_name("bob", "Python")
    assert len(nodes) == 1


@pytest.mark.asyncio
async def test_cross_agent_upsert_preserves_properties(repo: InMemoryRepository) -> None:
    """Cross-agent upsert merges properties from both agents."""
    nt = await repo.get_or_create_node_type("alice", "Technology", "A technology")

    await repo.upsert_node(
        agent_id="alice",
        name="PostgreSQL",
        type_id=nt.id,
        content="Relational database",
        properties={"license": "PostgreSQL License"},
    )

    node = await repo.upsert_node(
        agent_id="bob",
        name="PostgreSQL",
        type_id=nt.id,
        content="Advanced relational database",
        properties={"version": "16"},
    )

    # Properties from both agents are merged
    assert node.properties["license"] == "PostgreSQL License"
    assert node.properties["version"] == "16"


# ── UPDATE zero-rows fallback (adapter behavior) ──


@pytest.mark.asyncio
async def test_adapter_update_zero_rows_falls_through_to_insert() -> None:
    """When UPDATE returns None (0 rows), adapter falls through to INSERT instead of crashing.

    This tests the adapter's SQL-level fallback path using a mocked connection.
    """
    from neocortex.db.adapter import GraphServiceAdapter

    mock_graph = MagicMock()
    adapter = GraphServiceAdapter.__new__(GraphServiceAdapter)
    adapter._graph = mock_graph
    adapter._pool = MagicMock()
    adapter._router = MagicMock()

    # Mock _resolve_schema and _scoped_conn
    adapter._resolve_schema = AsyncMock(return_value="ncx_shared__test")

    mock_conn = AsyncMock()
    # Phase 1: Name lookup finds existing node
    mock_conn.fetch = AsyncMock(
        return_value=[
            {
                "id": 42,
                "type_id": 1,
                "name": "Python",
                "content": "old content",
                "properties": "{}",
                "source": "test",
                "importance": 0.5,
                "forgotten": False,
                "created_at": None,
                "updated_at": None,
            }
        ]
    )
    # UPDATE returns None (0 rows matched — concurrent delete or RLS artifact)
    mock_conn.fetchrow = AsyncMock(return_value=None)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_scoped_conn(schema, agent_id, target_schema):
        yield mock_conn

    adapter._scoped_conn = fake_scoped_conn

    # Should NOT raise RuntimeError — falls through to INSERT
    # The INSERT also returns None in this mock, so it will raise "Failed to create node"
    # We need the INSERT to succeed
    now = datetime.now(UTC)
    insert_row = {
        "id": 99,
        "type_id": 1,
        "name": "Python",
        "content": "new content",
        "properties": "{}",
        "source": "test",
        "importance": 0.5,
        "access_count": 0,
        "last_accessed_at": None,
        "forgotten": False,
        "forgotten_at": None,
        "created_at": now,
        "updated_at": now,
    }

    call_count = 0

    async def fetchrow_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: UPDATE returns None (0 rows)
            return None
        # Second call: INSERT succeeds
        return insert_row

    mock_conn.fetchrow = AsyncMock(side_effect=fetchrow_side_effect)

    node = await adapter.upsert_node(
        agent_id="bob",
        name="Python",
        type_id=1,
        content="new content",
        target_schema="ncx_shared__test",
    )

    assert node.id == 99
    assert node.name == "Python"
    assert call_count == 2  # UPDATE failed, then INSERT succeeded


# ── tool_calls_limit configuration ──


def test_extraction_tool_calls_limit_default() -> None:
    """extraction_tool_calls_limit defaults to 150."""
    settings = MCPSettings(mock_db=True)
    assert settings.extraction_tool_calls_limit == 150


def test_extraction_tool_calls_limit_override() -> None:
    """extraction_tool_calls_limit can be overridden via env var."""
    with patch.dict(os.environ, {"NEOCORTEX_EXTRACTION_TOOL_CALLS_LIMIT": "200"}):
        settings = MCPSettings(mock_db=True)
        assert settings.extraction_tool_calls_limit == 200


# ── Recall type resolution ──


@pytest.mark.asyncio
async def test_recall_returns_node_type(repo: InMemoryRepository) -> None:
    """Recall returns a type identifier for nodes (not 'Unknown').

    Note: InMemoryRepository returns 'Node' as item_type for all nodes
    (it doesn't resolve to the specific NodeType name like the PG adapter does).
    The PG adapter's JOIN-based resolution (Stage 5) is verified by the
    integration tests in test_rls.py. This test ensures the mock at least
    returns a non-empty, non-'Unknown' type.
    """
    nt = await repo.get_or_create_node_type("alice", "Programming_Language", "A programming language")
    await repo.upsert_node(
        agent_id="alice",
        name="Python",
        type_id=nt.id,
        content="A versatile programming language",
    )

    results = await repo.recall("Python", agent_id="alice")
    assert len(results) >= 1

    node_result = next(r for r in results if r.source_kind == "node")
    assert node_result.item_type != "Unknown"
    assert node_result.item_type  # not empty


@pytest.mark.asyncio
async def test_recall_episode_type_is_episode(repo: InMemoryRepository) -> None:
    """Recall returns 'Episode' as item_type for episodes."""
    await repo.store_episode("alice", "Python is great for ML")

    results = await repo.recall("Python", agent_id="alice")
    assert len(results) >= 1

    ep_result = next(r for r in results if r.source_kind == "episode")
    assert ep_result.item_type == "Episode"
