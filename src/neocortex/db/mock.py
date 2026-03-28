from datetime import UTC, datetime
from typing import TypedDict

from neocortex.models import Edge, EdgeType, Episode, Node, NodeType
from neocortex.schemas.memory import GraphStats, RecallItem, TypeInfo
from neocortex.scoring import (
    HybridWeights,
    compute_base_activation,
    compute_hybrid_score,
    compute_recency_score,
)


class EpisodeRecord(TypedDict, total=False):
    id: int
    agent_id: str
    content: str
    context: str | None
    source_type: str
    metadata: dict
    embedding: list[float] | None
    created_at: datetime
    access_count: int
    last_accessed_at: datetime
    importance: float


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
        metadata: dict | None = None,
        importance: float = 0.5,
    ) -> int:
        episode_id = self._next_id
        self._next_id += 1
        now = datetime.now(UTC)
        episode_metadata = metadata or {}
        if context:
            episode_metadata["context"] = context
        self._episodes.append(
            {
                "id": episode_id,
                "agent_id": agent_id,
                "content": content,
                "context": context,
                "source_type": source_type,
                "metadata": episode_metadata,
                "created_at": now,
                "access_count": 0,
                "last_accessed_at": now,
                "importance": importance,
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
        weights = HybridWeights(vector=0.3, text=0.2, recency=0.1, activation=0.25, importance=0.15)
        half_life = 168.0  # 7 days
        matches: list[RecallItem] = []

        # Match episodes
        for episode in self._episodes:
            if episode["agent_id"] != agent_id:
                continue
            content = str(episode["content"])
            if query_lower not in content.lower():
                continue

            created_at = episode.get("created_at", datetime.now(UTC))
            recency = compute_recency_score(created_at, half_life)

            access_count = episode.get("access_count", 0)
            last_accessed_at = episode.get("last_accessed_at", created_at)
            activation = compute_base_activation(access_count, last_accessed_at)

            importance_val = episode.get("importance", 0.5)
            score = compute_hybrid_score(
                vector_sim=None,
                text_rank=None,
                recency=recency,
                activation=activation,
                importance=importance_val,
                weights=weights,
            )

            matches.append(
                RecallItem(
                    item_id=int(episode["id"]),
                    name=f"Episode #{episode['id']}",
                    content=content,
                    item_type="Episode",
                    score=score,
                    activation_score=activation,
                    importance=importance_val,
                    source=str(episode["source_type"]),
                    source_kind="episode",
                    graph_name=None,
                )
            )

        # Match nodes
        for node in self._nodes.values():
            name_match = query_lower in node.name.lower()
            content_match = node.content and query_lower in node.content.lower()
            if not (name_match or content_match):
                continue

            recency = compute_recency_score(node.created_at, half_life)
            last_acc = node.last_accessed_at or node.created_at
            activation = compute_base_activation(node.access_count, last_acc)
            score = compute_hybrid_score(
                vector_sim=None,
                text_rank=None,
                recency=recency,
                activation=activation,
                importance=node.importance,
                weights=weights,
            )

            matches.append(
                RecallItem(
                    item_id=node.id,
                    name=node.name,
                    content=node.content or "",
                    item_type="Node",
                    score=score,
                    activation_score=activation,
                    importance=node.importance,
                    source=node.source,
                    source_kind="node",
                    graph_name=None,
                )
            )

        matches.sort(key=lambda item: item.score, reverse=True)
        return matches[:limit]

    async def get_node_types(self, agent_id: str | None = None, target_schema: str | None = None) -> list[TypeInfo]:
        del agent_id, target_schema
        return [
            TypeInfo(
                id=nt.id,
                name=nt.name,
                description=nt.description,
                count=sum(1 for n in self._nodes.values() if n.type_id == nt.id),
            )
            for nt in sorted(self._node_types.values(), key=lambda t: t.name)
        ]

    async def get_edge_types(self, agent_id: str | None = None, target_schema: str | None = None) -> list[TypeInfo]:
        del agent_id, target_schema
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

    async def update_episode_embedding(
        self, episode_id: int, embedding: list[float], agent_id: str, target_schema: str | None = None
    ) -> None:
        # When target_schema is set, search the schema-bucketed episodes first
        if target_schema and target_schema in self._schema_episodes:
            for episode in self._schema_episodes[target_schema]:
                if episode["id"] == episode_id:
                    episode["embedding"] = embedding
                    return
        for episode in self._episodes:
            if episode["id"] == episode_id:
                episode["embedding"] = embedding
                return

    async def list_graphs(self, agent_id: str) -> list[str]:
        del agent_id
        return []

    # ── Type Management ──

    async def get_or_create_node_type(
        self, agent_id: str, name: str, description: str | None = None, target_schema: str | None = None
    ) -> NodeType:
        del target_schema
        if name in self._node_types:
            return self._node_types[name]
        now = datetime.now(UTC)
        nt = NodeType(id=self._next_type_id, name=name, description=description, created_at=now)
        self._next_type_id += 1
        self._node_types[name] = nt
        return nt

    async def get_or_create_edge_type(
        self, agent_id: str, name: str, description: str | None = None, target_schema: str | None = None
    ) -> EdgeType:
        del target_schema
        if name in self._edge_types:
            return self._edge_types[name]
        now = datetime.now(UTC)
        et = EdgeType(id=self._next_type_id, name=name, description=description, created_at=now)
        self._next_type_id += 1
        self._edge_types[name] = et
        return et

    # ── Episode Read ──

    async def get_episode(self, agent_id: str, episode_id: int, target_schema: str | None = None) -> Episode | None:
        # When target_schema is set, search the schema-bucketed episodes first
        episodes = self._schema_episodes.get(target_schema, []) if target_schema else self._episodes
        for ep in episodes:
            if ep["id"] == episode_id and ep["agent_id"] == agent_id:
                return Episode(
                    id=ep["id"],
                    agent_id=ep["agent_id"],
                    content=ep["content"],
                    embedding=ep.get("embedding"),
                    source_type=ep.get("source_type"),
                    metadata=ep.get("metadata", {}),
                    access_count=ep.get("access_count", 0),
                    last_accessed_at=ep.get("last_accessed_at"),
                    importance=ep.get("importance", 0.5),
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
        target_schema: str | None = None,
        importance: float = 0.5,
    ) -> Node:
        del target_schema
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
                    importance=max(node.importance, importance),
                    access_count=node.access_count,
                    last_accessed_at=node.last_accessed_at,
                    forgotten=node.forgotten,
                    forgotten_at=node.forgotten_at,
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
            importance=importance,
            created_at=now,
            updated_at=now,
        )
        self._next_node_id += 1
        self._nodes[node.id] = node
        return node

    async def find_nodes_by_name(self, agent_id: str, name: str, target_schema: str | None = None) -> list[Node]:
        del target_schema
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
        target_schema: str | None = None,
    ) -> Edge:
        del target_schema
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

    async def list_all_node_names(self, agent_id: str, target_schema: str | None = None) -> list[str]:
        del target_schema
        return sorted(n.name for n in self._nodes.values())

    # ── Access Tracking ──

    async def record_node_access(self, agent_id: str, node_ids: list[int]) -> None:
        now = datetime.now(UTC)
        for nid in node_ids:
            node = self._nodes.get(nid)
            if node is not None:
                self._nodes[nid] = node.model_copy(
                    update={"access_count": node.access_count + 1, "last_accessed_at": now}
                )

    async def record_episode_access(self, agent_id: str, episode_ids: list[int]) -> None:
        now = datetime.now(UTC)
        for ep in self._episodes:
            if ep["id"] in episode_ids:
                ep["access_count"] = ep.get("access_count", 0) + 1
                ep["last_accessed_at"] = now

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
