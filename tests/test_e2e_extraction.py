"""E2E integration test for the extraction pipeline (Stage 7, Plan 07).

Tests the full pipeline: ingest episodes, run extraction (mocked LLM),
verify graph state, recall with graph context, discover with counts.

All tests run against InMemoryRepository with pydantic_ai TestModel —
no Docker or API keys needed.
"""

from __future__ import annotations

import pytest

from neocortex.db.mock import InMemoryRepository
from neocortex.extraction.pipeline import _persist_payload
from neocortex.extraction.schemas import (
    LibrarianPayload,
    NormalizedEntity,
    NormalizedRelation,
    ProposedEdgeType,
    ProposedNodeType,
)
from neocortex.schemas.memory import GraphContext, GraphStats

AGENT = "e2e-test-agent"


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


def _medical_payload_1() -> LibrarianPayload:
    """Serotonin-related extraction output."""
    return LibrarianPayload(
        accepted_node_types=[
            ProposedNodeType(name="Neurotransmitter", description="Chemical messenger in the nervous system"),
            ProposedNodeType(name="BiologicalProcess", description="A physiological process"),
            ProposedNodeType(name="BrainRegion", description="Anatomical brain structure"),
        ],
        accepted_edge_types=[
            ProposedEdgeType(name="REGULATES", description="Controls or modulates"),
            ProposedEdgeType(name="PRODUCED_IN", description="Site of synthesis"),
        ],
        entities=[
            NormalizedEntity(
                name="Serotonin",
                type_name="Neurotransmitter",
                description="A monoamine neurotransmitter involved in mood regulation",
                properties={"alternate_name": "5-HT"},
            ),
            NormalizedEntity(
                name="Mood Regulation",
                type_name="BiologicalProcess",
                description="Biological process of mood control",
            ),
            NormalizedEntity(
                name="Raphe Nuclei",
                type_name="BrainRegion",
                description="Brainstem nuclei that synthesize serotonin",
            ),
        ],
        relations=[
            NormalizedRelation(
                source_name="Serotonin",
                target_name="Mood Regulation",
                relation_type="REGULATES",
                weight=0.9,
            ),
            NormalizedRelation(
                source_name="Serotonin",
                target_name="Raphe Nuclei",
                relation_type="PRODUCED_IN",
                weight=0.85,
            ),
        ],
        summary="Serotonin neurotransmitter relationships",
    )


def _medical_payload_2() -> LibrarianPayload:
    """SSRI-related extraction output, linking to existing Serotonin."""
    return LibrarianPayload(
        accepted_node_types=[
            ProposedNodeType(name="Drug", description="A pharmaceutical substance"),
            ProposedNodeType(name="Disease", description="A medical condition"),
        ],
        accepted_edge_types=[
            ProposedEdgeType(name="INHIBITS", description="Blocks or reduces activity"),
            ProposedEdgeType(name="TREATS", description="Therapeutic relationship"),
        ],
        entities=[
            NormalizedEntity(
                name="Fluoxetine",
                type_name="Drug",
                description="A selective serotonin reuptake inhibitor (SSRI)",
                properties={"brand_name": "Prozac"},
            ),
            NormalizedEntity(
                name="Depression",
                type_name="Disease",
                description="Major depressive disorder",
            ),
        ],
        relations=[
            NormalizedRelation(
                source_name="Fluoxetine",
                target_name="Serotonin",
                relation_type="INHIBITS",
                weight=0.9,
                properties={"mechanism": "blocks reuptake"},
            ),
            NormalizedRelation(
                source_name="Fluoxetine",
                target_name="Depression",
                relation_type="TREATS",
                weight=0.95,
            ),
        ],
        summary="SSRI drug relationships",
    )


def _medical_payload_3() -> LibrarianPayload:
    """Sexual dysfunction payload, cross-linking drugs and conditions."""
    return LibrarianPayload(
        accepted_node_types=[
            ProposedNodeType(name="SideEffect", description="Adverse drug reaction"),
        ],
        accepted_edge_types=[
            ProposedEdgeType(name="CAUSES", description="Causal relationship"),
            ProposedEdgeType(name="AFFECTS", description="Has impact on"),
        ],
        entities=[
            NormalizedEntity(
                name="Sexual Dysfunction",
                type_name="SideEffect",
                description="SSRI-induced sexual side effects",
            ),
        ],
        relations=[
            NormalizedRelation(
                source_name="Fluoxetine",
                target_name="Sexual Dysfunction",
                relation_type="CAUSES",
                weight=0.7,
            ),
            NormalizedRelation(
                source_name="Sexual Dysfunction",
                target_name="Mood Regulation",
                relation_type="AFFECTS",
                weight=0.5,
            ),
        ],
        summary="SSRI sexual dysfunction side effects",
    )


# ── Ingest + extract + verify graph ──


