from typing import TypedDict

from neocortex.schemas.memory import GraphStats, RecallItem, TypeInfo


class EpisodeRecord(TypedDict, total=False):
    id: int
    agent_id: str
    content: str
    context: str | None
    source_type: str
    embedding: list[float] | None


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
                    item_id=int(episode["id"]),
                    name=f"Episode #{episode['id']}",
                    content=content,
                    item_type="Episode",
                    score=1.0,
                    source=str(episode["source_type"]),
                    source_kind="episode",
                    graph_name=None,
                )
            )

        return matches[:limit]

    async def get_node_types(self, agent_id: str | None = None) -> list[TypeInfo]:
        del agent_id
        return []

    async def get_edge_types(self, agent_id: str | None = None) -> list[TypeInfo]:
        del agent_id
        return []

    async def get_stats(self, agent_id: str | None = None) -> GraphStats:
        count = sum(1 for e in self._episodes if agent_id is None or e["agent_id"] == agent_id)
        return GraphStats(total_nodes=0, total_edges=0, total_episodes=count)

    async def update_episode_embedding(self, episode_id: int, embedding: list[float], agent_id: str) -> None:
        for episode in self._episodes:
            if episode["id"] == episode_id:
                episode["embedding"] = embedding
                return

    async def list_graphs(self, agent_id: str) -> list[str]:
        del agent_id
        return []
