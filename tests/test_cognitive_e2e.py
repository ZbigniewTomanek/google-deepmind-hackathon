"""E2E tests for cognitive heuristics — built incrementally, one TestStageN class per plan stage."""

from datetime import UTC, datetime

import pytest

from neocortex.db.mock import InMemoryRepository
from neocortex.mcp_settings import MCPSettings
from neocortex.models import Edge, Episode, Node
from neocortex.schemas.memory import RecallItem

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
        # Existing weights unchanged
        assert settings.recall_weight_vector == 0.4
        assert settings.recall_weight_text == 0.35
        assert settings.recall_weight_recency == 0.25

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
