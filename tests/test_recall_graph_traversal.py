"""Tests for enhanced recall with graph traversal (Stage 6, Plan 07).

All tests run against InMemoryRepository — no Docker needed.
"""

from __future__ import annotations

import pytest

from neocortex.db.mock import InMemoryRepository

AGENT = "test-agent"


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


async def _build_small_graph(repo: InMemoryRepository) -> dict:
    """Create a small graph with 5 nodes and 6 edges.

    Graph topology:
        Serotonin --[REGULATES]--> Mood
        Serotonin --[INHIBITED_BY]--> Fluoxetine
        Fluoxetine --[TREATS]--> Depression
        Depression --[AFFECTS]--> Mood
        Fluoxetine --[CAUSES]--> SexualDysfunction
        SexualDysfunction --[AFFECTS]--> Mood
    """
    nt_neuro = await repo.get_or_create_node_type(AGENT, "Neurotransmitter")
    nt_drug = await repo.get_or_create_node_type(AGENT, "Drug")
    nt_condition = await repo.get_or_create_node_type(AGENT, "Condition")
    nt_process = await repo.get_or_create_node_type(AGENT, "BiologicalProcess")

    et_regulates = await repo.get_or_create_edge_type(AGENT, "REGULATES")
    et_inhibited = await repo.get_or_create_edge_type(AGENT, "INHIBITED_BY")
    et_treats = await repo.get_or_create_edge_type(AGENT, "TREATS")
    et_affects = await repo.get_or_create_edge_type(AGENT, "AFFECTS")
    et_causes = await repo.get_or_create_edge_type(AGENT, "CAUSES")

    serotonin = await repo.upsert_node(
        AGENT, "Serotonin", nt_neuro.id, content="A monoamine neurotransmitter"
    )
    mood = await repo.upsert_node(
        AGENT, "Mood Regulation", nt_process.id, content="Biological process of mood control"
    )
    fluoxetine = await repo.upsert_node(
        AGENT, "Fluoxetine", nt_drug.id, content="An SSRI antidepressant"
    )
    depression = await repo.upsert_node(
        AGENT, "Depression", nt_condition.id, content="Major depressive disorder"
    )
    sexual_dysfunction = await repo.upsert_node(
        AGENT, "Sexual Dysfunction", nt_condition.id, content="SSRI-induced sexual side effects"
    )

    await repo.upsert_edge(AGENT, serotonin.id, mood.id, et_regulates.id, weight=0.9)
    await repo.upsert_edge(AGENT, serotonin.id, fluoxetine.id, et_inhibited.id, weight=0.8)
    await repo.upsert_edge(AGENT, fluoxetine.id, depression.id, et_treats.id, weight=0.95)
    await repo.upsert_edge(AGENT, depression.id, mood.id, et_affects.id, weight=0.7)
    await repo.upsert_edge(AGENT, fluoxetine.id, sexual_dysfunction.id, et_causes.id, weight=0.6)
    await repo.upsert_edge(AGENT, sexual_dysfunction.id, mood.id, et_affects.id, weight=0.5)

    return {
        "serotonin": serotonin,
        "mood": mood,
        "fluoxetine": fluoxetine,
        "depression": depression,
        "sexual_dysfunction": sexual_dysfunction,
    }


# ── search_nodes ──


@pytest.mark.asyncio
async def test_search_nodes_by_name(repo: InMemoryRepository) -> None:
    nodes = await _build_small_graph(repo)
    results = await repo.search_nodes(AGENT, "Serotonin")
    assert len(results) == 1
    assert results[0].id == nodes["serotonin"].id


@pytest.mark.asyncio
async def test_search_nodes_by_content(repo: InMemoryRepository) -> None:
    await _build_small_graph(repo)
    results = await repo.search_nodes(AGENT, "antidepressant")
    assert len(results) == 1
    assert results[0].name == "Fluoxetine"


@pytest.mark.asyncio
async def test_search_nodes_empty_query(repo: InMemoryRepository) -> None:
    await _build_small_graph(repo)
    results = await repo.search_nodes(AGENT, "nonexistent_term_xyz")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_search_nodes_limit(repo: InMemoryRepository) -> None:
    await _build_small_graph(repo)
    # "mood" appears in name "Mood Regulation" and content of other nodes
    results = await repo.search_nodes(AGENT, "mood", limit=1)
    assert len(results) <= 1


@pytest.mark.asyncio
async def test_search_nodes_case_insensitive(repo: InMemoryRepository) -> None:
    nodes = await _build_small_graph(repo)
    results = await repo.search_nodes(AGENT, "serotonin")
    assert len(results) == 1
    assert results[0].id == nodes["serotonin"].id


# ── get_node_neighborhood (already tested in Stage 1, but verify depth limiting) ──


@pytest.mark.asyncio
async def test_neighborhood_depth_1(repo: InMemoryRepository) -> None:
    nodes = await _build_small_graph(repo)
    neighborhood = await repo.get_node_neighborhood(AGENT, nodes["serotonin"].id, depth=1)
    neighbor_ids = {entry["node"].id for entry in neighborhood}
    # Serotonin connects directly to Mood and Fluoxetine
    assert nodes["mood"].id in neighbor_ids
    assert nodes["fluoxetine"].id in neighbor_ids
    # Should NOT include Depression or Sexual Dysfunction at depth 1
    assert nodes["depression"].id not in neighbor_ids
    assert nodes["sexual_dysfunction"].id not in neighbor_ids


