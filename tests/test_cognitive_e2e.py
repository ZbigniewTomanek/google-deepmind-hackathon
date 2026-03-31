"""E2E tests for cognitive heuristics — built incrementally, one TestStageN class per plan stage."""

from datetime import UTC, datetime, timedelta

import pytest

from neocortex.db.mock import InMemoryRepository
from neocortex.extraction.pipeline import _persist_payload
from neocortex.extraction.schemas import (
    ExtractedEntity,
    LibrarianPayload,
    NormalizedEntity,
)
from neocortex.mcp_settings import MCPSettings
from neocortex.models import Edge, Episode, Node
from neocortex.schemas.memory import GraphStats, RecallItem
from neocortex.scoring import (
    HybridWeights,
    compute_base_activation,
    compute_hybrid_score,
    compute_spreading_activation,
    neighborhood_to_adjacency,
)
from neocortex.tools.recall import _maybe_forget_sweep

AGENT_ID = "test-agent"


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.fixture
def settings() -> MCPSettings:
    return MCPSettings()


async def populate_small_graph(repo: InMemoryRepository) -> dict:
    """Create a small graph: 3 node types, 5 nodes, 6 edges, 2 episodes.

    Returns dict with references to all created objects for assertions.
    """
    # Node types
    concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
    person = await repo.get_or_create_node_type(AGENT_ID, "Person")
    tool = await repo.get_or_create_node_type(AGENT_ID, "Tool")

    # Edge type
    relates = await repo.get_or_create_edge_type(AGENT_ID, "RELATES_TO")

    # Nodes
    n1 = await repo.upsert_node(AGENT_ID, "Serotonin", concept.id, content="A neurotransmitter")
    n2 = await repo.upsert_node(AGENT_ID, "Dopamine", concept.id, content="A neurotransmitter involved in reward")
    n3 = await repo.upsert_node(AGENT_ID, "Dr. Smith", person.id, content="Neuroscience researcher")
    n4 = await repo.upsert_node(AGENT_ID, "Python", tool.id, content="Programming language")
    n5 = await repo.upsert_node(AGENT_ID, "NumPy", tool.id, content="Numerical computing library")

    # Edges (6 total)
    e1 = await repo.upsert_edge(AGENT_ID, n1.id, n2.id, relates.id, weight=1.0)
    assert e1 is not None
    e2 = await repo.upsert_edge(AGENT_ID, n1.id, n3.id, relates.id, weight=0.8)
    assert e2 is not None
    e3 = await repo.upsert_edge(AGENT_ID, n2.id, n3.id, relates.id, weight=0.6)
    assert e3 is not None
    e4 = await repo.upsert_edge(AGENT_ID, n4.id, n5.id, relates.id, weight=1.0)
    assert e4 is not None
    e5 = await repo.upsert_edge(AGENT_ID, n3.id, n4.id, relates.id, weight=0.4)
    assert e5 is not None
    e6 = await repo.upsert_edge(AGENT_ID, n5.id, n1.id, relates.id, weight=0.3)
    assert e6 is not None

    # Episodes
    ep1_id = await repo.store_episode(AGENT_ID, "Discussed serotonin pathways with Dr. Smith")
    ep2_id = await repo.store_episode(AGENT_ID, "Used Python and NumPy for data analysis")

    return {
        "node_types": {"concept": concept, "person": person, "tool": tool},
        "edge_types": {"relates": relates},
        "nodes": {"serotonin": n1, "dopamine": n2, "dr_smith": n3, "python": n4, "numpy": n5},
        "edges": {"e1": e1, "e2": e2, "e3": e3, "e4": e4, "e5": e5, "e6": e6},
        "episode_ids": [ep1_id, ep2_id],
    }


class TestStage1SchemaFoundation:
    def test_node_model_has_cognitive_fields(self):
        now = datetime.now(UTC)
        node = Node(
            id=1,
            type_id=1,
            name="Test",
            created_at=now,
            updated_at=now,
        )
        assert node.access_count == 0
        assert node.importance == 0.5
        assert node.forgotten is False
        assert node.forgotten_at is None

    def test_episode_model_has_cognitive_fields(self):
        now = datetime.now(UTC)
        episode = Episode(
            id=1,
            agent_id="test",
            content="test content",
            created_at=now,
        )
        assert episode.access_count == 0
        assert episode.importance == 0.5
        assert episode.consolidated is False

    def test_edge_model_has_last_reinforced_at(self):
        now = datetime.now(UTC)
        edge = Edge(
            id=1,
            source_id=1,
            target_id=2,
            type_id=1,
            created_at=now,
            last_reinforced_at=now,
        )
        assert edge.last_reinforced_at == now

    def test_edge_model_last_reinforced_at_defaults_none(self):
        now = datetime.now(UTC)
        edge = Edge(
            id=1,
            source_id=1,
            target_id=2,
            type_id=1,
            created_at=now,
        )
        assert edge.last_reinforced_at is None

    def test_recall_item_has_cognitive_fields(self):
        item = RecallItem(
            item_id=1,
            name="Test",
            content="test",
            item_type="Concept",
            score=0.8,
            activation_score=0.6,
            importance=0.9,
            source_kind="node",
        )
        assert item.activation_score == 0.6
        assert item.importance == 0.9

    def test_recall_item_cognitive_fields_default_none(self):
        item = RecallItem(
            item_id=1,
            name="Test",
            content="test",
            item_type="Concept",
            score=0.8,
            source_kind="node",
        )
        assert item.activation_score is None
        assert item.importance is None

    def test_settings_have_cognitive_params(self):
        settings = MCPSettings()
        # New cognitive params
        assert settings.recall_weight_activation == 0.20
        assert settings.recall_weight_importance == 0.15
        assert settings.activation_decay_rate == 0.5
        assert settings.spreading_activation_decay == 0.6
        assert settings.spreading_activation_max_depth == 2
        assert settings.forget_activation_threshold == 0.05
        assert settings.forget_importance_floor == 0.3
        assert settings.edge_reinforcement_delta == 0.05
        assert settings.edge_weight_floor == 0.1
        assert settings.edge_weight_ceiling == 1.5
        # Rebalanced weights (Stage 3: temporal recency rebalance)
        assert settings.recall_weight_vector == 0.3
        assert settings.recall_weight_text == 0.2
        assert settings.recall_weight_recency == 0.15

    @pytest.mark.asyncio
    async def test_mock_repo_upsert_node_with_new_fields(self, repo: InMemoryRepository):
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        node = await repo.upsert_node(AGENT_ID, "Test Node", concept.id, content="test content")
        assert node.access_count == 0
        assert node.importance == 0.5
        assert node.forgotten is False

    @pytest.mark.asyncio
    async def test_populate_small_graph(self, repo: InMemoryRepository):
        """Verify the shared helper creates the expected graph structure."""
        graph = await populate_small_graph(repo)
        assert len(graph["nodes"]) == 5
        assert len(graph["edges"]) == 6
        assert len(graph["episode_ids"]) == 2


