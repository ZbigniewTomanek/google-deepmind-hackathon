"""Tests for MemoryRepository graph mutation methods (Stage 1, Plan 07).

All tests run against InMemoryRepository — no Docker needed.
"""

from __future__ import annotations

import pytest

from neocortex.db.mock import InMemoryRepository

AGENT = "test-agent"


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


# ── get_episode ──


@pytest.mark.asyncio
async def test_get_episode_returns_stored(repo: InMemoryRepository) -> None:
    eid = await repo.store_episode(AGENT, "hello world", context="test")
    episode = await repo.get_episode(AGENT, eid)
    assert episode is not None
    assert episode.id == eid
    assert episode.content == "hello world"
    assert episode.agent_id == AGENT


@pytest.mark.asyncio
async def test_get_episode_returns_none_for_missing(repo: InMemoryRepository) -> None:
    result = await repo.get_episode(AGENT, 9999)
    assert result is None


@pytest.mark.asyncio
async def test_get_episode_filters_by_agent(repo: InMemoryRepository) -> None:
    eid = await repo.store_episode("other-agent", "secret data")
    result = await repo.get_episode(AGENT, eid)
    assert result is None


# ── get_or_create_node_type ──


@pytest.mark.asyncio
async def test_get_or_create_node_type_creates_new(repo: InMemoryRepository) -> None:
    nt = await repo.get_or_create_node_type(AGENT, "Drug", "A pharmaceutical compound")
    assert nt.name == "Drug"
    assert nt.description == "A pharmaceutical compound"
    assert nt.id > 0


@pytest.mark.asyncio
async def test_get_or_create_node_type_idempotent(repo: InMemoryRepository) -> None:
    nt1 = await repo.get_or_create_node_type(AGENT, "Drug", "desc1")
    nt2 = await repo.get_or_create_node_type(AGENT, "Drug", "desc2")
    assert nt1.id == nt2.id
    assert nt1.name == nt2.name


@pytest.mark.asyncio
async def test_get_or_create_edge_type_creates_new(repo: InMemoryRepository) -> None:
    et = await repo.get_or_create_edge_type(AGENT, "TREATS", "Treatment relation")
    assert et.name == "TREATS"
    assert et.id > 0


@pytest.mark.asyncio
async def test_get_or_create_edge_type_idempotent(repo: InMemoryRepository) -> None:
    et1 = await repo.get_or_create_edge_type(AGENT, "TREATS")
    et2 = await repo.get_or_create_edge_type(AGENT, "TREATS")
    assert et1.id == et2.id


# ── upsert_node ──


@pytest.mark.asyncio
async def test_upsert_node_creates_new(repo: InMemoryRepository) -> None:
    nt = await repo.get_or_create_node_type(AGENT, "Drug")
    node = await repo.upsert_node(AGENT, "Aspirin", nt.id, content="A common painkiller")
    assert node.name == "Aspirin"
    assert node.type_id == nt.id
    assert node.content == "A common painkiller"


@pytest.mark.asyncio
async def test_upsert_node_idempotent_same_name_and_type(repo: InMemoryRepository) -> None:
    nt = await repo.get_or_create_node_type(AGENT, "Drug")
    n1 = await repo.upsert_node(AGENT, "Aspirin", nt.id, properties={"class": "NSAID"})
    n2 = await repo.upsert_node(AGENT, "Aspirin", nt.id, properties={"dosage": "500mg"})
    assert n1.id == n2.id
    # Properties should be merged
    assert n2.properties["class"] == "NSAID"
    assert n2.properties["dosage"] == "500mg"


@pytest.mark.asyncio
async def test_upsert_node_different_types_creates_distinct(repo: InMemoryRepository) -> None:
    nt_drug = await repo.get_or_create_node_type(AGENT, "Drug")
    nt_neuro = await repo.get_or_create_node_type(AGENT, "Neurotransmitter")
    n1 = await repo.upsert_node(AGENT, "Serotonin", nt_drug.id)
    n2 = await repo.upsert_node(AGENT, "Serotonin", nt_neuro.id)
    assert n1.id != n2.id
    assert n1.type_id == nt_drug.id
    assert n2.type_id == nt_neuro.id


