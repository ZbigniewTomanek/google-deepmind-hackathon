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

    async def get_node_types(self) -> list[TypeInfo]:
        """Return available node types."""

    async def get_edge_types(self) -> list[TypeInfo]:
        """Return available edge types."""

    async def get_stats(self) -> GraphStats:
        """Return graph summary statistics."""
