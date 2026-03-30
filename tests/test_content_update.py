"""Tests for node content update semantics on upsert.

Verifies that:
- Content is updated when new content is provided
- Content is preserved when new content is None
- Empty string content overwrites existing (matches SQL COALESCE semantics)

All tests run against InMemoryRepository — no Docker needed.
"""

from __future__ import annotations

import pytest

from neocortex.db.mock import InMemoryRepository

AGENT = "test-agent"


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.mark.asyncio
async def test_content_updates_on_upsert(repo: InMemoryRepository) -> None:
    """Content should reflect the latest value when a new description is provided."""
    nt = await repo.get_or_create_node_type(AGENT, "Person")

    # Create node with initial content
    node1 = await repo.upsert_node(AGENT, "Alice", nt.id, content="Alice is on billing team")
    assert node1.content == "Alice is on billing team"

    # Upsert same node with updated content
    node2 = await repo.upsert_node(AGENT, "Alice", nt.id, content="Alice is on auth team")
    assert node2.id == node1.id, "Should update existing node, not create new"
    assert node2.content == "Alice is on auth team"


@pytest.mark.asyncio
async def test_content_preserved_when_none(repo: InMemoryRepository) -> None:
    """Content should be preserved when upsert provides content=None."""
    nt = await repo.get_or_create_node_type(AGENT, "Person")

    # Create node with initial content
    node1 = await repo.upsert_node(AGENT, "Alice", nt.id, content="Alice is on auth team")
    assert node1.content == "Alice is on auth team"

    # Upsert same node with content=None (should keep old)
    node2 = await repo.upsert_node(AGENT, "Alice", nt.id, content=None)
    assert node2.id == node1.id
    assert node2.content == "Alice is on auth team", "Content should be preserved when new is None"


@pytest.mark.asyncio
async def test_empty_string_content_overwrites(repo: InMemoryRepository) -> None:
    """Empty string is a valid value (not None), should overwrite existing content.

    This matches PostgreSQL COALESCE semantics: COALESCE('', old) = ''.
    """
    nt = await repo.get_or_create_node_type(AGENT, "Person")

    node1 = await repo.upsert_node(AGENT, "Alice", nt.id, content="Alice is on auth team")
    assert node1.content == "Alice is on auth team"

    # Empty string is non-None, should overwrite
    node2 = await repo.upsert_node(AGENT, "Alice", nt.id, content="")
    assert node2.id == node1.id
    assert node2.content == "", "Empty string should overwrite existing content"


@pytest.mark.asyncio
async def test_content_update_case_insensitive_match(repo: InMemoryRepository) -> None:
    """Upsert should match existing nodes case-insensitively."""
    nt = await repo.get_or_create_node_type(AGENT, "Person")

    node1 = await repo.upsert_node(AGENT, "Alice", nt.id, content="Original description")
    node2 = await repo.upsert_node(AGENT, "alice", nt.id, content="Updated description")

    assert node2.id == node1.id, "Case-insensitive match should find existing node"
    assert node2.content == "Updated description"


@pytest.mark.asyncio
async def test_multiple_content_updates(repo: InMemoryRepository) -> None:
    """Content should track through multiple sequential updates."""
    nt = await repo.get_or_create_node_type(AGENT, "Person")

    node = await repo.upsert_node(AGENT, "Alice", nt.id, content="v1")
    assert node.content == "v1"

    node = await repo.upsert_node(AGENT, "Alice", nt.id, content="v2")
    assert node.content == "v2"

    node = await repo.upsert_node(AGENT, "Alice", nt.id, content=None)
    assert node.content == "v2", "None should not overwrite"

    node = await repo.upsert_node(AGENT, "Alice", nt.id, content="v3")
    assert node.content == "v3"
