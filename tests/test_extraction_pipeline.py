"""Tests for the extraction pipeline (Stage 4, Plan 07).

Tests run against InMemoryRepository with pydantic_ai TestModel — no Docker
or API keys needed.
"""

from __future__ import annotations

import pytest

from neocortex.db.mock import InMemoryRepository
from neocortex.extraction.pipeline import _persist_payload, run_extraction
from neocortex.extraction.schemas import (
    LibrarianPayload,
    NormalizedEntity,
    NormalizedRelation,
    ProposedEdgeType,
    ProposedNodeType,
)

AGENT = "test-agent"


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


def _sample_payload() -> LibrarianPayload:
    """Build a realistic librarian payload for testing persistence."""
    return LibrarianPayload(
        accepted_node_types=[
            ProposedNodeType(name="Neurotransmitter", description="A chemical messenger"),
            ProposedNodeType(name="Drug", description="A pharmaceutical substance"),
        ],
        accepted_edge_types=[
            ProposedEdgeType(name="INHIBITS", description="Blocks or reduces activity"),
            ProposedEdgeType(name="TREATS", description="Therapeutic relationship"),
        ],
        entities=[
            NormalizedEntity(
                name="Serotonin",
                type_name="Neurotransmitter",
                description="A monoamine neurotransmitter involved in mood regulation",
                properties={"alternate_name": "5-HT"},
                is_new=True,
            ),
            NormalizedEntity(
                name="Fluoxetine",
                type_name="Drug",
                description="A selective serotonin reuptake inhibitor (SSRI)",
                properties={"brand_name": "Prozac"},
                is_new=True,
            ),
        ],
        relations=[
            NormalizedRelation(
                source_name="Fluoxetine",
                target_name="Serotonin",
                relation_type="INHIBITS",
                weight=0.9,
                properties={"evidence": "blocks reuptake"},
            ),
        ],
        summary="Extracted neurotransmitter-drug relationships",
    )


# ── _persist_payload tests ──


@pytest.mark.asyncio
async def test_persist_payload_creates_types(repo: InMemoryRepository) -> None:
    """Verify that accepted types from payload are persisted."""
    eid = await repo.store_episode(AGENT, "test content")
    payload = _sample_payload()

    await _persist_payload(repo, None, AGENT, eid, payload)

    node_types = await repo.get_node_types(AGENT)
    edge_types = await repo.get_edge_types(AGENT)
    nt_names = {t.name for t in node_types}
    et_names = {t.name for t in edge_types}
    assert "Neurotransmitter" in nt_names
    assert "Drug" in nt_names
    assert "INHIBITS" in et_names
    assert "TREATS" in et_names


@pytest.mark.asyncio
async def test_persist_payload_creates_nodes(repo: InMemoryRepository) -> None:
    """Verify that entities are persisted as nodes."""
    eid = await repo.store_episode(AGENT, "test content")
    payload = _sample_payload()

    await _persist_payload(repo, None, AGENT, eid, payload)

    serotonin = await repo.find_nodes_by_name(AGENT, "Serotonin")
    assert len(serotonin) == 1
    assert serotonin[0].name == "Serotonin"
    assert serotonin[0].properties["alternate_name"] == "5-HT"
    assert serotonin[0].properties["_source_episode"] == eid

    fluoxetine = await repo.find_nodes_by_name(AGENT, "Fluoxetine")
    assert len(fluoxetine) == 1
    assert fluoxetine[0].properties["brand_name"] == "Prozac"


@pytest.mark.asyncio
async def test_persist_payload_creates_edges(repo: InMemoryRepository) -> None:
    """Verify that relations are persisted as edges."""
    eid = await repo.store_episode(AGENT, "test content")
    payload = _sample_payload()

    await _persist_payload(repo, None, AGENT, eid, payload)

    sigs = await repo.list_all_edge_signatures(AGENT)
    assert len(sigs) == 1
    assert "Fluoxetine" in sigs[0]
    assert "Serotonin" in sigs[0]


@pytest.mark.asyncio
async def test_persist_payload_skips_edge_with_missing_node(
    repo: InMemoryRepository,
) -> None:
    """Edges referencing non-existent nodes should be skipped, not crash."""
    eid = await repo.store_episode(AGENT, "test content")
    payload = LibrarianPayload(
        entities=[
            NormalizedEntity(name="Alpha", type_name="TypeA"),
        ],
        relations=[
            NormalizedRelation(
                source_name="Alpha",
                target_name="NonExistent",
                relation_type="LINKS_TO",
            ),
        ],
    )

    # Should not raise
    await _persist_payload(repo, None, AGENT, eid, payload)

    sigs = await repo.list_all_edge_signatures(AGENT)
    assert len(sigs) == 0  # edge skipped


