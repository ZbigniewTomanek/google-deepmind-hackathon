from typing import Protocol

from neocortex.models import Edge, EdgeType, Episode, Node, NodeType
from neocortex.schemas.memory import GraphStats, RecallItem, TypeInfo


class MemoryRepository(Protocol):
    """Abstract interface for NeoCortex storage backends."""

    async def store_episode(
        self,
        agent_id: str,
        content: str,
        context: str | None = None,
        source_type: str = "mcp",
        metadata: dict | None = None,
        importance: float = 0.5,
    ) -> int:
        """Store a raw episode and return the episode ID."""

    async def store_episode_to(
        self,
        agent_id: str,
        target_schema: str,
        content: str,
        context: str | None = None,
        source_type: str = "mcp",
    ) -> int:
        """Store an episode in an explicit target schema (for shared graph writes)."""

    async def recall(
        self, query: str, agent_id: str, limit: int = 10, query_embedding: list[float] | None = None
    ) -> list[RecallItem]:
        """Return ranked recall results for an agent."""

    async def get_node_types(self, agent_id: str | None = None, target_schema: str | None = None) -> list[TypeInfo]:
        """Return available node types."""

    async def get_edge_types(self, agent_id: str | None = None, target_schema: str | None = None) -> list[TypeInfo]:
        """Return available edge types."""

    async def get_stats(self, agent_id: str | None = None) -> GraphStats:
        """Return graph summary statistics."""

    async def update_episode_embedding(
        self, episode_id: int, embedding: list[float], agent_id: str, target_schema: str | None = None
    ) -> None:
        """Attach a vector embedding to an existing episode."""

    async def list_graphs(self, agent_id: str) -> list[str]:
        """Return graph schemas accessible to the agent."""

    # ── Type Management ──

    async def get_or_create_node_type(
        self, agent_id: str, name: str, description: str | None = None, target_schema: str | None = None
    ) -> NodeType:
        """Return existing node type by name or create a new one."""

    async def get_or_create_edge_type(
        self, agent_id: str, name: str, description: str | None = None, target_schema: str | None = None
    ) -> EdgeType:
        """Return existing edge type by name or create a new one."""

    # ── Episode Read ──

    async def get_episode(self, agent_id: str, episode_id: int, target_schema: str | None = None) -> Episode | None:
        """Fetch a single episode by ID within the agent's schema or a target schema."""

    # ── Node CRUD ──

    async def upsert_node(
        self,
        agent_id: str,
        name: str,
        type_id: int,
        content: str | None = None,
        properties: dict | None = None,
        embedding: list[float] | None = None,
        source: str | None = None,
        target_schema: str | None = None,
        importance: float = 0.5,
    ) -> Node:
        """Upsert by (name, type_id) within the agent's schema.

        If a node with the same name AND type_id exists, merge properties and update.
        Importance uses max semantics — it only goes up.
        Name alone is NOT the uniqueness key — the same name under different types
        creates separate nodes (e.g. 'Serotonin' as Neurotransmitter vs Drug).
        """

    async def find_nodes_by_name(self, agent_id: str, name: str, target_schema: str | None = None) -> list[Node]:
        """Return all nodes matching ``name`` (case-insensitive) across all types."""

    # ── Edge CRUD ──

    async def upsert_edge(
        self,
        agent_id: str,
        source_id: int,
        target_id: int,
        type_id: int,
        weight: float = 1.0,
        properties: dict | None = None,
        target_schema: str | None = None,
    ) -> Edge:
        """Upsert by (source_id, target_id, type_id) within the agent's schema.

        If an edge with the same triple exists, merge properties and update weight.
        """

    # ── Node Search ──

    async def search_nodes(
        self,
        agent_id: str,
        query: str,
        limit: int = 5,
        query_embedding: list[float] | None = None,
    ) -> list[tuple[Node, float]]:
        """Search nodes by text and/or vector similarity.

        Combines text search on node names/content with vector similarity
        on node embeddings. Returns top-N matching (node, relevance_score) tuples.
        """

    # ── Graph Traversal ──

    async def get_node_neighborhood(self, agent_id: str, node_id: int, depth: int = 2) -> list[dict]:
        """BFS traversal up to ``depth`` hops.

        Returns list of ``{node: Node, edges: list[Edge], distance: int}``.
        """

    # ── Bulk Queries (for extraction pipeline) ──

    async def list_all_node_names(self, agent_id: str, target_schema: str | None = None) -> list[str]:
        """Return all node names in the agent's graph."""

    async def list_all_edge_signatures(self, agent_id: str) -> list[str]:
        """Return all edge signatures (source→type→target) in the agent's graph."""

    # ── Access Tracking ──

    async def record_node_access(self, agent_id: str, node_ids: list[int]) -> None:
        """Increment access_count and update last_accessed_at for recalled nodes."""

    async def record_episode_access(self, agent_id: str, episode_ids: list[int]) -> None:
        """Increment access_count and update last_accessed_at for recalled episodes."""

    # ── Edge Reinforcement ──

    async def reinforce_edges(
        self, agent_id: str, edge_ids: list[int], delta: float = 0.05, ceiling: float = 2.0
    ) -> None:
        """Increment edge weights for traversed edges, capped at ceiling."""

    async def decay_stale_edges(
        self,
        agent_id: str,
        older_than_hours: float = 168.0,
        decay_factor: float = 0.95,
        floor: float = 0.1,
        force: bool = False,
    ) -> int:
        """Decay weights of edges not recently reinforced. Returns count of decayed edges.

        Uses last_reinforced_at (not created_at) to target edges that haven't
        been traversed recently. The force parameter bypasses probabilistic
        gating for deterministic testing.
        """
