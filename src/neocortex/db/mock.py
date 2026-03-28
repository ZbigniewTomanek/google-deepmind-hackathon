from datetime import UTC, datetime
from typing import TypedDict

from neocortex.models import Edge, EdgeType, Episode, Node, NodeType
from neocortex.schemas.memory import GraphStats, RecallItem, TypeInfo


class EpisodeRecord(TypedDict, total=False):
    id: int
    agent_id: str
    content: str
    context: str | None
    source_type: str
    embedding: list[float] | None
    created_at: datetime


class InMemoryRepository:
    """Mock repository for testing and local MCP scaffolding."""

    def __init__(self) -> None:
        self._episodes: list[EpisodeRecord] = []
        self._schema_episodes: dict[str, list[EpisodeRecord]] = {}
        self._next_id = 1
        self._node_types: dict[str, NodeType] = {}  # keyed by name
        self._edge_types: dict[str, EdgeType] = {}  # keyed by name
        self._nodes: dict[int, Node] = {}  # keyed by id
        self._edges: dict[int, Edge] = {}  # keyed by id
        self._next_node_id = 1
        self._next_edge_id = 1
        self._next_type_id = 1

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
                "created_at": datetime.now(UTC),
            }
        )
        return episode_id

    async def store_episode_to(
        self,
        agent_id: str,
        target_schema: str,
        content: str,
        context: str | None = None,
        source_type: str = "mcp",
    ) -> int:
        episode_id = self._next_id
        self._next_id += 1
        record: EpisodeRecord = {
            "id": episode_id,
            "agent_id": agent_id,
            "content": content,
            "context": context,
            "source_type": source_type,
            "created_at": datetime.now(UTC),
        }
        self._episodes.append(record)
        self._schema_episodes.setdefault(target_schema, []).append(record)
        return episode_id

    async def recall(
        self, query: str, agent_id: str, limit: int = 10, query_embedding: list[float] | None = None
    ) -> list[RecallItem]:
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
        return [
            TypeInfo(
                id=nt.id,
                name=nt.name,
                description=nt.description,
                count=sum(1 for n in self._nodes.values() if n.type_id == nt.id),
            )
            for nt in sorted(self._node_types.values(), key=lambda t: t.name)
        ]

    async def get_edge_types(self, agent_id: str | None = None) -> list[TypeInfo]:
        del agent_id
        return [
            TypeInfo(
                id=et.id,
                name=et.name,
                description=et.description,
                count=sum(1 for e in self._edges.values() if e.type_id == et.id),
            )
            for et in sorted(self._edge_types.values(), key=lambda t: t.name)
        ]

    async def get_stats(self, agent_id: str | None = None) -> GraphStats:
        count = sum(1 for e in self._episodes if agent_id is None or e["agent_id"] == agent_id)
        return GraphStats(
            total_nodes=len(self._nodes),
            total_edges=len(self._edges),
            total_episodes=count,
        )

    async def update_episode_embedding(self, episode_id: int, embedding: list[float], agent_id: str) -> None:
        for episode in self._episodes:
            if episode["id"] == episode_id:
                episode["embedding"] = embedding
                return

    async def list_graphs(self, agent_id: str) -> list[str]:
        del agent_id
        return []

    # ── Type Management ──

    async def get_or_create_node_type(self, agent_id: str, name: str, description: str | None = None) -> NodeType:
        if name in self._node_types:
            return self._node_types[name]
        now = datetime.now(UTC)
        nt = NodeType(id=self._next_type_id, name=name, description=description, created_at=now)
        self._next_type_id += 1
        self._node_types[name] = nt
        return nt

    async def get_or_create_edge_type(self, agent_id: str, name: str, description: str | None = None) -> EdgeType:
        if name in self._edge_types:
            return self._edge_types[name]
        now = datetime.now(UTC)
        et = EdgeType(id=self._next_type_id, name=name, description=description, created_at=now)
        self._next_type_id += 1
        self._edge_types[name] = et
        return et

    # ── Episode Read ──

    async def get_episode(self, agent_id: str, episode_id: int) -> Episode | None:
        for ep in self._episodes:
            if ep["id"] == episode_id and ep["agent_id"] == agent_id:
                return Episode(
                    id=ep["id"],
                    agent_id=ep["agent_id"],
                    content=ep["content"],
                    embedding=ep.get("embedding"),
                    source_type=ep.get("source_type"),
                    metadata={"context": ep.get("context")} if ep.get("context") else {},
                    created_at=ep.get("created_at", datetime.now(UTC)),
                )
        return None

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
    ) -> Node:
        props = properties or {}
        # Look for existing node by (name, type_id)
        for node in self._nodes.values():
            if node.name.lower() == name.lower() and node.type_id == type_id:
                merged_props = {**node.properties, **props}
                updated = Node(
                    id=node.id,
                    type_id=node.type_id,
                    name=name,
                    content=content or node.content,
                    properties=merged_props,
                    embedding=embedding or node.embedding,
                    source=source or node.source,
                    created_at=node.created_at,
                    updated_at=datetime.now(UTC),
                )
                self._nodes[node.id] = updated
                return updated
        now = datetime.now(UTC)
        node = Node(
            id=self._next_node_id,
            type_id=type_id,
            name=name,
            content=content,
            properties=props,
            embedding=embedding,
            source=source,
            created_at=now,
            updated_at=now,
        )
        self._next_node_id += 1
        self._nodes[node.id] = node
        return node

    async def find_nodes_by_name(self, agent_id: str, name: str) -> list[Node]:
        return [n for n in self._nodes.values() if n.name.lower() == name.lower()]

    # ── Edge CRUD ──

    async def upsert_edge(
        self,
        agent_id: str,
        source_id: int,
        target_id: int,
        type_id: int,
        weight: float = 1.0,
        properties: dict | None = None,
    ) -> Edge:
        props = properties or {}
        # Look for existing edge by (source_id, target_id, type_id)
        for edge in self._edges.values():
            if edge.source_id == source_id and edge.target_id == target_id and edge.type_id == type_id:
                merged_props = {**edge.properties, **props}
                updated = Edge(
                    id=edge.id,
                    source_id=source_id,
                    target_id=target_id,
                    type_id=type_id,
                    weight=weight,
                    properties=merged_props,
                    created_at=edge.created_at,
                )
                self._edges[edge.id] = updated
                return updated
        now = datetime.now(UTC)
        edge = Edge(
            id=self._next_edge_id,
            source_id=source_id,
            target_id=target_id,
            type_id=type_id,
            weight=weight,
            properties=props,
            created_at=now,
        )
        self._next_edge_id += 1
        self._edges[edge.id] = edge
        return edge

    # ── Node Search ──

    async def search_nodes(
        self,
        agent_id: str,
        query: str,
        limit: int = 5,
        query_embedding: list[float] | None = None,
    ) -> list[Node]:
        query_lower = query.lower()
        matches: list[Node] = []
        for node in self._nodes.values():
            name_match = query_lower in node.name.lower()
            content_match = node.content and query_lower in node.content.lower()
            if name_match or content_match:
                matches.append(node)
        return matches[:limit]

    # ── Graph Traversal ──

    async def get_node_neighborhood(self, agent_id: str, node_id: int, depth: int = 2) -> list[dict]:
        visited: set[int] = {node_id}
        results: list[dict] = []
        current_frontier = [node_id]

        for dist in range(1, depth + 1):
            next_frontier: list[int] = []
            for nid in current_frontier:
                for edge in self._edges.values():
                    neighbor_id: int | None = None
                    if edge.source_id == nid and edge.target_id not in visited:
                        neighbor_id = edge.target_id
                    elif edge.target_id == nid and edge.source_id not in visited:
                        neighbor_id = edge.source_id

                    if neighbor_id is not None and neighbor_id in self._nodes:
                        visited.add(neighbor_id)
                        next_frontier.append(neighbor_id)
                        results.append(
                            {
                                "node": self._nodes[neighbor_id],
                                "edges": [edge],
                                "distance": dist,
                            }
                        )
            current_frontier = next_frontier
            if not current_frontier:
                break

        return results

    # ── Bulk Queries ──

    async def list_all_node_names(self, agent_id: str) -> list[str]:
        return sorted(n.name for n in self._nodes.values())

    async def list_all_edge_signatures(self, agent_id: str) -> list[str]:
        sigs = []
        for edge in self._edges.values():
            src = self._nodes.get(edge.source_id)
            tgt = self._nodes.get(edge.target_id)
            et = None
            for et_val in self._edge_types.values():
                if et_val.id == edge.type_id:
                    et = et_val
                    break
            if src and tgt and et:
                sigs.append(f"{src.name}→{et.name}→{tgt.name}")
        return sorted(sigs)
