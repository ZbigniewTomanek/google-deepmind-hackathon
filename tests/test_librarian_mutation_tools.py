"""Tests for librarian mutation tools and tool-driven curation (Stage 3, Plan 16).

Tests verify:
- 4 mutation tools are registered on the tool-equipped librarian agent
- Mutation tools work against InMemoryRepository
- CurationSummary validator computes counts from actions
- cleanup_partial_curation removes tagged nodes/edges
- Pipeline uses tool-driven curation by default
- Pipeline falls back to _persist_payload when librarian_use_tools=False
- delete_edge works in mock repo
"""

from __future__ import annotations

import pytest

from neocortex.db.mock import InMemoryRepository
from neocortex.extraction.agents import (
    AgentInferenceConfig,
    LibrarianAgentDeps,
    build_librarian_agent,
)
from neocortex.extraction.schemas import (
    CurationAction,
    CurationSummary,
    ExtractedEntity,
    ExtractedRelation,
)

AGENT = "test-agent"
_TEST_CONFIG = AgentInferenceConfig(use_test_model=True)


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


def _make_deps(
    repo: InMemoryRepository,
    episode_id: int | None = None,
) -> LibrarianAgentDeps:
    """Build minimal librarian deps for testing."""
    return LibrarianAgentDeps(
        episode_text="Alice works on billing.",
        node_types=["Person", "Service"],
        edge_types=["WORKS_ON"],
        extracted_entities=[
            ExtractedEntity(name="Alice", type_name="Person", description="A person"),
        ],
        extracted_relations=[
            ExtractedRelation(
                source_name="Alice",
                target_name="Billing",
                relation_type="WORKS_ON",
            ),
        ],
        repo=repo,
        embeddings=None,
        agent_id=AGENT,
        episode_id=episode_id,
    )


# ── Tool registration tests ──


def test_tool_equipped_librarian_has_8_tools() -> None:
    """Tool-equipped librarian has 4 retrieval + 4 mutation = 8 tools."""
    agent = build_librarian_agent(_TEST_CONFIG, use_tools=True)
    tool_names = sorted(agent._function_toolset.tools.keys())
    assert "create_or_update_node" in tool_names
    assert "create_or_update_edge" in tool_names
    assert "archive_node" in tool_names
    assert "remove_edge" in tool_names
    assert "search_existing_nodes" in tool_names
    assert "find_node_by_name" in tool_names
    assert "inspect_node_neighborhood" in tool_names
    assert "get_edges_between" in tool_names
    assert "find_similar_nodes" in tool_names
    assert len(tool_names) == 9


def test_fallback_librarian_has_5_tools() -> None:
    """Non-tool librarian has only 5 retrieval tools, no mutation tools."""
    agent = build_librarian_agent(_TEST_CONFIG, use_tools=False)
    tool_names = sorted(agent._function_toolset.tools.keys())
    assert "create_or_update_node" not in tool_names
    assert "create_or_update_edge" not in tool_names
    assert "archive_node" not in tool_names
    assert "remove_edge" not in tool_names
    assert len(tool_names) == 5


# ── CurationSummary tests ──


def test_curation_summary_computes_counts_from_actions() -> None:
    """CurationSummary validator derives counts from actions list."""
    summary = CurationSummary(
        actions=[
            CurationAction(action="created_node", entity_name="Alice"),
            CurationAction(action="created_node", entity_name="Bob"),
            CurationAction(action="updated_node", entity_name="Charlie"),
            CurationAction(action="archived_node", entity_name="Dave"),
            CurationAction(action="created_edge", edge_source="Alice", edge_target="Bob"),
            CurationAction(action="removed_edge", edge_source="Charlie", edge_target="Dave"),
            CurationAction(action="removed_edge", edge_source="Eve", edge_target="Frank"),
        ],
        summary="Test summary",
    )
    assert summary.entities_created == 2
    assert summary.entities_updated == 1
    assert summary.entities_archived == 1
    assert summary.edges_created == 1
    assert summary.edges_removed == 2


def test_curation_summary_empty_actions() -> None:
    """CurationSummary with no actions has all zero counts."""
    summary = CurationSummary(summary="Nothing done")
    assert summary.entities_created == 0
    assert summary.entities_updated == 0
    assert summary.entities_archived == 0
    assert summary.edges_created == 0
    assert summary.edges_removed == 0


