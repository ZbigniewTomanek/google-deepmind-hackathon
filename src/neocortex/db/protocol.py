from typing import Protocol

from neocortex.schemas.memory import GraphStats, RecallItem, TypeInfo


class MemoryRepository(Protocol):
    """Abstract interface for NeoCortex storage backends."""

    async def store_episode(
        self,
        agent_id: str,
        content: str,
        context: str | None = None,
        source_type: str = "mcp",
    ) -> int:
        """Store a raw episode and return the episode ID."""

    async def recall(self, query: str, agent_id: str, limit: int = 10) -> list[RecallItem]:
        """Return ranked recall results for an agent."""

    async def get_node_types(self, agent_id: str | None = None) -> list[TypeInfo]:
        """Return available node types."""

    async def get_edge_types(self, agent_id: str | None = None) -> list[TypeInfo]:
        """Return available edge types."""

    async def get_stats(self, agent_id: str | None = None) -> GraphStats:
        """Return graph summary statistics."""

    async def list_graphs(self, agent_id: str) -> list[str]:
        """Return graph schemas accessible to the agent."""
