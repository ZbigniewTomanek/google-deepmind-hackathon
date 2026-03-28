"""E2E tests for cognitive heuristics — built incrementally, one TestStageN class per plan stage."""

from datetime import UTC, datetime, timedelta

import pytest

from neocortex.db.mock import InMemoryRepository
from neocortex.mcp_settings import MCPSettings
from neocortex.models import Edge, Episode, Node
from neocortex.schemas.memory import RecallItem
from neocortex.scoring import HybridWeights, compute_base_activation, compute_hybrid_score

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