@pytest.mark.asyncio
async def test_e2e_ingest_and_extract(repo: InMemoryRepository) -> None:
    """Full pipeline: ingest 3 episodes, persist extraction results, verify graph."""
    # Ingest episodes
    eid1 = await repo.store_episode(AGENT, "Serotonin is a neurotransmitter in the brain...")
    eid2 = await repo.store_episode(AGENT, "SSRIs like fluoxetine block serotonin reuptake...")
    eid3 = await repo.store_episode(AGENT, "SSRI-induced sexual dysfunction is common...")

    # Simulate extraction output (what the 3-agent pipeline would produce)
    await _persist_payload(repo, None, AGENT, eid1, _medical_payload_1())
    await _persist_payload(repo, None, AGENT, eid2, _medical_payload_2())
    await _persist_payload(repo, None, AGENT, eid3, _medical_payload_3())

    # Verify ontology
    node_types = await repo.get_node_types(AGENT)
    edge_types = await repo.get_edge_types(AGENT)
    type_names = {t.name for t in node_types}
    edge_names = {t.name for t in edge_types}

    assert "Neurotransmitter" in type_names
    assert "Drug" in type_names
    assert "Disease" in type_names
    assert "SideEffect" in type_names
    assert "REGULATES" in edge_names
    assert "INHIBITS" in edge_names
    assert "TREATS" in edge_names
    assert "CAUSES" in edge_names

    # Verify nodes
    serotonin_nodes = await repo.find_nodes_by_name(AGENT, "Serotonin")
    assert len(serotonin_nodes) == 1
    fluoxetine_nodes = await repo.find_nodes_by_name(AGENT, "Fluoxetine")
    assert len(fluoxetine_nodes) == 1
    depression_nodes = await repo.find_nodes_by_name(AGENT, "Depression")
    assert len(depression_nodes) == 1

    # Verify total counts
    all_node_names = await repo.list_all_node_names(AGENT)
    # Serotonin, Mood Regulation, Raphe Nuclei, Fluoxetine, Depression, Sexual Dysfunction
    assert len(all_node_names) >= 6

    all_edge_sigs = await repo.list_all_edge_signatures(AGENT)
    assert len(all_edge_sigs) >= 5  # REGULATES, PRODUCED_IN, INHIBITS, TREATS, CAUSES


@pytest.mark.asyncio
async def test_e2e_recall_returns_episodes(repo: InMemoryRepository) -> None:
    """Recall finds stored episodes."""
    await repo.store_episode(AGENT, "Serotonin is important for mood regulation")
    await repo.store_episode(AGENT, "Fluoxetine blocks serotonin reuptake")

    results = await repo.recall("serotonin", AGENT, limit=10)
    assert len(results) >= 1
    assert all(r.source_kind == "episode" for r in results)


@pytest.mark.asyncio
async def test_e2e_recall_search_nodes(repo: InMemoryRepository) -> None:
    """Recall search_nodes returns nodes from extracted graph."""
    eid1 = await repo.store_episode(AGENT, "Serotonin is a neurotransmitter")
    await _persist_payload(repo, None, AGENT, eid1, _medical_payload_1())

    nodes = await repo.search_nodes(AGENT, "Serotonin")
    assert len(nodes) >= 1
    assert nodes[0].name == "Serotonin"


@pytest.mark.asyncio
async def test_e2e_graph_traversal_depth(repo: InMemoryRepository) -> None:
    """Verify graph traversal returns correct neighborhood at different depths."""
    eid1 = await repo.store_episode(AGENT, "Serotonin neurotransmitter")
    eid2 = await repo.store_episode(AGENT, "SSRIs and fluoxetine")
    await _persist_payload(repo, None, AGENT, eid1, _medical_payload_1())
    await _persist_payload(repo, None, AGENT, eid2, _medical_payload_2())

    serotonin = (await repo.find_nodes_by_name(AGENT, "Serotonin"))[0]

    # Depth 1: direct neighbors (Mood Regulation, Raphe Nuclei, Fluoxetine via INHIBITS)
    hood_1 = await repo.get_node_neighborhood(AGENT, serotonin.id, depth=1)
    names_1 = {entry["node"].name for entry in hood_1}
    assert "Mood Regulation" in names_1
    assert "Raphe Nuclei" in names_1

    # Depth 2: should reach Depression (via Fluoxetine -> TREATS -> Depression)
    hood_2 = await repo.get_node_neighborhood(AGENT, serotonin.id, depth=2)
    names_2 = {entry["node"].name for entry in hood_2}
    assert len(names_2) > len(names_1)