@pytest.mark.asyncio
async def test_neighborhood_depth_2(repo: InMemoryRepository) -> None:
    nodes = await _build_small_graph(repo)
    neighborhood = await repo.get_node_neighborhood(AGENT, nodes["serotonin"].id, depth=2)
    neighbor_ids = {entry["node"].id for entry in neighborhood}
    # At depth 2, should also reach Depression and Sexual Dysfunction
    assert nodes["depression"].id in neighbor_ids
    assert nodes["sexual_dysfunction"].id in neighbor_ids


@pytest.mark.asyncio
async def test_neighborhood_depth_3_reaches_all(repo: InMemoryRepository) -> None:
    nodes = await _build_small_graph(repo)
    neighborhood = await repo.get_node_neighborhood(AGENT, nodes["serotonin"].id, depth=3)
    # All 4 other nodes should be reachable
    neighbor_ids = {entry["node"].id for entry in neighborhood}
    assert len(neighbor_ids) == 4  # all except serotonin itself


@pytest.mark.asyncio
async def test_neighborhood_includes_distance(repo: InMemoryRepository) -> None:
    nodes = await _build_small_graph(repo)
    neighborhood = await repo.get_node_neighborhood(AGENT, nodes["serotonin"].id, depth=2)
    # Direct neighbors at distance 1
    distance_1 = {entry["node"].id for entry in neighborhood if entry["distance"] == 1}
    distance_2 = {entry["node"].id for entry in neighborhood if entry["distance"] == 2}
    assert nodes["mood"].id in distance_1
    assert nodes["fluoxetine"].id in distance_1
    # Depression and Sexual Dysfunction at distance 2
    assert nodes["depression"].id in distance_2 or nodes["sexual_dysfunction"].id in distance_2


@pytest.mark.asyncio
async def test_neighborhood_includes_edges(repo: InMemoryRepository) -> None:
    nodes = await _build_small_graph(repo)
    neighborhood = await repo.get_node_neighborhood(AGENT, nodes["serotonin"].id, depth=1)
    for entry in neighborhood:
        assert len(entry["edges"]) > 0, "Each neighbor should have at least one connecting edge"


# ── Recall integration with graph context (mock recall + search_nodes) ──


@pytest.mark.asyncio
async def test_recall_returns_episodes(repo: InMemoryRepository) -> None:
    """Basic recall still works with episodes."""
    await repo.store_episode(AGENT, "Serotonin is important for mood regulation")
    results = await repo.recall("Serotonin", AGENT, limit=10)
    assert len(results) >= 1
    assert results[0].source_kind == "episode"


@pytest.mark.asyncio
async def test_search_nodes_multiple_matches(repo: InMemoryRepository) -> None:
    """search_nodes returns multiple matches."""
    await _build_small_graph(repo)
    # Both Depression and Sexual Dysfunction are Condition type
    results = await repo.search_nodes(AGENT, "Dysfunction")
    assert len(results) >= 1
    names = {r.name for r in results}
    assert "Sexual Dysfunction" in names


@pytest.mark.asyncio
async def test_graph_context_structure(repo: InMemoryRepository) -> None:
    """Verify GraphContext can be constructed from neighborhood data."""
    from neocortex.schemas.memory import GraphContext

    nodes = await _build_small_graph(repo)
    neighborhood = await repo.get_node_neighborhood(AGENT, nodes["serotonin"].id, depth=1)

    node_types = await repo.get_node_types(AGENT)
    edge_types = await repo.get_edge_types(AGENT)
    type_name_map = {t.id: t.name for t in node_types}
    edge_type_name_map = {t.id: t.name for t in edge_types}

    center = nodes["serotonin"]
    ctx = GraphContext(
        center_node={
            "id": center.id,
            "name": center.name,
            "type": type_name_map.get(center.type_id, "Unknown"),
            "properties": center.properties,
        },
        edges=[
            {
                "source": entry["edges"][0].source_id,
                "target": entry["edges"][0].target_id,
                "type": edge_type_name_map.get(entry["edges"][0].type_id, "Unknown"),
                "weight": entry["edges"][0].weight,
                "properties": entry["edges"][0].properties,
            }
            for entry in neighborhood
            if entry["edges"]
        ],
        neighbor_nodes=[
            {
                "id": entry["node"].id,
                "name": entry["node"].name,
                "type": type_name_map.get(entry["node"].type_id, "Unknown"),
            }
            for entry in neighborhood
        ],
        depth=1,
    )
    assert ctx.center_node["name"] == "Serotonin"
    assert ctx.center_node["type"] == "Neurotransmitter"
    assert len(ctx.neighbor_nodes) == 2
    assert len(ctx.edges) == 2
    assert ctx.depth == 1


@pytest.mark.asyncio
async def test_recall_item_with_graph_context(repo: InMemoryRepository) -> None:
    """Verify RecallItem can hold graph_context."""
    from neocortex.schemas.memory import GraphContext, RecallItem

    gc = GraphContext(
        center_node={"id": 1, "name": "Test", "type": "Type", "properties": {}},
        edges=[],
        neighbor_nodes=[],
        depth=2,
    )
    item = RecallItem(
        item_id=1,
        name="Test Node",
        content="Test content",
        item_type="TestType",
        score=0.9,
        source_kind="node",
        graph_context=gc,
    )
    assert item.graph_context is not None
    assert item.graph_context.center_node["name"] == "Test"


@pytest.mark.asyncio
async def test_recall_item_without_graph_context(repo: InMemoryRepository) -> None:
    """RecallItem works without graph_context (backward compat)."""
    from neocortex.schemas.memory import RecallItem

    item = RecallItem(
        item_id=1,
        name="Episode #1",
        content="Some content",
        item_type="Episode",
        score=0.8,
        source_kind="episode",
    )
    assert item.graph_context is None
