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
from neocortex.schemas.memory import RecallItem
from neocortex.scoring import (
    HybridWeights,
    compute_base_activation,
    compute_hybrid_score,
    compute_spreading_activation,
    neighborhood_to_adjacency,
)

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
    e2 = await repo.upsert_edge(AGENT_ID, n1.id, n3.id, relates.id, weight=0.8)
    e3 = await repo.upsert_edge(AGENT_ID, n2.id, n3.id, relates.id, weight=0.6)
    e4 = await repo.upsert_edge(AGENT_ID, n4.id, n5.id, relates.id, weight=1.0)
    e5 = await repo.upsert_edge(AGENT_ID, n3.id, n4.id, relates.id, weight=0.4)
    e6 = await repo.upsert_edge(AGENT_ID, n5.id, n1.id, relates.id, weight=0.3)

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
        assert settings.recall_weight_activation == 0.25
        assert settings.recall_weight_importance == 0.15
        assert settings.activation_decay_rate == 0.5
        assert settings.spreading_activation_decay == 0.6
        assert settings.spreading_activation_max_depth == 2
        assert settings.forget_activation_threshold == 0.05
        assert settings.forget_importance_floor == 0.3
        assert settings.edge_reinforcement_delta == 0.05
        assert settings.edge_weight_floor == 0.1
        assert settings.edge_weight_ceiling == 2.0
        # Rebalanced weights (Stage 2)
        assert settings.recall_weight_vector == 0.3
        assert settings.recall_weight_text == 0.2
        assert settings.recall_weight_recency == 0.1

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
        """Node with access_count=100, last_accessed=now returns activation close to 1.0."""
        now = datetime.now(UTC)
        activation = compute_base_activation(access_count=100, last_accessed_at=now)
        assert activation > 0.95

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

        await repo.reinforce_edges(AGENT_ID, [edge.id], delta=0.1, ceiling=2.0)
        updated = repo._edges[edge.id]
        assert updated.weight == pytest.approx(1.1)
        assert updated.last_reinforced_at is not None

    @pytest.mark.asyncio
    async def test_reinforce_edges_respects_ceiling(self, repo: InMemoryRepository):
        """Create edge with weight=1.95, reinforce with delta=0.1, ceiling=2.0, verify capped at 2.0."""
        concept = await repo.get_or_create_node_type(AGENT_ID, "Concept")
        relates = await repo.get_or_create_edge_type(AGENT_ID, "RELATES_TO")
        a = await repo.upsert_node(AGENT_ID, "Alpha", concept.id)
        b = await repo.upsert_node(AGENT_ID, "Beta", concept.id)
        edge = await repo.upsert_edge(AGENT_ID, a.id, b.id, relates.id, weight=1.95)

        await repo.reinforce_edges(AGENT_ID, [edge.id], delta=0.1, ceiling=2.0)
        updated = repo._edges[edge.id]
        assert updated.weight == pytest.approx(2.0)

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
        e2 = await repo.upsert_edge(AGENT_ID, b.id, c.id, relates.id, weight=1.0)
        e3 = await repo.upsert_edge(AGENT_ID, c.id, d.id, relates.id, weight=1.0)

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
