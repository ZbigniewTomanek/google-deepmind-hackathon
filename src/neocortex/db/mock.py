from typing import TypedDict

from neocortex.schemas.memory import GraphStats, RecallItem, TypeInfo


class EpisodeRecord(TypedDict):
    id: int
    agent_id: str
    content: str
    context: str | None
    source_type: str


class InMemoryRepository:
    """Mock repository for testing and local MCP scaffolding."""

    def __init__(self) -> None:
        self._episodes: list[EpisodeRecord] = []
        self._next_id = 1

    async def store_episode(
        self,
        agent_id: str,
        content: str,
        context: str | None = None,
        source_type: str = "mcp",
    ) -> int:
        episode_id = self._next_id
        self._next_id += 1
        self._episodes.append(
            {
                "id": episode_id,
                "agent_id": agent_id,
                "content": content,
                "context": context,
                "source_type": source_type,
            }
        )
        return episode_id

    async def recall(self, query: str, agent_id: str, limit: int = 10) -> list[RecallItem]:
        query_lower = query.lower()
        matches: list[RecallItem] = []

        for episode in self._episodes:
            if episode["agent_id"] != agent_id:
                continue
            content = str(episode["content"])
            if query_lower not in content.lower():
                continue

            matches.append(
                RecallItem(
                    node_id=int(episode["id"]),
                    name=f"Episode #{episode['id']}",
                    content=content,
                    node_type="Episode",
                    score=1.0,
                    source=str(episode["source_type"]),
                )
            )

        return matches[:limit]

    async def get_node_types(self) -> list[TypeInfo]:
        return []

    async def get_edge_types(self) -> list[TypeInfo]:
        return []

    async def get_stats(self, agent_id: str | None = None) -> GraphStats:
        del agent_id
        return GraphStats(total_nodes=0, total_edges=0, total_episodes=len(self._episodes))