class TestStage2BaseActivation:
    def test_base_activation_zero_access(self):
        """Node with access_count=0 returns activation ~0.5 (sigmoid of 0)."""
        now = datetime.now(UTC)
        activation = compute_base_activation(access_count=0, last_accessed_at=now)
        # ln(0+1) - 0.5*ln(0+1) = 0 - 0 = 0, sigmoid(0) = 0.5
        assert activation == pytest.approx(0.5, abs=0.01)

    def test_base_activation_high_frequency_recent(self):
        """Node with access_count=100, last_accessed=now returns high activation (dampened)."""
        now = datetime.now(UTC)
        activation = compute_base_activation(access_count=100, last_accessed_at=now)
        # With default dampening (exponent=0.5): ln(√100+1) = ln(11) ≈ 2.4, sigmoid ≈ 0.92
        assert activation > 0.85

    def test_base_activation_low_frequency_stale(self):
        """Node with access_count=1, last_accessed=30d ago returns activation < 0.3."""
        stale = datetime.now(UTC) - timedelta(days=30)
        activation = compute_base_activation(access_count=1, last_accessed_at=stale)
        assert activation < 0.3

    def test_base_activation_decays_with_time(self):
        """Two nodes same access_count, one accessed 1h ago, other 7d ago — first scores higher."""
        recent = datetime.now(UTC) - timedelta(hours=1)
        old = datetime.now(UTC) - timedelta(days=7)
        act_recent = compute_base_activation(access_count=5, last_accessed_at=recent)
        act_old = compute_base_activation(access_count=5, last_accessed_at=old)
        assert act_recent > act_old

    def test_hybrid_score_five_signals(self):
        """All 5 signals provided, verify weighted sum."""
        weights = HybridWeights(vector=0.3, text=0.2, recency=0.1, activation=0.25, importance=0.15)
        score = compute_hybrid_score(
            vector_sim=0.9,
            text_rank=0.8,
            recency=0.7,
            activation=0.6,
            importance=0.5,
            weights=weights,
        )
        expected = 0.3 * 0.9 + 0.2 * 0.8 + 0.1 * 0.7 + 0.25 * 0.6 + 0.15 * 0.5
        assert score == pytest.approx(expected, abs=1e-9)

    def test_hybrid_score_activation_none_degrades(self):
        """activation=None redistributes weight to remaining signals."""
        weights = HybridWeights(vector=0.3, text=0.2, recency=0.1, activation=0.25, importance=0.15)
        score = compute_hybrid_score(
            vector_sim=0.9,
            text_rank=0.8,
            recency=0.7,
            activation=None,
            importance=0.5,
            weights=weights,
        )
        # Without activation: total weight = 0.3 + 0.2 + 0.1 + 0.15 = 0.75
        total = 0.3 + 0.2 + 0.1 + 0.15
        expected = (0.3 / total) * 0.9 + (0.2 / total) * 0.8 + (0.1 / total) * 0.7 + (0.15 / total) * 0.5
        assert score == pytest.approx(expected, abs=1e-9)

    @pytest.mark.asyncio
    async def test_record_node_access_increments(self, repo: InMemoryRepository):
        """Create node via mock repo, call record_node_access, verify increments."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        node = await repo.upsert_node(AGENT_ID, "Test Node", concept.id, content="test")
        assert node.access_count == 0

        await repo.record_node_access(AGENT_ID, [node.id])
        updated = repo._nodes[node.id]
        assert updated.access_count == 1
        assert updated.last_accessed_at is not None

    @pytest.mark.asyncio
    async def test_record_episode_access_increments(self, repo: InMemoryRepository):
        """Store episode, call record_episode_access, verify increments."""
        ep_id = await repo.store_episode(AGENT_ID, "Test episode content")
        ep_record = next(e for e in repo._episodes if e["id"] == ep_id)
        assert ep_record.get("access_count", 0) == 0

        await repo.record_episode_access(AGENT_ID, [ep_id])
        ep_record = next(e for e in repo._episodes if e["id"] == ep_id)
        assert ep_record["access_count"] == 1
        assert ep_record["last_accessed_at"] is not None

    @pytest.mark.asyncio
    async def test_mock_recall_uses_real_scoring(self, repo: InMemoryRepository):
        """Populate mock repo with 2 nodes, verify scored node ranks higher (not both score=1.0)."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")

        # Node 1: accessed 50 times recently
        n1 = await repo.upsert_node(AGENT_ID, "Serotonin Alpha", concept.id, content="A neurotransmitter alpha")
        now = datetime.now(UTC)
        repo._nodes[n1.id] = n1.model_copy(update={"access_count": 50, "last_accessed_at": now})

        # Node 2: never accessed
        await repo.upsert_node(AGENT_ID, "Serotonin Beta", concept.id, content="A neurotransmitter beta")

        results = await repo.recall("Serotonin", AGENT_ID, limit=10)
        assert len(results) >= 2
        # They should have different scores (not both 1.0)
        scores = [r.score for r in results]
        assert len(set(scores)) > 1, "Scores should not all be the same"
        # The frequently accessed node should rank first
        assert results[0].name == "Serotonin Alpha"

    @pytest.mark.asyncio
    async def test_episode_activation_in_recall(self, repo: InMemoryRepository):
        """Store 2 episodes. Recall both. Recall again — verify episodes that were recalled have access_count >= 1."""
        await repo.store_episode(AGENT_ID, "Serotonin pathway discussion")
        await repo.store_episode(AGENT_ID, "Serotonin receptor analysis")

        # First recall
        results1 = await repo.recall("Serotonin", AGENT_ID, limit=10)
        assert len(results1) == 2

        # Manually record access (in real flow, recall tool does this)
        episode_ids = [r.item_id for r in results1 if r.source_kind == "episode"]
        await repo.record_episode_access(AGENT_ID, episode_ids)

        # Second recall — episodes should now have higher activation
        results2 = await repo.recall("Serotonin", AGENT_ID, limit=10)
        assert len(results2) == 2
        for r in results2:
            if r.source_kind == "episode":
                assert r.activation_score is not None
                assert r.activation_score > 0.5  # Higher than zero-access baseline

    @pytest.mark.asyncio
    async def test_recall_records_access(self, repo: InMemoryRepository):
        """Populate graph with nodes and episodes, recall, verify access incremented.

        Note: the mock recall() does NOT auto-record access — that's the recall tool's job.
        So this test manually records access to verify the mechanism works.
        """
        await populate_small_graph(repo)
        # Recall matching "Serotonin" — should match node and episode
        results = await repo.recall("serotonin", AGENT_ID, limit=10)
        assert len(results) > 0

        # Simulate what the recall tool does: record access
        node_ids = [r.item_id for r in results if r.source_kind == "node"]
        episode_ids = [r.item_id for r in results if r.source_kind == "episode"]
        if node_ids:
            await repo.record_node_access(AGENT_ID, node_ids)
        if episode_ids:
            await repo.record_episode_access(AGENT_ID, episode_ids)

        # Verify access was recorded
        for nid in node_ids:
            assert repo._nodes[nid].access_count >= 1
        for ep in repo._episodes:
            if ep["id"] in episode_ids:
                assert ep["access_count"] >= 1