def test_curation_summary_overrides_manual_counts() -> None:
    """Validator recomputes counts even if LLM provides them explicitly."""
    summary = CurationSummary(
        actions=[
            CurationAction(action="created_node", entity_name="Alice"),
        ],
        entities_created=99,  # LLM got it wrong
    )
    assert summary.entities_created == 1  # validator corrected it


# ── delete_edge tests ──


@pytest.mark.asyncio
async def test_delete_edge_removes_edge(repo: InMemoryRepository) -> None:
    """delete_edge removes an existing edge and returns True."""
    nt = await repo.get_or_create_node_type(AGENT, "Person")
    et = await repo.get_or_create_edge_type(AGENT, "KNOWS")
    alice = await repo.upsert_node(AGENT, "Alice", nt.id)
    bob = await repo.upsert_node(AGENT, "Bob", nt.id)
    edge = await repo.upsert_edge(AGENT, alice.id, bob.id, et.id)

    result = await repo.delete_edge(AGENT, edge.id)
    assert result is True

    # Edge should be gone
    sigs = await repo.list_all_edge_signatures(AGENT)
    assert len(sigs) == 0


@pytest.mark.asyncio
async def test_delete_edge_nonexistent_returns_false(repo: InMemoryRepository) -> None:
    """delete_edge returns False for non-existent edge."""
    result = await repo.delete_edge(AGENT, 9999)
    assert result is False


# ── cleanup_partial_curation tests ──


@pytest.mark.asyncio
async def test_cleanup_partial_curation_removes_tagged_items(repo: InMemoryRepository) -> None:
    """cleanup_partial_curation deletes nodes/edges tagged with episode_id."""
    nt = await repo.get_or_create_node_type(AGENT, "Person")
    et = await repo.get_or_create_edge_type(AGENT, "KNOWS")

    # Create items tagged with episode 42
    alice = await repo.upsert_node(
        AGENT,
        "Alice",
        nt.id,
        properties={"_source_episode": 42},
    )
    bob = await repo.upsert_node(
        AGENT,
        "Bob",
        nt.id,
        properties={"_source_episode": 42},
    )
    await repo.upsert_edge(
        AGENT,
        alice.id,
        bob.id,
        et.id,
        properties={"_source_episode": 42},
    )

    # Create an unrelated item (episode 99) that should NOT be deleted
    await repo.upsert_node(
        AGENT,
        "Charlie",
        nt.id,
        properties={"_source_episode": 99},
    )

    deleted = await repo.cleanup_partial_curation(AGENT, 42)
    assert deleted == 3  # 2 nodes + 1 edge

    # Charlie should still exist
    charlie = await repo.find_nodes_by_name(AGENT, "Charlie")
    assert len(charlie) == 1

    # Alice and Bob should be gone
    alice_nodes = await repo.find_nodes_by_name(AGENT, "Alice")
    assert len(alice_nodes) == 0


@pytest.mark.asyncio
async def test_cleanup_partial_curation_no_matches(repo: InMemoryRepository) -> None:
    """cleanup_partial_curation returns 0 when nothing matches."""
    deleted = await repo.cleanup_partial_curation(AGENT, 999)
    assert deleted == 0


@pytest.mark.asyncio
async def test_retry_after_partial_failure(repo: InMemoryRepository) -> None:
    """Simulates partial curation failure and successful retry."""
    nt = await repo.get_or_create_node_type(AGENT, "Person")

    # Simulate partial curation: one node was created before failure
    await repo.upsert_node(
        AGENT,
        "Alice",
        nt.id,
        content="Partial",
        properties={"_source_episode": 10},
    )

    # Cleanup before retry
    deleted = await repo.cleanup_partial_curation(AGENT, 10)
    assert deleted == 1

    # Retry: create again cleanly
    await repo.upsert_node(
        AGENT,
        "Alice",
        nt.id,
        content="Complete",
        properties={"_source_episode": 10},
    )

    alice = await repo.find_nodes_by_name(AGENT, "Alice")
    assert len(alice) == 1
    assert alice[0].content == "Complete"


# ── Pipeline integration tests ──