# ── find_nodes_by_name ──


@pytest.mark.asyncio
async def test_find_nodes_by_name_empty(repo: InMemoryRepository) -> None:
    result = await repo.find_nodes_by_name(AGENT, "NonExistent")
    assert result == []


@pytest.mark.asyncio
async def test_find_nodes_by_name_single(repo: InMemoryRepository) -> None:
    nt = await repo.get_or_create_node_type(AGENT, "Drug")
    await repo.upsert_node(AGENT, "Aspirin", nt.id)
    result = await repo.find_nodes_by_name(AGENT, "aspirin")  # case-insensitive
    assert len(result) == 1
    assert result[0].name == "Aspirin"


@pytest.mark.asyncio
async def test_find_nodes_by_name_multiple_types(repo: InMemoryRepository) -> None:
    nt_drug = await repo.get_or_create_node_type(AGENT, "Drug")
    nt_neuro = await repo.get_or_create_node_type(AGENT, "Neurotransmitter")
    await repo.upsert_node(AGENT, "Serotonin", nt_drug.id)
    await repo.upsert_node(AGENT, "Serotonin", nt_neuro.id)
    result = await repo.find_nodes_by_name(AGENT, "Serotonin")
    assert len(result) == 2


# ── upsert_edge ──


@pytest.mark.asyncio
async def test_upsert_edge_creates_new(repo: InMemoryRepository) -> None:
    nt = await repo.get_or_create_node_type(AGENT, "Drug")
    et = await repo.get_or_create_edge_type(AGENT, "TREATS")
    n1 = await repo.upsert_node(AGENT, "Aspirin", nt.id)
    n2 = await repo.upsert_node(AGENT, "Headache", nt.id)
    edge = await repo.upsert_edge(AGENT, n1.id, n2.id, et.id, weight=0.9)
    assert edge.source_id == n1.id
    assert edge.target_id == n2.id
    assert edge.weight == 0.9


@pytest.mark.asyncio
async def test_upsert_edge_updates_existing(repo: InMemoryRepository) -> None:
    nt = await repo.get_or_create_node_type(AGENT, "Drug")
    et = await repo.get_or_create_edge_type(AGENT, "TREATS")
    n1 = await repo.upsert_node(AGENT, "Aspirin", nt.id)
    n2 = await repo.upsert_node(AGENT, "Headache", nt.id)
    e1 = await repo.upsert_edge(AGENT, n1.id, n2.id, et.id, weight=0.5, properties={"evidence": "study1"})
    e2 = await repo.upsert_edge(AGENT, n1.id, n2.id, et.id, weight=0.9, properties={"confidence": 0.8})
    assert e1.id == e2.id
    assert e2.weight == 0.9
    assert e2.properties["evidence"] == "study1"
    assert e2.properties["confidence"] == 0.8


# ── get_node_neighborhood ──


@pytest.mark.asyncio
async def test_neighborhood_depth_1(repo: InMemoryRepository) -> None:
    nt = await repo.get_or_create_node_type(AGENT, "Concept")
    et = await repo.get_or_create_edge_type(AGENT, "RELATED_TO")
    a = await repo.upsert_node(AGENT, "A", nt.id)
    b = await repo.upsert_node(AGENT, "B", nt.id)
    c = await repo.upsert_node(AGENT, "C", nt.id)
    await repo.upsert_edge(AGENT, a.id, b.id, et.id)
    await repo.upsert_edge(AGENT, b.id, c.id, et.id)

    neighborhood = await repo.get_node_neighborhood(AGENT, a.id, depth=1)
    names = {item["node"].name for item in neighborhood}
    assert names == {"B"}
    assert all(item["distance"] == 1 for item in neighborhood)