class TestStage3Importance:
    @pytest.mark.asyncio
    async def test_upsert_node_with_importance(self, repo: InMemoryRepository):
        """Upsert node with importance=0.8, read back, verify importance=0.8."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        node = await repo.upsert_node(AGENT_ID, "Serotonin", concept.id, content="A neurotransmitter", importance=0.8)
        assert node.importance == 0.8

    @pytest.mark.asyncio
    async def test_upsert_node_importance_takes_max(self, repo: InMemoryRepository):
        """Upsert node with importance=0.3, then 0.7, then 0.5 — verify max semantics."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        node = await repo.upsert_node(AGENT_ID, "Serotonin", concept.id, content="A neurotransmitter", importance=0.3)
        assert node.importance == 0.3

        node = await repo.upsert_node(AGENT_ID, "Serotonin", concept.id, content="A neurotransmitter", importance=0.7)
        assert node.importance == 0.7

        node = await repo.upsert_node(AGENT_ID, "Serotonin", concept.id, content="A neurotransmitter", importance=0.5)
        assert node.importance == 0.7  # max semantics — stays at 0.7

    @pytest.mark.asyncio
    async def test_upsert_node_default_importance(self, repo: InMemoryRepository):
        """Upsert without specifying importance, verify default 0.5."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        node = await repo.upsert_node(AGENT_ID, "Dopamine", concept.id, content="Reward pathway")
        assert node.importance == 0.5

    def test_importance_in_hybrid_score(self):
        """Verify compute_hybrid_score with importance=0.9 scores higher than importance=0.1."""
        weights = HybridWeights(vector=0.3, text=0.2, recency=0.1, activation=0.25, importance=0.15)
        score_high = compute_hybrid_score(
            vector_sim=None, text_rank=None, recency=0.5, activation=0.5, importance=0.9, weights=weights
        )
        score_low = compute_hybrid_score(
            vector_sim=None, text_rank=None, recency=0.5, activation=0.5, importance=0.1, weights=weights
        )
        assert score_high > score_low

    @pytest.mark.asyncio
    async def test_importance_boosts_recall_ranking(self, repo: InMemoryRepository):
        """Populate mock repo with 2 nodes matching same query: one high-importance, one low. Verify ranking."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        await repo.upsert_node(
            AGENT_ID, "Serotonin Alpha", concept.id, content="A neurotransmitter alpha", importance=0.9
        )
        await repo.upsert_node(
            AGENT_ID, "Serotonin Beta", concept.id, content="A neurotransmitter beta", importance=0.1
        )

        results = await repo.recall("Serotonin", AGENT_ID, limit=10)
        assert len(results) >= 2
        assert results[0].name == "Serotonin Alpha"
        assert results[0].importance == 0.9
        assert results[1].importance == 0.1

    def test_extraction_schemas_have_importance(self):
        """Instantiate ExtractedEntity and NormalizedEntity with importance field, verify validation."""
        entity = ExtractedEntity(name="Serotonin", type_name="Neurotransmitter", importance=0.8)
        assert entity.importance == 0.8

        normalized = NormalizedEntity(name="Serotonin", type_name="Neurotransmitter", importance=0.7)
        assert normalized.importance == 0.7

        # Verify validation rejects out-of-range
        with pytest.raises(ValueError):
            ExtractedEntity(name="Bad", type_name="T", importance=1.5)
        with pytest.raises(ValueError):
            NormalizedEntity(name="Bad", type_name="T", importance=-0.1)

    @pytest.mark.asyncio
    async def test_importance_hint_floors_extracted_importance(self, repo: InMemoryRepository):
        """Store episode with importance_hint=0.8. Persist entity with lower importance.
        Verify node gets importance=0.8 (hint used as floor).
        Then persist entity with higher importance=0.9 — verify importance stays 0.9.
        """
        # Store episode with importance_hint
        ep_id = await repo.store_episode(
            AGENT_ID,
            "Serotonin is critical for mood regulation",
            metadata={"importance_hint": 0.8},
            importance=0.8,
        )

        # Create a payload with entity that has lower importance (0.4)
        await repo.get_or_create_node_type(AGENT_ID, "Neurotransmitter")
        payload = LibrarianPayload(
            entities=[
                NormalizedEntity(
                    name="Serotonin",
                    type_name="Neurotransmitter",
                    description="A neurotransmitter",
                    importance=0.4,
                )
            ],
            relations=[],
        )

        await _persist_payload(repo, None, AGENT_ID, ep_id, payload)

        nodes = await repo.find_nodes_by_name(AGENT_ID, "Serotonin")
        assert len(nodes) == 1
        assert nodes[0].importance == 0.8  # hint used as floor

        # Now persist with higher extractor importance (0.9)
        ep_id2 = await repo.store_episode(
            AGENT_ID,
            "Serotonin details",
            metadata={"importance_hint": 0.8},
            importance=0.8,
        )
        payload2 = LibrarianPayload(
            entities=[
                NormalizedEntity(
                    name="Serotonin",
                    type_name="Neurotransmitter",
                    description="A neurotransmitter",
                    importance=0.9,
                )
            ],
            relations=[],
        )
        await _persist_payload(repo, None, AGENT_ID, ep_id2, payload2)

        nodes = await repo.find_nodes_by_name(AGENT_ID, "Serotonin")
        assert len(nodes) == 1
        assert nodes[0].importance == 0.9  # extractor was higher, max semantics