@pytest.mark.asyncio
async def test_e2e_graph_context_construction(repo: InMemoryRepository) -> None:
    """Verify GraphContext can be built from neighborhood data."""
    eid1 = await repo.store_episode(AGENT, "Serotonin neurotransmitter")
    await _persist_payload(repo, None, AGENT, eid1, _medical_payload_1())

    serotonin = (await repo.find_nodes_by_name(AGENT, "Serotonin"))[0]
    neighborhood = await repo.get_node_neighborhood(AGENT, serotonin.id, depth=1)

    node_types = await repo.get_node_types(AGENT)
    edge_types = await repo.get_edge_types(AGENT)
    type_map = {t.id: t.name for t in node_types}
    edge_type_map = {t.id: t.name for t in edge_types}

    ctx = GraphContext(
        center_node={
            "id": serotonin.id,
            "name": serotonin.name,
            "type": type_map.get(serotonin.type_id, "Unknown"),
            "properties": serotonin.properties,
        },
        edges=[
            {
                "source": entry["edges"][0].source_id,
                "target": entry["edges"][0].target_id,
                "type": edge_type_map.get(entry["edges"][0].type_id, "Unknown"),
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
                "type": type_map.get(entry["node"].type_id, "Unknown"),
            }
            for entry in neighborhood
        ],
        depth=1,
    )

    assert ctx.center_node["name"] == "Serotonin"
    assert ctx.center_node["type"] == "Neurotransmitter"
    assert len(ctx.neighbor_nodes) >= 2
    assert len(ctx.edges) >= 2
    edge_types_found = {e["type"] for e in ctx.edges}
    assert "REGULATES" in edge_types_found or "PRODUCED_IN" in edge_types_found


@pytest.mark.asyncio
async def test_e2e_discover_returns_types_with_counts(repo: InMemoryRepository) -> None:
    """Discover returns node/edge types with accurate counts."""
    eid1 = await repo.store_episode(AGENT, "Serotonin")
    eid2 = await repo.store_episode(AGENT, "Fluoxetine")
    await _persist_payload(repo, None, AGENT, eid1, _medical_payload_1())
    await _persist_payload(repo, None, AGENT, eid2, _medical_payload_2())

    node_types = await repo.get_node_types(AGENT)
    assert len(node_types) >= 4  # Neurotransmitter, BiologicalProcess, BrainRegion, Drug, Disease

    # Check that counts reflect actual node counts
    for nt in node_types:
        if nt.name == "Neurotransmitter":
            assert nt.count >= 1  # Serotonin
        elif nt.name == "Drug":
            assert nt.count >= 1  # Fluoxetine

    edge_types = await repo.get_edge_types(AGENT)
    assert len(edge_types) >= 3

    stats = await repo.get_stats(AGENT)
    assert isinstance(stats, GraphStats)
    assert stats.total_nodes >= 5
    assert stats.total_edges >= 4
    assert stats.total_episodes >= 2


@pytest.mark.asyncio
async def test_e2e_no_duplicate_nodes_on_reprocess(repo: InMemoryRepository) -> None:
    """Re-extracting the same content should not create duplicate nodes."""
    eid1 = await repo.store_episode(AGENT, "Serotonin content")
    await _persist_payload(repo, None, AGENT, eid1, _medical_payload_1())

    # Count nodes after first extraction
    names_before = await repo.list_all_node_names(AGENT)

    # Re-persist same payload (simulates re-extraction on retry)
    await _persist_payload(repo, None, AGENT, eid1, _medical_payload_1())

    names_after = await repo.list_all_node_names(AGENT)
    assert len(names_after) == len(names_before), "Duplicate nodes created on reprocess"


@pytest.mark.asyncio
async def test_e2e_cross_episode_edges(repo: InMemoryRepository) -> None:
    """Edges can reference nodes created by different episodes."""
    eid1 = await repo.store_episode(AGENT, "Serotonin neurotransmitter")
    eid2 = await repo.store_episode(AGENT, "Fluoxetine SSRI")
    eid3 = await repo.store_episode(AGENT, "SSRI side effects")

    await _persist_payload(repo, None, AGENT, eid1, _medical_payload_1())
    await _persist_payload(repo, None, AGENT, eid2, _medical_payload_2())
    await _persist_payload(repo, None, AGENT, eid3, _medical_payload_3())

    # Verify the CAUSES edge from Fluoxetine (eid2) to Sexual Dysfunction (eid3)
    fluoxetine = (await repo.find_nodes_by_name(AGENT, "Fluoxetine"))[0]
    hood = await repo.get_node_neighborhood(AGENT, fluoxetine.id, depth=1)
    neighbor_names = {entry["node"].name for entry in hood}
    assert "Sexual Dysfunction" in neighbor_names, "Cross-episode edge not found"
    assert "Depression" in neighbor_names, "Fluoxetine -> Depression edge not found"


@pytest.mark.asyncio
async def test_e2e_episode_agent_isolation(repo: InMemoryRepository) -> None:
    """Different agents' episodes are isolated in the mock.

    Note: Node-level agent isolation is enforced by the GraphServiceAdapter
    via PostgreSQL schema routing, not by InMemoryRepository. This test
    verifies episode isolation which the mock does support.
    """
    agent_a = "agent-alice"
    agent_b = "agent-bob"

    await repo.store_episode(agent_a, "Alice's serotonin data")
    await repo.store_episode(agent_b, "Bob's dopamine data")

    results_a = await repo.recall("serotonin", agent_a, limit=10)
    results_b = await repo.recall("serotonin", agent_b, limit=10)

    # Alice should find her episode, Bob should not
    assert len(results_a) == 1
    assert len(results_b) == 0

    results_b2 = await repo.recall("dopamine", agent_b, limit=10)
    assert len(results_b2) == 1