@pytest.mark.asyncio
async def test_neighborhood_depth_2(repo: InMemoryRepository) -> None:
    nt = await repo.get_or_create_node_type(AGENT, "Concept")
    et = await repo.get_or_create_edge_type(AGENT, "RELATED_TO")
    a = await repo.upsert_node(AGENT, "A", nt.id)
    b = await repo.upsert_node(AGENT, "B", nt.id)
    c = await repo.upsert_node(AGENT, "C", nt.id)
    await repo.upsert_edge(AGENT, a.id, b.id, et.id)
    await repo.upsert_edge(AGENT, b.id, c.id, et.id)

    neighborhood = await repo.get_node_neighborhood(AGENT, a.id, depth=2)
    names = {item["node"].name for item in neighborhood}
    assert names == {"B", "C"}
    distances = {item["node"].name: item["distance"] for item in neighborhood}
    assert distances["B"] == 1
    assert distances["C"] == 2


@pytest.mark.asyncio
async def test_neighborhood_depth_3_with_star_graph(repo: InMemoryRepository) -> None:
    nt = await repo.get_or_create_node_type(AGENT, "Concept")
    et = await repo.get_or_create_edge_type(AGENT, "CONNECTED")
    center = await repo.upsert_node(AGENT, "Center", nt.id)
    leaves = []
    for i in range(4):
        leaf = await repo.upsert_node(AGENT, f"Leaf{i}", nt.id)
        leaves.append(leaf)
        await repo.upsert_edge(AGENT, center.id, leaf.id, et.id)

    # Add a chain from Leaf0 → Far1 → Far2
    far1 = await repo.upsert_node(AGENT, "Far1", nt.id)
    far2 = await repo.upsert_node(AGENT, "Far2", nt.id)
    await repo.upsert_edge(AGENT, leaves[0].id, far1.id, et.id)
    await repo.upsert_edge(AGENT, far1.id, far2.id, et.id)

    neighborhood = await repo.get_node_neighborhood(AGENT, center.id, depth=3)
    names = {item["node"].name for item in neighborhood}
    assert "Leaf0" in names
    assert "Far1" in names
    assert "Far2" in names
    assert len(names) == 6  # 4 leaves + Far1 + Far2


# ── list_all_node_names / list_all_edge_signatures ──


@pytest.mark.asyncio
async def test_list_all_node_names(repo: InMemoryRepository) -> None:
    nt = await repo.get_or_create_node_type(AGENT, "Drug")
    await repo.upsert_node(AGENT, "Aspirin", nt.id)
    await repo.upsert_node(AGENT, "Ibuprofen", nt.id)
    names = await repo.list_all_node_names(AGENT)
    assert sorted(names) == ["Aspirin", "Ibuprofen"]


@pytest.mark.asyncio
async def test_list_all_edge_signatures(repo: InMemoryRepository) -> None:
    nt = await repo.get_or_create_node_type(AGENT, "Drug")
    et = await repo.get_or_create_edge_type(AGENT, "TREATS")
    n1 = await repo.upsert_node(AGENT, "Aspirin", nt.id)
    n2 = await repo.upsert_node(AGENT, "Headache", nt.id)
    await repo.upsert_edge(AGENT, n1.id, n2.id, et.id)
    sigs = await repo.list_all_edge_signatures(AGENT)
    assert sigs == ["Aspirin→TREATS→Headache"]


# ── get_node_types / get_edge_types with data ──


@pytest.mark.asyncio
async def test_get_node_types_returns_counts(repo: InMemoryRepository) -> None:
    nt = await repo.get_or_create_node_type(AGENT, "Drug")
    await repo.upsert_node(AGENT, "Aspirin", nt.id)
    await repo.upsert_node(AGENT, "Ibuprofen", nt.id)
    types = await repo.get_node_types(AGENT)
    assert len(types) == 1
    assert types[0].name == "Drug"
    assert types[0].count == 2


@pytest.mark.asyncio
async def test_get_stats_includes_nodes_edges(repo: InMemoryRepository) -> None:
    nt = await repo.get_or_create_node_type(AGENT, "Drug")
    et = await repo.get_or_create_edge_type(AGENT, "TREATS")
    n1 = await repo.upsert_node(AGENT, "Aspirin", nt.id)
    n2 = await repo.upsert_node(AGENT, "Headache", nt.id)
    await repo.upsert_edge(AGENT, n1.id, n2.id, et.id)
    await repo.store_episode(AGENT, "test episode")
    stats = await repo.get_stats(AGENT)
    assert stats.total_nodes == 2
    assert stats.total_edges == 1
    assert stats.total_episodes == 1