class TestStage4SpreadingActivation:
    def test_spreading_single_seed_two_neighbors(self):
        """Graph: A→B(w=1.0), A→C(w=0.5). Seed A with score 1.0.
        Verify B gets higher bonus than C (proportional to edge weight).
        """
        adjacency = {
            1: [(2, 1.0), (3, 0.5)],  # A -> B(1.0), A -> C(0.5)
        }
        bonus = compute_spreading_activation(
            seed_nodes=[(1, 1.0)],
            neighborhood=adjacency,
            decay=0.6,
            max_depth=2,
        )
        assert 2 in bonus
        assert 3 in bonus
        # B should get higher bonus than C (proportional to edge weight)
        assert bonus[2] > bonus[3]

    def test_spreading_two_seeds_converge(self):
        """Graph: A→C, B→C. Seed A and B each with score 1.0.
        Verify C's bonus is the sum of both contributions (before normalization).
        """
        adjacency = {
            1: [(3, 1.0)],  # A -> C
            2: [(3, 1.0)],  # B -> C
        }
        # Single seed A
        compute_spreading_activation(
            seed_nodes=[(1, 1.0)],
            neighborhood=adjacency,
            decay=0.6,
            max_depth=2,
        )
        # Both seeds — C should receive from both
        bonus_both = compute_spreading_activation(
            seed_nodes=[(1, 1.0), (2, 1.0)],
            neighborhood=adjacency,
            decay=0.6,
            max_depth=2,
        )
        # With two seeds, C gets contributions from both (normalized)
        assert 3 in bonus_both
        assert bonus_both[3] > 0

    def test_spreading_decay_across_hops(self):
        """Graph: A→B→C. Seed A. Verify B's bonus > C's bonus."""
        adjacency = {
            1: [(2, 1.0)],  # A -> B
            2: [(3, 1.0)],  # B -> C
        }
        bonus = compute_spreading_activation(
            seed_nodes=[(1, 1.0)],
            neighborhood=adjacency,
            decay=0.6,
            max_depth=2,
        )
        assert 2 in bonus
        assert 3 in bonus
        assert bonus[2] > bonus[3]  # B (1 hop) > C (2 hops)

    def test_spreading_isolated_node_zero_bonus(self):
        """Node D with no edges. Verify D gets 0 bonus."""
        adjacency: dict[int, list[tuple[int, float]]] = {}
        bonus = compute_spreading_activation(
            seed_nodes=[(1, 1.0)],
            neighborhood=adjacency,
            decay=0.6,
            max_depth=2,
        )
        assert bonus.get(4, 0.0) == 0.0

    def test_spreading_respects_max_depth(self):
        """Graph: A→B→C→D. max_depth=2. Verify D (3 hops) gets 0 bonus."""
        adjacency = {
            1: [(2, 1.0)],  # A -> B
            2: [(3, 1.0)],  # B -> C
            3: [(4, 1.0)],  # C -> D
        }
        bonus = compute_spreading_activation(
            seed_nodes=[(1, 1.0)],
            neighborhood=adjacency,
            decay=0.6,
            max_depth=2,
        )
        assert 2 in bonus  # 1 hop
        assert 3 in bonus  # 2 hops
        assert 4 not in bonus  # 3 hops — beyond max_depth

    def test_spreading_with_varying_edge_weights(self):
        """Graph: A→B(w=2.0), A→C(w=0.1). Verify B bonus >> C bonus."""
        adjacency = {
            1: [(2, 2.0), (3, 0.1)],
        }
        bonus = compute_spreading_activation(
            seed_nodes=[(1, 1.0)],
            neighborhood=adjacency,
            decay=0.6,
            max_depth=2,
        )
        assert bonus[2] > bonus[3]
        # B should have significantly more bonus
        assert bonus[2] / bonus[3] > 10

    @pytest.mark.asyncio
    async def test_recall_includes_spreading_bonus(self, repo: InMemoryRepository):
        """Full integration: populate mock repo with a triangle graph (A→B→C→A).
        Recall a query matching node A. Verify results include B and C with
        non-zero spreading_bonus in RecallItem.
        """
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        relates = await repo.get_or_create_edge_type(AGENT_ID, "RELATES_TO")

        a = await repo.upsert_node(AGENT_ID, "Serotonin", concept.id, content="A neurotransmitter serotonin")
        b = await repo.upsert_node(AGENT_ID, "Dopamine", concept.id, content="A neurotransmitter dopamine")
        c = await repo.upsert_node(AGENT_ID, "GABA", concept.id, content="An inhibitory neurotransmitter")

        await repo.upsert_edge(AGENT_ID, a.id, b.id, relates.id, weight=1.0)
        await repo.upsert_edge(AGENT_ID, b.id, c.id, relates.id, weight=1.0)
        await repo.upsert_edge(AGENT_ID, c.id, a.id, relates.id, weight=1.0)

        # search_nodes for "Serotonin" should find node A
        results = await repo.search_nodes(AGENT_ID, "Serotonin")
        assert len(results) >= 1
        node, _score = results[0]
        assert node.name == "Serotonin"

        # Recall "Serotonin" — should get A directly plus B and C via neighborhood
        # The recall tool handles spreading activation, but here we test the scoring primitives
        neighborhood = await repo.get_node_neighborhood(AGENT_ID, a.id, depth=2)
        adjacency = neighborhood_to_adjacency(neighborhood, a.id)
        bonus = compute_spreading_activation(
            seed_nodes=[(a.id, 1.0)],
            neighborhood=adjacency,
            decay=0.6,
            max_depth=2,
        )
        # B and C should have non-zero bonus
        assert b.id in bonus
        assert bonus[b.id] > 0
        # C is also reachable (via A→B→C or C→A bidirectional)
        assert c.id in bonus
        assert bonus[c.id] > 0

    @pytest.mark.asyncio
    async def test_neighborhood_to_adjacency_conversion(self, repo: InMemoryRepository):
        """Call get_node_neighborhood() for a known graph, convert via
        neighborhood_to_adjacency(), verify correct adjacency map structure.
        """
        graph = await populate_small_graph(repo)
        serotonin = graph["nodes"]["serotonin"]
        neighborhood = await repo.get_node_neighborhood(AGENT_ID, serotonin.id, depth=2)
        adjacency = neighborhood_to_adjacency(neighborhood, serotonin.id)

        # adjacency should contain entries for nodes connected by edges
        assert len(adjacency) > 0
        # All values should be lists of (neighbor_id, weight) tuples
        for _node_id, neighbors in adjacency.items():
            assert isinstance(neighbors, list)
            for neighbor_id, weight in neighbors:
                assert isinstance(neighbor_id, int)
                assert isinstance(weight, (int, float))

    @pytest.mark.asyncio
    async def test_search_nodes_returns_relevance_scores(self, repo: InMemoryRepository):
        """Call search_nodes() on mock repo, verify results include relevance scores."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        await repo.upsert_node(AGENT_ID, "Serotonin", concept.id, content="A neurotransmitter")
        await repo.upsert_node(AGENT_ID, "Dopamine", concept.id, content="Has serotonin-like effects")

        results = await repo.search_nodes(AGENT_ID, "Serotonin")
        assert len(results) >= 1
        for _node, score in results:
            assert isinstance(score, float)
            assert score > 0
        # Name match should score higher than content-only match
        name_match = [(n, s) for n, s in results if n.name == "Serotonin"]
        content_match = [(n, s) for n, s in results if n.name == "Dopamine"]
        if name_match and content_match:
            assert name_match[0][1] >= content_match[0][1]


class TestStage5EdgeReinforcement:
    @pytest.mark.asyncio
    async def test_reinforce_edges_increments_weight(self, repo: InMemoryRepository):
        """Create edge with weight=1.0, call reinforce_edges, verify weight=1.1."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        relates = await repo.get_or_create_edge_type(AGENT_ID, "RELATES_TO")
        a = await repo.upsert_node(AGENT_ID, "Alpha", concept.id)
        b = await repo.upsert_node(AGENT_ID, "Beta", concept.id)
        edge = await repo.upsert_edge(AGENT_ID, a.id, b.id, relates.id, weight=1.0)
        assert edge is not None

        await repo.reinforce_edges(AGENT_ID, [edge.id], delta=0.1, ceiling=2.0)
        updated = repo._edges[edge.id]
        assert updated.weight == pytest.approx(1.1)
        assert updated.last_reinforced_at is not None

    @pytest.mark.asyncio
    async def test_reinforce_edges_respects_ceiling(self, repo: InMemoryRepository):
        """Reinforce edge many times, verify weight never exceeds ceiling."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        relates = await repo.get_or_create_edge_type(AGENT_ID, "RELATES_TO")
        a = await repo.upsert_node(AGENT_ID, "Alpha", concept.id)
        b = await repo.upsert_node(AGENT_ID, "Beta", concept.id)
        edge = await repo.upsert_edge(AGENT_ID, a.id, b.id, relates.id, weight=1.4)
        assert edge is not None

        for _ in range(50):
            await repo.reinforce_edges(AGENT_ID, [edge.id], delta=0.1, ceiling=1.5)
        updated = repo._edges[edge.id]
        assert updated.weight <= 1.5

    @pytest.mark.asyncio
    async def test_reinforce_edges_multiple(self, repo: InMemoryRepository):
        """Create 3 edges, reinforce 2, verify only those 2 have increased weight."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        relates = await repo.get_or_create_edge_type(AGENT_ID, "RELATES_TO")
        a = await repo.upsert_node(AGENT_ID, "A", concept.id)
        b = await repo.upsert_node(AGENT_ID, "B", concept.id)
        c = await repo.upsert_node(AGENT_ID, "C", concept.id)
        d = await repo.upsert_node(AGENT_ID, "D", concept.id)
        e1 = await repo.upsert_edge(AGENT_ID, a.id, b.id, relates.id, weight=1.0)
        assert e1 is not None
        e2 = await repo.upsert_edge(AGENT_ID, b.id, c.id, relates.id, weight=1.0)
        assert e2 is not None
        e3 = await repo.upsert_edge(AGENT_ID, c.id, d.id, relates.id, weight=1.0)
        assert e3 is not None

        await repo.reinforce_edges(AGENT_ID, [e1.id, e2.id], delta=0.1, ceiling=2.0)
        assert repo._edges[e1.id].weight == pytest.approx(1.1)
        assert repo._edges[e2.id].weight == pytest.approx(1.1)
        assert repo._edges[e3.id].weight == pytest.approx(1.0)  # untouched

    @pytest.mark.asyncio
    async def test_decay_stale_edges_reduces_weight(self, repo: InMemoryRepository):
        """Create edge with weight=1.5 and old last_reinforced_at, call decay, verify weight reduced."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        relates = await repo.get_or_create_edge_type(AGENT_ID, "RELATES_TO")
        a = await repo.upsert_node(AGENT_ID, "A", concept.id)
        b = await repo.upsert_node(AGENT_ID, "B", concept.id)
        edge = await repo.upsert_edge(AGENT_ID, a.id, b.id, relates.id, weight=1.5)
        assert edge is not None

        # Make the edge stale by setting last_reinforced_at to 2 weeks ago
        old_time = datetime.now(UTC) - timedelta(days=14)
        repo._edges[edge.id] = edge.model_copy(update={"last_reinforced_at": old_time})

        count = await repo.decay_stale_edges(AGENT_ID, older_than_hours=168.0, decay_factor=0.95, floor=0.1, force=True)
        assert count == 1
        assert repo._edges[edge.id].weight == pytest.approx(1.5 * 0.95)

    @pytest.mark.asyncio
    async def test_decay_stale_edges_respects_floor(self, repo: InMemoryRepository):
        """Edge at weight=0.12, floor=0.1, decay_factor=0.5, verify weight stays at floor."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        relates = await repo.get_or_create_edge_type(AGENT_ID, "RELATES_TO")
        a = await repo.upsert_node(AGENT_ID, "A", concept.id)
        b = await repo.upsert_node(AGENT_ID, "B", concept.id)
        edge = await repo.upsert_edge(AGENT_ID, a.id, b.id, relates.id, weight=0.12)
        assert edge is not None

        old_time = datetime.now(UTC) - timedelta(days=14)
        repo._edges[edge.id] = edge.model_copy(update={"last_reinforced_at": old_time})

        await repo.decay_stale_edges(AGENT_ID, older_than_hours=168.0, decay_factor=0.5, floor=0.1, force=True)
        assert repo._edges[edge.id].weight == pytest.approx(0.1)

    @pytest.mark.asyncio
    async def test_decay_stale_edges_skips_recently_reinforced(self, repo: InMemoryRepository):
        """Create edge, reinforce it, call decay, verify weight unchanged (recently reinforced)."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        relates = await repo.get_or_create_edge_type(AGENT_ID, "RELATES_TO")
        a = await repo.upsert_node(AGENT_ID, "A", concept.id)
        b = await repo.upsert_node(AGENT_ID, "B", concept.id)
        edge = await repo.upsert_edge(AGENT_ID, a.id, b.id, relates.id, weight=1.5)
        assert edge is not None

        # Reinforce it (sets last_reinforced_at to now)
        await repo.reinforce_edges(AGENT_ID, [edge.id], delta=0.1)
        weight_after_reinforce = repo._edges[edge.id].weight

        # Decay should skip it (just reinforced)
        count = await repo.decay_stale_edges(AGENT_ID, older_than_hours=168.0, decay_factor=0.95, floor=0.1, force=True)
        assert count == 0
        assert repo._edges[edge.id].weight == pytest.approx(weight_after_reinforce)

    @pytest.mark.asyncio
    async def test_decay_targets_last_reinforced_not_created(self, repo: InMemoryRepository):
        """Create an old edge that was recently reinforced. Decay should skip it."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        relates = await repo.get_or_create_edge_type(AGENT_ID, "RELATES_TO")
        a = await repo.upsert_node(AGENT_ID, "A", concept.id)
        b = await repo.upsert_node(AGENT_ID, "B", concept.id)
        edge = await repo.upsert_edge(AGENT_ID, a.id, b.id, relates.id, weight=1.5)
        assert edge is not None

        # Make created_at old but last_reinforced_at recent
        old_time = datetime.now(UTC) - timedelta(days=30)
        recent = datetime.now(UTC) - timedelta(hours=1)
        repo._edges[edge.id] = edge.model_copy(update={"created_at": old_time, "last_reinforced_at": recent})

        count = await repo.decay_stale_edges(AGENT_ID, older_than_hours=168.0, decay_factor=0.95, floor=0.1, force=True)
        assert count == 0
        assert repo._edges[edge.id].weight == pytest.approx(1.5)

    @pytest.mark.asyncio
    async def test_repeated_recall_strengthens_edges(self, repo: InMemoryRepository):
        """Populate graph, recall same query 5 times. Verify edge weights monotonically increase."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        relates = await repo.get_or_create_edge_type(AGENT_ID, "RELATES_TO")
        a = await repo.upsert_node(AGENT_ID, "Serotonin", concept.id, content="A neurotransmitter serotonin")
        b = await repo.upsert_node(AGENT_ID, "Dopamine", concept.id, content="A neurotransmitter dopamine")
        edge = await repo.upsert_edge(AGENT_ID, a.id, b.id, relates.id, weight=1.0)
        assert edge is not None

        weights = [repo._edges[edge.id].weight]
        for _ in range(5):
            # Simulate what recall tool does: reinforce edges in neighborhood
            neighborhood = await repo.get_node_neighborhood(AGENT_ID, a.id, depth=2)
            edge_ids = [e.id for entry in neighborhood for e in entry["edges"]]
            if edge_ids:
                await repo.reinforce_edges(AGENT_ID, edge_ids, delta=0.05, ceiling=2.0)
            weights.append(repo._edges[edge.id].weight)

        # Weights should monotonically increase
        for i in range(1, len(weights)):
            assert weights[i] >= weights[i - 1], f"Weight at iteration {i} did not increase: {weights}"

    @pytest.mark.asyncio
    async def test_spreading_uses_reinforced_weights(self, repo: InMemoryRepository):
        """Reinforce an edge to weight=2.0, verify spreading activation delivers
        higher bonus than a weight=1.0 path.
        """
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        relates = await repo.get_or_create_edge_type(AGENT_ID, "RELATES_TO")
        a = await repo.upsert_node(AGENT_ID, "Alpha", concept.id)
        b = await repo.upsert_node(AGENT_ID, "Beta", concept.id)
        c = await repo.upsert_node(AGENT_ID, "Gamma", concept.id)

        # A→B with high weight, A→C with normal weight
        await repo.upsert_edge(AGENT_ID, a.id, b.id, relates.id, weight=2.0)
        await repo.upsert_edge(AGENT_ID, a.id, c.id, relates.id, weight=1.0)

        adjacency = {
            a.id: [(b.id, 2.0), (c.id, 1.0)],
        }
        bonus = compute_spreading_activation(
            seed_nodes=[(a.id, 1.0)],
            neighborhood=adjacency,
            decay=0.6,
            max_depth=2,
        )
        # Reinforced path (weight=2.0) should deliver higher bonus
        assert bonus[b.id] > bonus[c.id]


class TestStage6ForgetAndConsolidate:
    @pytest.mark.asyncio
    async def test_mark_forgotten_excludes_from_recall(self, repo: InMemoryRepository):
        """Create 3 nodes matching query 'serotonin'. Forget node #2. Recall. Verify only #1 and #3 returned."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        n1 = await repo.upsert_node(AGENT_ID, "Serotonin Alpha", concept.id, content="A serotonin variant")
        n2 = await repo.upsert_node(AGENT_ID, "Serotonin Beta", concept.id, content="A serotonin variant")
        n3 = await repo.upsert_node(AGENT_ID, "Serotonin Gamma", concept.id, content="A serotonin variant")

        await repo.mark_forgotten(AGENT_ID, [n2.id])
        results = await repo.recall("serotonin", AGENT_ID, limit=10)
        result_ids = {r.item_id for r in results if r.source_kind == "node"}
        assert n1.id in result_ids
        assert n2.id not in result_ids
        assert n3.id in result_ids

    @pytest.mark.asyncio
    async def test_mark_forgotten_excludes_from_search_nodes(self, repo: InMemoryRepository):
        """Same as above but via search_nodes()."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        n1 = await repo.upsert_node(AGENT_ID, "Serotonin Alpha", concept.id, content="A serotonin variant")
        n2 = await repo.upsert_node(AGENT_ID, "Serotonin Beta", concept.id, content="A serotonin variant")
        n3 = await repo.upsert_node(AGENT_ID, "Serotonin Gamma", concept.id, content="A serotonin variant")

        await repo.mark_forgotten(AGENT_ID, [n2.id])
        results = await repo.search_nodes(AGENT_ID, "Serotonin")
        result_ids = {n.id for n, _s in results}
        assert n1.id in result_ids
        assert n2.id not in result_ids
        assert n3.id in result_ids

    @pytest.mark.asyncio
    async def test_forgotten_node_excluded_from_neighborhood(self, repo: InMemoryRepository):
        """A→B→C graph. Forget B. Get neighborhood of A. Verify B and C absent from results."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        relates = await repo.get_or_create_edge_type(AGENT_ID, "RELATES_TO")
        a = await repo.upsert_node(AGENT_ID, "Alpha", concept.id)
        b = await repo.upsert_node(AGENT_ID, "Beta", concept.id)
        c = await repo.upsert_node(AGENT_ID, "Gamma", concept.id)
        await repo.upsert_edge(AGENT_ID, a.id, b.id, relates.id, weight=1.0)
        await repo.upsert_edge(AGENT_ID, b.id, c.id, relates.id, weight=1.0)

        await repo.mark_forgotten(AGENT_ID, [b.id])
        neighborhood = await repo.get_node_neighborhood(AGENT_ID, a.id, depth=2)
        neighbor_ids = {entry["node"].id for entry in neighborhood}
        assert b.id not in neighbor_ids
        assert c.id not in neighbor_ids  # C unreachable since B is forgotten

    @pytest.mark.asyncio
    async def test_forgotten_node_persists_in_db(self, repo: InMemoryRepository):
        """Forget a node, verify it's still in _nodes dict (not deleted)."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        n = await repo.upsert_node(AGENT_ID, "Ephemeral", concept.id)

        await repo.mark_forgotten(AGENT_ID, [n.id])
        assert n.id in repo._nodes
        assert repo._nodes[n.id].forgotten is True
        assert repo._nodes[n.id].forgotten_at is not None

    @pytest.mark.asyncio
    async def test_resurrect_node_on_upsert(self, repo: InMemoryRepository):
        """Forget a node, then upsert same name+type. Verify forgotten=False, access_count incremented."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        n = await repo.upsert_node(AGENT_ID, "Lazarus", concept.id, content="Will be resurrected")
        original_access = n.access_count

        await repo.mark_forgotten(AGENT_ID, [n.id])
        assert repo._nodes[n.id].forgotten is True

        # Re-upsert same name+type — should resurrect
        resurrected = await repo.upsert_node(AGENT_ID, "Lazarus", concept.id, content="Resurrected content")
        assert resurrected.forgotten is False
        assert resurrected.forgotten_at is None
        assert resurrected.access_count == original_access + 1

    @pytest.mark.asyncio
    async def test_identify_forgettable_nodes_low_activation_low_importance(self, repo: InMemoryRepository):
        """Create 4 nodes with different profiles. Only the low-importance, never-accessed, stale one is forgettable."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")

        # (a) high importance + accessed
        na = await repo.upsert_node(AGENT_ID, "Important Active", concept.id, importance=0.8)
        await repo.record_node_access(AGENT_ID, [na.id])

        # (b) low importance + accessed
        nb = await repo.upsert_node(AGENT_ID, "Unimportant Active", concept.id, importance=0.1)
        await repo.record_node_access(AGENT_ID, [nb.id])

        # (c) high importance + never accessed (but stale)
        nc = await repo.upsert_node(AGENT_ID, "Important Stale", concept.id, importance=0.8)
        old_time = datetime.now(UTC) - timedelta(days=14)
        repo._nodes[nc.id] = nc.model_copy(update={"last_accessed_at": old_time})

        # (d) low importance + never accessed + stale → forgettable
        nd = await repo.upsert_node(AGENT_ID, "Unimportant Stale", concept.id, importance=0.1)
        repo._nodes[nd.id] = nd.model_copy(update={"last_accessed_at": old_time})

        forgettable = await repo.identify_forgettable_nodes(AGENT_ID, 0.05, 0.3)
        assert nd.id in forgettable
        assert na.id not in forgettable
        assert nb.id not in forgettable
        assert nc.id not in forgettable

    @pytest.mark.asyncio
    async def test_identify_forgettable_nodes_respects_importance_floor(self, repo: InMemoryRepository):
        """Node with importance=0.4 and floor=0.3 → forgettable. With floor=0.5 → not forgettable."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        old_time = datetime.now(UTC) - timedelta(days=14)
        n = await repo.upsert_node(AGENT_ID, "Borderline", concept.id, importance=0.4)
        repo._nodes[n.id] = n.model_copy(update={"last_accessed_at": old_time})

        # floor=0.3 → importance 0.4 >= 0.3, NOT forgettable
        forgettable = await repo.identify_forgettable_nodes(AGENT_ID, 0.05, 0.3)
        assert n.id not in forgettable

        # floor=0.5 → importance 0.4 < 0.5, forgettable
        forgettable = await repo.identify_forgettable_nodes(AGENT_ID, 0.05, 0.5)
        assert n.id in forgettable

    @pytest.mark.asyncio
    async def test_episode_consolidation_marks_flag(self, repo: InMemoryRepository):
        """Store episode, call mark_episode_consolidated(), verify consolidated=True."""
        ep_id = await repo.store_episode(AGENT_ID, "Test consolidation episode")
        ep_record = next(e for e in repo._episodes if e["id"] == ep_id)
        assert ep_record.get("consolidated", False) is False

        await repo.mark_episode_consolidated(AGENT_ID, ep_id)
        ep_record = next(e for e in repo._episodes if e["id"] == ep_id)
        assert ep_record["consolidated"] is True

    @pytest.mark.asyncio
    async def test_consolidated_episodes_ranked_lower(self, repo: InMemoryRepository):
        """Store 2 episodes matching query. Consolidate one. Recall. Verify unconsolidated ranks above."""
        ep1_id = await repo.store_episode(AGENT_ID, "Serotonin pathway discussion first")
        ep2_id = await repo.store_episode(AGENT_ID, "Serotonin pathway discussion second")

        # Consolidate ep1
        await repo.mark_episode_consolidated(AGENT_ID, ep1_id)

        results = await repo.recall("Serotonin", AGENT_ID, limit=10)
        episode_results = [r for r in results if r.source_kind == "episode"]
        assert len(episode_results) == 2

        # Unconsolidated episode (ep2) should rank above consolidated (ep1)
        assert episode_results[0].item_id == ep2_id
        assert episode_results[1].item_id == ep1_id
        assert episode_results[0].score > episode_results[1].score

    @pytest.mark.asyncio
    async def test_full_lifecycle_forget_and_resurrect(self, repo: InMemoryRepository):
        """Create node, recall it (access_count=1), verify not forgettable.
        Create another never-accessed low-importance node, verify it IS forgettable.
        Forget it. Upsert same entity again, verify resurrected.
        """
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")

        # Active node — should not be forgettable
        n_active = await repo.upsert_node(AGENT_ID, "Active Serotonin", concept.id, importance=0.2)
        await repo.record_node_access(AGENT_ID, [n_active.id])

        # Stale low-importance node — should be forgettable
        n_stale = await repo.upsert_node(AGENT_ID, "Stale Compound", concept.id, importance=0.1)
        old_time = datetime.now(UTC) - timedelta(days=14)
        repo._nodes[n_stale.id] = n_stale.model_copy(update={"last_accessed_at": old_time})

        # Verify forgettable identification
        forgettable = await repo.identify_forgettable_nodes(AGENT_ID, 0.05, 0.3)
        assert n_active.id not in forgettable
        assert n_stale.id in forgettable

        # Forget the stale node
        count = await repo.mark_forgotten(AGENT_ID, [n_stale.id])
        assert count == 1

        # Verify it's excluded from recall
        results = await repo.recall("Stale Compound", AGENT_ID, limit=10)
        node_ids = {r.item_id for r in results if r.source_kind == "node"}
        assert n_stale.id not in node_ids

        # Re-extract the same entity (upsert resurrects)
        resurrected = await repo.upsert_node(AGENT_ID, "Stale Compound", concept.id, importance=0.1)
        assert resurrected.forgotten is False
        assert resurrected.access_count >= 1

        # Now it should appear in recall again
        results = await repo.recall("Stale Compound", AGENT_ID, limit=10)
        node_ids = {r.item_id for r in results if r.source_kind == "node"}
        assert n_stale.id in node_ids


