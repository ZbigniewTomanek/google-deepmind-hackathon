import json

import asyncpg

from neocortex.db.scoped import scoped_connection
from neocortex.graph_service import GraphService
from neocortex.schemas.memory import GraphStats, RecallItem, TypeInfo


class GraphServiceAdapter:
    """Adapt GraphService to the MemoryRepository protocol."""

    def __init__(self, graph: GraphService, pool: asyncpg.Pool | None = None):
        self._graph = graph
        self._pool = pool

    async def store_episode(
        self,
        agent_id: str,
        content: str,
        context: str | None = None,
        source_type: str = "mcp",
    ) -> int:
        metadata = {"context": context} if context else {}
        if self._pool is None:
            episode = await self._graph.create_episode(
                agent_id=agent_id,
                content=content,
                source_type=source_type,
                metadata=metadata,
            )
            return episode.id

        async with scoped_connection(self._pool, agent_id) as conn:
            row = await conn.fetchrow(
                """INSERT INTO episode (agent_id, content, source_type, metadata)
                   VALUES ($1, $2, $3, $4::jsonb)
                   RETURNING id""",
                agent_id,
                content,
                source_type,
                json.dumps(metadata),
            )
        if row is None:
            raise RuntimeError("Failed to store episode.")
        return int(row["id"])

    async def recall(self, query: str, agent_id: str, limit: int = 10) -> list[RecallItem]:
        if self._pool is None:
            return await self._recall_via_graph(query=query, agent_id=agent_id, limit=limit)

        async with scoped_connection(self._pool, agent_id) as conn:
            node_rows = await conn.fetch(
                """SELECT
                       id,
                       name,
                       content,
                       source,
                       type_id,
                       ts_rank(tsv, plainto_tsquery('english', $1)) AS rank
                   FROM node
                   WHERE tsv @@ plainto_tsquery('english', $1)
                   ORDER BY rank DESC
                   LIMIT $2""",
                query,
                limit,
            )
            episode_rows = await conn.fetch(
                """SELECT id, content, source_type, created_at
                   FROM episode
                   WHERE content ILIKE '%' || $1 || '%'
                   ORDER BY created_at DESC
                   LIMIT $2""",
                query,
                limit,
            )
            type_rows = await conn.fetch("SELECT id, name FROM node_type")

        type_names = {int(row["id"]): str(row["name"]) for row in type_rows}
        node_results = [
            RecallItem(
                node_id=int(row["id"]),
                name=str(row["name"]),
                content=str(row["content"] or ""),
                node_type=type_names.get(int(row["type_id"]), "Unknown"),
                score=float(row["rank"] or 0.0),
                source=str(row["source"]) if row["source"] is not None else None,
            )
            for row in node_rows
        ]
        episode_results = [
            RecallItem(
                node_id=int(row["id"]),
                name=f"Episode #{int(row['id'])}",
                content=str(row["content"]),
                node_type="Episode",
                score=0.5,
                source=str(row["source_type"]) if row["source_type"] is not None else None,
            )
            for row in episode_rows
        ]
        return (node_results + episode_results)[:limit]

    async def get_node_types(self) -> list[TypeInfo]:
        return await self._get_types(table_name="node_type")

    async def get_edge_types(self) -> list[TypeInfo]:
        return await self._get_types(table_name="edge_type")

    async def get_stats(self, agent_id: str | None = None) -> GraphStats:
        if self._pool is None or agent_id is None:
            stats = await self._graph.get_ontology_stats()
            return GraphStats(
                total_nodes=int(stats["total_nodes"]),
                total_edges=int(stats["total_edges"]),
                total_episodes=int(stats["total_episodes"]),
            )

        async with scoped_connection(self._pool, agent_id) as conn:
            row = await conn.fetchrow("""SELECT
                       (SELECT count(*) FROM node) AS total_nodes,
                       (SELECT count(*) FROM edge) AS total_edges,
                       (SELECT count(*) FROM episode) AS total_episodes""")
        if row is None:
            raise RuntimeError("Failed to fetch graph stats.")

        return GraphStats(
            total_nodes=int(row["total_nodes"]),
            total_edges=int(row["total_edges"]),
            total_episodes=int(row["total_episodes"]),
        )

    async def _recall_via_graph(self, query: str, agent_id: str, limit: int) -> list[RecallItem]:
        hits = await self._graph.search_by_text(query, limit=limit)
        episodes = await self._graph.list_episodes(agent_id=agent_id, limit=max(limit * 5, 20))
        type_ids = {int(hit["type_id"]) for hit in hits}
        type_names = await self._get_type_names(type_ids)
        node_results = [
            RecallItem(
                node_id=int(hit["id"]),
                name=str(hit["name"]),
                content=str(hit.get("content") or ""),
                node_type=type_names.get(int(hit["type_id"]), "Unknown"),
                score=float(hit.get("rank") or 0.0),
                source=str(hit["source"]) if hit.get("source") is not None else None,
            )
            for hit in hits
        ]
        query_lower = query.lower()
        episode_results = [
            RecallItem(
                node_id=episode.id,
                name=f"Episode #{episode.id}",
                content=episode.content,
                node_type="Episode",
                score=0.5,
                source=episode.source_type,
            )
            for episode in episodes
            if query_lower in episode.content.lower()
        ]
        return (node_results + episode_results)[:limit]

    async def _get_type_names(self, type_ids: set[int]) -> dict[int, str]:
        if not type_ids:
            return {}

        names: dict[int, str] = {}
        for type_id in type_ids:
            node_type = await self._graph.get_node_type(type_id)
            if node_type is not None:
                names[type_id] = node_type.name
        return names

    async def _get_types(self, table_name: str) -> list[TypeInfo]:
        if self._pool is None:
            stats = await self._graph.get_ontology_stats()
            key = "node_types" if table_name == "node_type" else "edge_types"
            return [
                TypeInfo(
                    id=index,
                    name=str(item["type_name"]),
                    count=int(item["count"]),
                )
                for index, item in enumerate(stats[key], start=1)
            ]

        rows = await self._graph._pg.fetch(f"SELECT id, name, description FROM {table_name} ORDER BY name")
        count_table = "node" if table_name == "node_type" else "edge"
        foreign_key = "type_id"
        counts = await self._graph._pg.fetch(
            f"SELECT {foreign_key} AS id, count(*) AS count FROM {count_table} GROUP BY {foreign_key}"
        )
        count_map = {int(row["id"]): int(row["count"]) for row in counts}

        return [
            TypeInfo(
                id=int(row["id"]),
                name=str(row["name"]),
                description=str(row["description"]) if row["description"] is not None else None,
                count=count_map.get(int(row["id"]), 0),
            )
            for row in rows
        ]