@pytest.mark.asyncio
async def test_persist_payload_idempotent_nodes(repo: InMemoryRepository) -> None:
    """Running persist twice with same payload should not duplicate nodes."""
    eid = await repo.store_episode(AGENT, "test content")
    payload = _sample_payload()

    await _persist_payload(repo, None, AGENT, eid, payload)
    await _persist_payload(repo, None, AGENT, eid, payload)

    serotonin = await repo.find_nodes_by_name(AGENT, "Serotonin")
    assert len(serotonin) == 1  # not duplicated

    fluoxetine = await repo.find_nodes_by_name(AGENT, "Fluoxetine")
    assert len(fluoxetine) == 1


@pytest.mark.asyncio
async def test_persist_payload_idempotent_edges(repo: InMemoryRepository) -> None:
    """Running persist twice should not create duplicate edges."""
    eid = await repo.store_episode(AGENT, "test content")
    payload = _sample_payload()

    await _persist_payload(repo, None, AGENT, eid, payload)
    await _persist_payload(repo, None, AGENT, eid, payload)

    sigs = await repo.list_all_edge_signatures(AGENT)
    assert len(sigs) == 1


@pytest.mark.asyncio
async def test_persist_payload_resolves_existing_nodes_for_edges(
    repo: InMemoryRepository,
) -> None:
    """Edges referencing nodes created in a prior run should resolve."""
    eid = await repo.store_episode(AGENT, "test content")

    # First payload creates Serotonin node
    payload1 = LibrarianPayload(
        entities=[
            NormalizedEntity(
                name="Serotonin", type_name="Neurotransmitter", description="5-HT"
            ),
        ],
    )
    await _persist_payload(repo, None, AGENT, eid, payload1)

    # Second payload creates Dopamine and links to existing Serotonin
    payload2 = LibrarianPayload(
        entities=[
            NormalizedEntity(
                name="Dopamine", type_name="Neurotransmitter", description="DA"
            ),
        ],
        relations=[
            NormalizedRelation(
                source_name="Dopamine",
                target_name="Serotonin",
                relation_type="INTERACTS_WITH",
            ),
        ],
    )
    await _persist_payload(repo, None, AGENT, eid, payload2)

    sigs = await repo.list_all_edge_signatures(AGENT)
    assert len(sigs) == 1
    assert "Dopamine" in sigs[0]
    assert "Serotonin" in sigs[0]


# ── Full pipeline tests with TestModel ──


@pytest.mark.asyncio
async def test_run_extraction_with_test_model(repo: InMemoryRepository) -> None:
    """Full pipeline with TestModel: verify it runs without errors."""
    eid = await repo.store_episode(
        AGENT,
        "Serotonin is a monoamine neurotransmitter that modulates mood.",
    )

    await run_extraction(
        repo=repo,
        embeddings=None,
        agent_id=AGENT,
        episode_ids=[eid],
        use_test_model=True,
    )

    # TestModel produces structurally valid output — verify flow completed
    # (specific node/edge counts depend on TestModel's generated data)
    stats = await repo.get_stats(AGENT)
    # At minimum, the pipeline ran without error. TestModel may produce
    # empty or populated lists, so we just verify the flow is sound.
    assert stats.total_episodes == 1


@pytest.mark.asyncio
async def test_run_extraction_skips_missing_episode(
    repo: InMemoryRepository,
) -> None:
    """Pipeline should skip episode IDs that don't exist."""
    await run_extraction(
        repo=repo,
        embeddings=None,
        agent_id=AGENT,
        episode_ids=[9999],
        use_test_model=True,
    )

    stats = await repo.get_stats(AGENT)
    assert stats.total_nodes == 0
    assert stats.total_edges == 0


@pytest.mark.asyncio
async def test_run_extraction_multiple_episodes(repo: InMemoryRepository) -> None:
    """Pipeline processes multiple episodes sequentially."""
    eid1 = await repo.store_episode(AGENT, "Text about serotonin.")
    eid2 = await repo.store_episode(AGENT, "Text about dopamine.")

    await run_extraction(
        repo=repo,
        embeddings=None,
        agent_id=AGENT,
        episode_ids=[eid1, eid2],
        use_test_model=True,
    )

    stats = await repo.get_stats(AGENT)
    assert stats.total_episodes == 2