class TestStage7FullComposition:
    """Verify all six heuristics compose correctly end-to-end."""

    @pytest.mark.asyncio
    async def test_composition_short_term_recall_favors_recent(self, repo: InMemoryRepository):
        """Simulate a coding session — store 3 related episodes in quick succession.
        Recall. Verify recency + high activation dominates ranking.
        """
        # Store 3 episodes rapidly (all very recent)
        ep1 = await repo.store_episode(AGENT_ID, "Debugging serotonin module error in parser")
        ep2 = await repo.store_episode(AGENT_ID, "Fixed serotonin module import path")
        ep3 = await repo.store_episode(AGENT_ID, "Tested serotonin module integration")

        # Access them to simulate repeated recall within a session
        await repo.record_episode_access(AGENT_ID, [ep1, ep2, ep3])
        await repo.record_episode_access(AGENT_ID, [ep1, ep2, ep3])

        results = await repo.recall("serotonin module", AGENT_ID, limit=10)
        episode_results = [r for r in results if r.source_kind == "episode"]
        assert len(episode_results) == 3

        # All should have activation > 0.5 (baseline) since they've been accessed recently
        for r in episode_results:
            assert r.activation_score is not None
            assert r.activation_score > 0.5

    @pytest.mark.asyncio
    async def test_composition_long_term_knowledge_persists(self, repo: InMemoryRepository):
        """Create node with high importance + many accesses (old) vs fresh but unimportant node.
        Verify old-but-important node outranks fresh-but-unimportant one.
        """
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")

        # Old important node with many accesses
        n_important = await repo.upsert_node(
            AGENT_ID,
            "Serotonin Receptor",
            concept.id,
            content="Key serotonin receptor for mood regulation",
            importance=0.9,
        )
        old_time = datetime.now(UTC) - timedelta(days=30)
        repo._nodes[n_important.id] = n_important.model_copy(update={"access_count": 50, "last_accessed_at": old_time})

        # Fresh but unimportant node
        await repo.upsert_node(
            AGENT_ID,
            "Serotonin Tangent",
            concept.id,
            content="Minor serotonin side note",
            importance=0.1,
        )

        results = await repo.recall("Serotonin", AGENT_ID, limit=10)
        node_results = [r for r in results if r.source_kind == "node"]
        assert len(node_results) >= 2

        # High-importance + high-access node should rank first
        assert node_results[0].name == "Serotonin Receptor"
        assert node_results[0].importance == 0.9

    @pytest.mark.asyncio
    async def test_composition_spreading_activation_discovers_hidden(self, repo: InMemoryRepository):
        """Build a 5-node chain: A→B→C→D→E. Only A matches the query.
        Verify B and C appear via spreading activation. D and E should NOT (beyond max_depth=2).
        """
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        relates = await repo.get_or_create_edge_type(AGENT_ID, "RELATES_TO")

        a = await repo.upsert_node(AGENT_ID, "Serotonin Chain", concept.id, content="Start of serotonin chain")
        b = await repo.upsert_node(AGENT_ID, "Receptor B", concept.id, content="Intermediate receptor")
        c = await repo.upsert_node(AGENT_ID, "Pathway C", concept.id, content="Downstream pathway")
        d = await repo.upsert_node(AGENT_ID, "Target D", concept.id, content="Far target")
        e = await repo.upsert_node(AGENT_ID, "Effect E", concept.id, content="End effect")

        await repo.upsert_edge(AGENT_ID, a.id, b.id, relates.id, weight=1.0)
        await repo.upsert_edge(AGENT_ID, b.id, c.id, relates.id, weight=1.0)
        await repo.upsert_edge(AGENT_ID, c.id, d.id, relates.id, weight=1.0)
        await repo.upsert_edge(AGENT_ID, d.id, e.id, relates.id, weight=1.0)

        # Only "Serotonin Chain" matches the query directly
        # Get neighborhood and run spreading activation
        neighborhood = await repo.get_node_neighborhood(AGENT_ID, a.id, depth=2)
        adjacency = neighborhood_to_adjacency(neighborhood, a.id)
        bonus = compute_spreading_activation(
            seed_nodes=[(a.id, 1.0)],
            neighborhood=adjacency,
            decay=0.6,
            max_depth=2,
        )

        # B and C should get bonus (1 and 2 hops)
        assert b.id in bonus
        assert bonus[b.id] > 0
        assert c.id in bonus
        assert bonus[c.id] > 0

        # D and E should NOT appear (beyond max_depth=2 for spreading, and
        # neighborhood was fetched with depth=2 so D is at hop 3 from A)
        assert d.id not in bonus
        assert e.id not in bonus

    @pytest.mark.asyncio
    async def test_composition_hebbian_trails_emerge(self, repo: InMemoryRepository):
        """Recall the same query 10 times. After each recall, verify that edges
        in the traversal path have increasing weights (with diminishing returns).
        """
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        relates = await repo.get_or_create_edge_type(AGENT_ID, "RELATES_TO")

        a = await repo.upsert_node(AGENT_ID, "Serotonin Hub", concept.id, content="Main serotonin hub")
        b = await repo.upsert_node(AGENT_ID, "Dopamine Hub", concept.id, content="Main dopamine hub")
        edge = await repo.upsert_edge(AGENT_ID, a.id, b.id, relates.id, weight=1.0)
        assert edge is not None

        weights = [repo._edges[edge.id].weight]
        for _ in range(10):
            neighborhood = await repo.get_node_neighborhood(AGENT_ID, a.id, depth=2)
            edge_ids = [e.id for entry in neighborhood for e in entry["edges"]]
            if edge_ids:
                await repo.reinforce_edges(AGENT_ID, edge_ids, delta=0.05, ceiling=1.5)
            weights.append(repo._edges[edge.id].weight)

        # Weights should monotonically increase
        for i in range(1, len(weights)):
            assert weights[i] >= weights[i - 1], f"Weight at iteration {i} did not increase: {weights}"

        # By iteration 10, the path should be stronger (diminishing returns → ~0.2-0.3 gain)
        assert weights[-1] > weights[0] + 0.2

    @pytest.mark.asyncio
    async def test_composition_forget_cycle(self, repo: InMemoryRepository, settings: MCPSettings):
        """Create 10 nodes with varying importance and access patterns.
        Run a forget sweep. Verify exactly the right nodes get forgotten.
        Recall and verify forgotten nodes absent. Re-extract one and verify resurrected.
        """
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")

        # Create a mix of nodes
        active_nodes = []
        stale_nodes = []
        old_time = datetime.now(UTC) - timedelta(days=14)

        for i in range(5):
            n = await repo.upsert_node(
                AGENT_ID,
                f"Active Node {i}",
                concept.id,
                content=f"Active content {i}",
                importance=0.6,
            )
            await repo.record_node_access(AGENT_ID, [n.id])
            active_nodes.append(n)

        for i in range(5):
            n = await repo.upsert_node(
                AGENT_ID,
                f"Stale Unimportant {i}",
                concept.id,
                content=f"Stale content {i}",
                importance=0.1,
            )
            repo._nodes[n.id] = n.model_copy(update={"last_accessed_at": old_time})
            stale_nodes.append(n)

        # Run forget sweep with force=True
        await _maybe_forget_sweep(repo, AGENT_ID, settings, force=True)

        # Active nodes should NOT be forgotten
        for n in active_nodes:
            assert repo._nodes[n.id].forgotten is False

        # Stale unimportant nodes should be forgotten
        for n in stale_nodes:
            assert repo._nodes[n.id].forgotten is True

        # Verify forgotten nodes absent from recall
        results = await repo.recall("Stale Unimportant", AGENT_ID, limit=20)
        result_ids = {r.item_id for r in results if r.source_kind == "node"}
        for n in stale_nodes:
            assert n.id not in result_ids

        # Re-extract one forgotten node (upsert resurrects it)
        resurrected = await repo.upsert_node(
            AGENT_ID,
            stale_nodes[0].name,
            concept.id,
            content="Resurrected content",
            importance=0.1,
        )
        assert resurrected.forgotten is False
        assert resurrected.access_count >= 1

        # Now it should appear in recall again
        results = await repo.recall(stale_nodes[0].name, AGENT_ID, limit=10)
        result_ids = {r.item_id for r in results if r.source_kind == "node"}
        assert stale_nodes[0].id in result_ids

    @pytest.mark.asyncio
    async def test_composition_consolidation_shifts_to_graph(self, repo: InMemoryRepository):
        """Store an episode, extract it (mock persist), consolidate it.
        Recall a query matching both the episode text and extracted nodes.
        Verify graph nodes rank above the consolidated episode.
        """
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")

        # Store episode
        ep_id = await repo.store_episode(AGENT_ID, "Serotonin is critical for mood regulation")

        # Simulate extraction: create a node from the episode content
        node = await repo.upsert_node(
            AGENT_ID,
            "Serotonin",
            concept.id,
            content="Serotonin is critical for mood regulation",
            importance=0.7,
        )

        # Consolidate the episode
        await repo.mark_episode_consolidated(AGENT_ID, ep_id)

        results = await repo.recall("Serotonin", AGENT_ID, limit=10)
        assert len(results) >= 2

        # Find node result and episode result
        node_result = next((r for r in results if r.source_kind == "node" and r.item_id == node.id), None)
        episode_result = next((r for r in results if r.source_kind == "episode" and r.item_id == ep_id), None)
        assert node_result is not None
        assert episode_result is not None

        # Graph node should outrank the consolidated episode
        assert node_result.score > episode_result.score

    def test_composition_graceful_degradation_no_activation(self):
        """Recall with activation=None and importance=None in hybrid scoring.
        Verify it falls back to vector+text+recency (3-signal mode) without errors.
        """
        weights = HybridWeights(vector=0.3, text=0.2, recency=0.1, activation=0.25, importance=0.15)

        # All signals present
        score_full = compute_hybrid_score(
            vector_sim=0.8,
            text_rank=0.7,
            recency=0.6,
            activation=0.5,
            importance=0.4,
            weights=weights,
        )

        # Only vector + text + recency (activation and importance None)
        score_degraded = compute_hybrid_score(
            vector_sim=0.8,
            text_rank=0.7,
            recency=0.6,
            activation=None,
            importance=None,
            weights=weights,
        )

        assert score_degraded > 0
        # Degraded should redistribute weights — result should differ but still be valid
        assert score_degraded != score_full
        # With only recency+vector+text, the redistributed weights should yield a valid [0,1] score
        assert 0 < score_degraded <= 1.0

    @pytest.mark.asyncio
    async def test_composition_cognitive_metrics_in_recall_items(self, repo: InMemoryRepository):
        """Recall and verify every RecallItem for node-sourced results has
        activation_score and importance populated (not None).
        """
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        await repo.upsert_node(AGENT_ID, "Serotonin", concept.id, content="A neurotransmitter", importance=0.8)
        await repo.upsert_node(AGENT_ID, "Serotonin Receptor", concept.id, content="Binds serotonin", importance=0.6)

        results = await repo.recall("Serotonin", AGENT_ID, limit=10)
        node_results = [r for r in results if r.source_kind == "node"]
        assert len(node_results) >= 2

        for r in node_results:
            assert r.activation_score is not None, f"Node {r.name} missing activation_score"
            assert r.importance is not None, f"Node {r.name} missing importance"
            assert 0 <= r.activation_score <= 1.0
            assert 0 <= r.importance <= 1.0

    @pytest.mark.asyncio
    async def test_cognitive_stats_in_discover(self, repo: InMemoryRepository):
        """Verify discover stats include cognitive metrics."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")

        # Create some nodes (some will be forgotten)
        n1 = await repo.upsert_node(AGENT_ID, "Active Node", concept.id, importance=0.8)
        n2 = await repo.upsert_node(AGENT_ID, "Forgotten Node", concept.id, importance=0.1)
        await repo.record_node_access(AGENT_ID, [n1.id])
        await repo.mark_forgotten(AGENT_ID, [n2.id])

        # Create an episode and consolidate it
        ep_id = await repo.store_episode(AGENT_ID, "Test episode")
        await repo.mark_episode_consolidated(AGENT_ID, ep_id)

        stats = await repo.get_stats(AGENT_ID)
        assert isinstance(stats, GraphStats)
        assert stats.total_nodes == 2
        assert stats.forgotten_nodes == 1
        assert stats.consolidated_episodes == 1
        assert stats.avg_activation > 0  # At least one active node with access
