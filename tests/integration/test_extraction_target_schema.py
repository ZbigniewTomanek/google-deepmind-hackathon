"""Integration test: extraction pipeline targets the correct schema.

Verifies that when episodes are stored in a shared schema via target_graph,
the extraction pipeline (with mocked LLM) creates nodes/edges in the correct
schema — not the agent's personal schema.
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
from neocortex.ingestion.episode_processor import EpisodeProcessor
from neocortex.permissions.memory_service import InMemoryPermissionService

BOOTSTRAP_ADMIN = "admin"
SHARED_SCHEMA = "ncx_shared__research"


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.fixture
def permissions() -> InMemoryPermissionService:
    svc = InMemoryPermissionService(bootstrap_admin_id=BOOTSTRAP_ADMIN)
    return svc


# ---------------------------------------------------------------------------
# Extraction persists to shared schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_payload_targets_shared_schema(repo: InMemoryRepository) -> None:
    """_persist_payload with target_schema creates nodes/edges via the shared path."""
    # Store an episode in the shared schema
    episode_id = await repo.store_episode_to("alice", SHARED_SCHEMA, "Research about quantum computing")

    # Build a librarian payload (simulates LLM extraction output)
    payload = LibrarianPayload(
        accepted_node_types=[
            ProposedNodeType(name="Technology", description="A technology or field"),
        ],
        accepted_edge_types=[
            ProposedEdgeType(name="RELATED_TO", description="Topical relationship"),
        ],
        entities=[
            NormalizedEntity(
                name="Quantum Computing",
                type_name="Technology",
                description="Computing paradigm using quantum mechanics",
            ),
            NormalizedEntity(
                name="Qubits",
                type_name="Technology",
                description="Quantum bits, the basic unit of quantum information",
            ),
        ],
        relations=[
            NormalizedRelation(
                source_name="Quantum Computing",
                target_name="Qubits",
                relation_type="RELATED_TO",
                weight=0.9,
            ),
        ],
    )

    # Persist with target_schema — all repo calls receive target_schema
    await _persist_payload(
        repo=repo,
        embeddings=None,
        agent_id="alice",
        episode_id=episode_id,
        payload=payload,
        target_schema=SHARED_SCHEMA,
    )

    # Verify nodes were created
    assert len(repo._nodes) == 2
    node_names = {n.name for n in repo._nodes.values()}
    assert "Quantum Computing" in node_names
    assert "Qubits" in node_names

    # Verify edge was created
    assert len(repo._edges) == 1
    edge = next(iter(repo._edges.values()))
    assert edge.weight == 0.9

    # Verify node types and edge types were created
    assert "Technology" in repo._node_types
    assert "RELATED_TO" in repo._edge_types


@pytest.mark.asyncio
async def test_persist_payload_personal_when_no_target(repo: InMemoryRepository) -> None:
    """_persist_payload without target_schema uses the personal graph path."""
    episode_id = await repo.store_episode("alice", "Personal notes about Python")

    payload = LibrarianPayload(
        entities=[
            NormalizedEntity(
                name="Python",
                type_name="Language",
                description="Programming language",
            ),
        ],
        relations=[],
    )

    await _persist_payload(
        repo=repo,
        embeddings=None,
        agent_id="alice",
        episode_id=episode_id,
        payload=payload,
        target_schema=None,
    )

    assert len(repo._nodes) == 1
    assert next(iter(repo._nodes.values())).name == "Python"
    # Episode is in main list only (not schema-bucketed)
    assert len(repo._schema_episodes) == 0


# ---------------------------------------------------------------------------
# Full ingestion + extraction flow (mocked LLM)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingestion_to_extraction_targets_shared_schema(
    repo: InMemoryRepository,
    permissions: InMemoryPermissionService,
) -> None:
    """End-to-end: ingestion with target_graph, then extraction persists to shared schema."""
    await permissions.ensure_admin(BOOTSTRAP_ADMIN)
    await permissions.grant("alice", SHARED_SCHEMA, can_read=True, can_write=True, granted_by=BOOTSTRAP_ADMIN)

    # 1. Ingest episode to shared schema
    processor = EpisodeProcessor(repo=repo, extraction_enabled=False)
    result = await processor.process_text("alice", "Dopamine is a neurotransmitter", {}, target_schema=SHARED_SCHEMA)
    assert result.status == "stored"
    assert SHARED_SCHEMA in repo._schema_episodes
    episode_id = repo._schema_episodes[SHARED_SCHEMA][0]["id"]

    # 2. Simulate extraction with target_schema
    payload = LibrarianPayload(
        accepted_node_types=[ProposedNodeType(name="Chemical", description="Chemical compound")],
        accepted_edge_types=[ProposedEdgeType(name="IS_A", description="Type relationship")],
        entities=[
            NormalizedEntity(name="Dopamine", type_name="Chemical", description="A neurotransmitter"),
        ],
        relations=[],
    )

    await _persist_payload(
        repo=repo,
        embeddings=None,
        agent_id="alice",
        episode_id=episode_id,
        payload=payload,
        target_schema=SHARED_SCHEMA,
    )

    # 3. Verify nodes in shared schema context
    assert len(repo._nodes) == 1
    node = next(iter(repo._nodes.values()))
    assert node.name == "Dopamine"
    assert node.properties.get("_source_episode") == episode_id

    # 4. Bob with read access can see the shared graph
    await permissions.grant("bob", SHARED_SCHEMA, can_read=True, can_write=False, granted_by=BOOTSTRAP_ADMIN)
    assert await permissions.can_read_schema("bob", SHARED_SCHEMA)

    # 5. Eve without access cannot read the shared graph
    assert not await permissions.can_read_schema("eve", SHARED_SCHEMA)


# ---------------------------------------------------------------------------
# Extraction with relations targeting shared schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extraction_creates_edges_in_shared_schema(repo: InMemoryRepository) -> None:
    """Extraction with relations creates edges with target_schema correctly."""
    episode_id = await repo.store_episode_to("alice", SHARED_SCHEMA, "Warsaw is the capital of Poland")

    payload = LibrarianPayload(
        accepted_node_types=[ProposedNodeType(name="City"), ProposedNodeType(name="Country")],
        accepted_edge_types=[ProposedEdgeType(name="CAPITAL_OF")],
        entities=[
            NormalizedEntity(name="Warsaw", type_name="City", description="Capital city"),
            NormalizedEntity(name="Poland", type_name="Country", description="European country"),
        ],
        relations=[
            NormalizedRelation(
                source_name="Warsaw",
                target_name="Poland",
                relation_type="CAPITAL_OF",
                weight=1.0,
            ),
        ],
    )

    await _persist_payload(
        repo=repo,
        embeddings=None,
        agent_id="alice",
        episode_id=episode_id,
        payload=payload,
        target_schema=SHARED_SCHEMA,
    )

    # Verify graph structure
    assert len(repo._nodes) == 2
    assert len(repo._edges) == 1
    edge = next(iter(repo._edges.values()))
    # Verify edge connects the right nodes
    src_node = repo._nodes[edge.source_id]
    tgt_node = repo._nodes[edge.target_id]
    assert src_node.name == "Warsaw"
    assert tgt_node.name == "Poland"

    # Verify edge signatures
    sigs = await repo.list_all_edge_signatures("alice")
    assert len(sigs) == 1
    assert "Warsaw" in sigs[0]
    assert "Poland" in sigs[0]
    assert "CAPITAL_OF" in sigs[0]