@pytest.mark.asyncio
async def test_pipeline_tool_mode_does_not_call_persist_payload(repo: InMemoryRepository) -> None:
    """In tool mode, pipeline should NOT call _persist_payload."""
    from unittest.mock import AsyncMock, patch

    from neocortex.extraction.pipeline import _persist_payload, run_extraction

    eid = await repo.store_episode(AGENT, "Alice works on billing.")

    persist_spy = AsyncMock(side_effect=_persist_payload)

    with patch("neocortex.extraction.pipeline._persist_payload", persist_spy):
        await run_extraction(
            repo=repo,
            embeddings=None,
            agent_id=AGENT,
            episode_ids=[eid],
            ontology_config=_TEST_CONFIG,
            extractor_config=_TEST_CONFIG,
            librarian_config=_TEST_CONFIG,
            librarian_use_tools=True,
        )

    persist_spy.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_fallback_mode_calls_persist_payload(repo: InMemoryRepository) -> None:
    """When librarian_use_tools=False, pipeline uses _persist_payload."""
    from unittest.mock import AsyncMock, patch

    from neocortex.extraction.pipeline import _persist_payload, run_extraction

    eid = await repo.store_episode(AGENT, "Alice works on billing.")

    persist_spy = AsyncMock(side_effect=_persist_payload)

    with patch("neocortex.extraction.pipeline._persist_payload", persist_spy):
        await run_extraction(
            repo=repo,
            embeddings=None,
            agent_id=AGENT,
            episode_ids=[eid],
            ontology_config=_TEST_CONFIG,
            extractor_config=_TEST_CONFIG,
            librarian_config=_TEST_CONFIG,
            librarian_use_tools=False,
        )

    persist_spy.assert_called_once()


@pytest.mark.asyncio
async def test_pipeline_skips_cleanup_before_curation(repo: InMemoryRepository) -> None:
    """Pipeline does NOT call cleanup_partial_curation — upsert semantics make it unnecessary."""
    from unittest.mock import AsyncMock

    from neocortex.extraction.pipeline import run_extraction

    eid = await repo.store_episode(AGENT, "Alice works on billing.")

    cleanup_spy = AsyncMock(return_value=0)
    repo.cleanup_partial_curation = cleanup_spy  # type: ignore[method-assign]  # ty: ignore[invalid-assignment]

    await run_extraction(
        repo=repo,
        embeddings=None,
        agent_id=AGENT,
        episode_ids=[eid],
        ontology_config=_TEST_CONFIG,
        extractor_config=_TEST_CONFIG,
        librarian_config=_TEST_CONFIG,
        librarian_use_tools=True,
    )

    cleanup_spy.assert_not_called()


@pytest.mark.asyncio
async def test_full_pipeline_tool_mode_with_test_model(repo: InMemoryRepository) -> None:
    """Full pipeline in tool mode runs without errors using TestModel."""
    from neocortex.extraction.pipeline import run_extraction

    eid = await repo.store_episode(
        AGENT,
        "Alice is an engineer who works on the billing service.",
    )

    await run_extraction(
        repo=repo,
        embeddings=None,
        agent_id=AGENT,
        episode_ids=[eid],
        ontology_config=_TEST_CONFIG,
        extractor_config=_TEST_CONFIG,
        librarian_config=_TEST_CONFIG,
        librarian_use_tools=True,
    )

    stats = await repo.get_stats(AGENT)
    assert stats.total_episodes == 1


@pytest.mark.asyncio
async def test_full_pipeline_fallback_mode_with_test_model(repo: InMemoryRepository) -> None:
    """Full pipeline in fallback mode runs without errors using TestModel."""
    from neocortex.extraction.pipeline import run_extraction

    eid = await repo.store_episode(
        AGENT,
        "Alice is an engineer who works on the billing service.",
    )

    await run_extraction(
        repo=repo,
        embeddings=None,
        agent_id=AGENT,
        episode_ids=[eid],
        ontology_config=_TEST_CONFIG,
        extractor_config=_TEST_CONFIG,
        librarian_config=_TEST_CONFIG,
        librarian_use_tools=False,
    )

    stats = await repo.get_stats(AGENT)
    assert stats.total_episodes == 1


# ── list_all_node_names limit tests ──


@pytest.mark.asyncio
async def test_list_all_node_names_with_limit(repo: InMemoryRepository) -> None:
    """list_all_node_names respects the limit parameter."""
    nt = await repo.get_or_create_node_type(AGENT, "Person")
    for name in ["Alice", "Bob", "Charlie", "Dave", "Eve"]:
        await repo.upsert_node(AGENT, name, nt.id)

    all_names = await repo.list_all_node_names(AGENT)
    assert len(all_names) == 5

    limited = await repo.list_all_node_names(AGENT, limit=3)
    assert len(limited) == 3
