from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from typing import TYPE_CHECKING

import asyncpg

from neocortex.db.scoped import graph_scoped_connection, schema_scoped_connection
from neocortex.graph_service import GraphService
from neocortex.mcp_settings import MCPSettings
from neocortex.postgres_service import PostgresService
from neocortex.schemas.memory import GraphStats, RecallItem, TypeInfo
from neocortex.scoring import HybridWeights, compute_hybrid_score, compute_recency_score

if TYPE_CHECKING:
    from neocortex.graph_router import GraphRouter


def _escape_ilike(query: str) -> str:
    """Escape special ILIKE characters for use with ``ESCAPE '\\'``."""
    return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class GraphServiceAdapter:
    """Adapt GraphService to the MemoryRepository protocol."""

    def __init__(
        self,
        graph: GraphService,
        router: GraphRouter | None = None,
        pool: asyncpg.Pool | None = None,
        pg: PostgresService | None = None,
        settings: MCPSettings | None = None,
    ):
        self._graph = graph
        self._router = router
        self._pool = pool
        self._pg = pg
        self._settings = settings or MCPSettings()

    async def store_episode(
        self,
        agent_id: str,
        content: str,
        context: str | None = None,
        source_type: str = "mcp",
    ) -> int:
        metadata = {"context": context} if context else {}
        if self._pool is None or self._router is None:
            episode = await self._graph.create_episode(
                agent_id=agent_id,
                content=content,
                source_type=source_type,
                metadata=metadata,
            )
            return episode.id

        schema_name = await self._router.route_store(agent_id)
        async with schema_scoped_connection(self._pool, schema_name) as conn:
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

    async def recall(
        self, query: str, agent_id: str, limit: int = 10, query_embedding: list[float] | None = None
    ) -> list[RecallItem]:
        if self._pool is None or self._router is None:
            return await self._recall_via_graph(
                query=query, agent_id=agent_id, limit=limit, query_embedding=query_embedding
            )

        schemas = await self._router.route_recall(agent_id)
        results_per_schema = await asyncio.gather(
            *(
                self._recall_in_schema(schema_name, query, agent_id, limit, query_embedding=query_embedding)
                for schema_name in schemas
            )
        )
        merged_results = [item for batch in results_per_schema for item in batch]
        merged_results.sort(key=lambda item: (item.score, item.source_kind == "node"), reverse=True)
        return _deduplicate_recall_items(merged_results)[:limit]

    async def update_episode_embedding(self, episode_id: int, embedding: list[float], agent_id: str) -> None:
        emb_str = str(embedding)
        if self._pool is None or self._router is None:
            if self._pg is None:
                raise RuntimeError("No database connection available for update_episode_embedding.")
            await self._pg.execute(
                "UPDATE episode SET embedding = $1::vector WHERE id = $2",
                emb_str,
                episode_id,
            )
            return
        schema_name = await self._router.route_store(agent_id)
        async with schema_scoped_connection(self._pool, schema_name) as conn:
            await conn.execute(
                "UPDATE episode SET embedding = $1::vector WHERE id = $2",
                emb_str,
                episode_id,
            )

    async def get_node_types(self, agent_id: str | None = None) -> list[TypeInfo]:
        return await self._get_types(table_name="node_type", count_table="node", agent_id=agent_id)

    async def get_edge_types(self, agent_id: str | None = None) -> list[TypeInfo]:
        return await self._get_types(table_name="edge_type", count_table="edge", agent_id=agent_id)

    async def get_stats(self, agent_id: str | None = None) -> GraphStats:
        if self._pool is None or self._router is None or agent_id is None:
            stats = await self._graph.get_ontology_stats()
            return GraphStats(
                total_nodes=int(stats["total_nodes"]),
                total_edges=int(stats["total_edges"]),
                total_episodes=int(stats["total_episodes"]),
            )

        schemas = await self._router.route_discover(agent_id)
        totals = GraphStats(total_nodes=0, total_edges=0, total_episodes=0)
        for schema_name in schemas:
            schema_stats = await self._get_stats_in_schema(schema_name, agent_id)
            totals.total_nodes += schema_stats.total_nodes
            totals.total_edges += schema_stats.total_edges
            totals.total_episodes += schema_stats.total_episodes
        return totals

    async def list_graphs(self, agent_id: str) -> list[str]:
        if self._router is None:
            return []
        return await self._router.route_discover(agent_id)

    async def _recall_via_graph(
        self, query: str, agent_id: str, limit: int, query_embedding: list[float] | None = None
    ) -> list[RecallItem]:
        weights = HybridWeights(
            vector=self._settings.recall_weight_vector,
            text=self._settings.recall_weight_text,
            recency=self._settings.recall_weight_recency,
        )
        half_life = self._settings.recall_recency_half_life_hours

        # 1. Text search (existing) — returns nodes with ts_rank
        text_hits = await self._graph.search_by_text(query, limit=limit)

        # 2. Vector search (new) — returns nodes with cosine similarity
        vector_hits: list[dict] = []
        if query_embedding is not None:
            vector_hits = await self._graph.search_by_vector(query_embedding, limit=limit)

        # 3. Episode search — text (ILIKE, existing) + vector (new)
        episodes = await self._graph.list_episodes(agent_id=agent_id, limit=max(limit * 5, 20))
        vector_episodes: list[dict] = []
        if query_embedding is not None:
            vector_episodes = await self._graph.search_episodes_by_vector(
                query_embedding, agent_id=agent_id, limit=limit
            )

        # 4. Collect all type ids for name resolution
        type_ids = {int(hit["type_id"]) for hit in text_hits}
        type_ids |= {int(hit["type_id"]) for hit in vector_hits}
        type_names = await self._get_type_names(type_ids)

        # 5. Merge nodes into a single dict keyed by id
        merged_nodes: dict[int, dict] = {}
        for hit in text_hits:
            nid = int(hit["id"])
            merged_nodes[nid] = {
                "hit": hit,
                "text_rank": float(hit.get("rank") or 0.0),
                "vector_sim": None,
            }
        for hit in vector_hits:
            nid = int(hit["id"])
            if nid in merged_nodes:
                merged_nodes[nid]["vector_sim"] = float(hit.get("similarity") or 0.0)
            else:
                merged_nodes[nid] = {
                    "hit": hit,
                    "text_rank": None,
                    "vector_sim": float(hit.get("similarity") or 0.0),
                }

        # 6. Score nodes
        node_results: list[RecallItem] = []
        for nid, info in merged_nodes.items():
            hit = info["hit"]
            created_at = hit.get("created_at")
            recency = compute_recency_score(created_at, half_life) if created_at else 0.5
            score = compute_hybrid_score(info["vector_sim"], info["text_rank"], recency, weights)
            node_results.append(
                RecallItem(
                    item_id=nid,
                    name=str(hit["name"]),
                    content=str(hit.get("content") or ""),
                    item_type=type_names.get(int(hit["type_id"]), "Unknown"),
                    score=score,
                    source=str(hit["source"]) if hit.get("source") is not None else None,
                    source_kind="node",
                    graph_name=None,
                )
            )

        # 7. Merge episodes — text matches + vector matches
        query_lower = query.lower()
        merged_episodes: dict[int, dict] = {}
        for episode in episodes:
            if query_lower in episode.content.lower():
                merged_episodes[episode.id] = {
                    "episode": episode,
                    "text_rank": None,  # episodes don't have tsvector
                    "vector_sim": None,
                }
        for hit in vector_episodes:
            eid = int(hit["id"])
            if eid in merged_episodes:
                merged_episodes[eid]["vector_sim"] = float(hit.get("similarity") or 0.0)
            else:
                # Build a minimal episode-like object for scoring
                merged_episodes[eid] = {
                    "episode": hit,
                    "text_rank": None,
                    "vector_sim": float(hit.get("similarity") or 0.0),
                }

        # 8. Score episodes
        episode_results: list[RecallItem] = []
        for eid, info in merged_episodes.items():
            ep = info["episode"]
            created_at = ep.created_at if hasattr(ep, "created_at") else ep.get("created_at")
            recency = compute_recency_score(created_at, half_life) if created_at else 0.5
            score = compute_hybrid_score(info["vector_sim"], info["text_rank"], recency, weights)
            content = ep.content if hasattr(ep, "content") else str(ep.get("content", ""))
            source_type = ep.source_type if hasattr(ep, "source_type") else str(ep.get("source_type", ""))
            episode_results.append(
                RecallItem(
                    item_id=eid,
                    name=f"Episode #{eid}",
                    content=content,
                    item_type="Episode",
                    score=score,
                    source=source_type,
                    source_kind="episode",
                    graph_name=None,
                )
            )

        all_results = node_results + episode_results
        all_results.sort(key=lambda item: item.score, reverse=True)
        return all_results[:limit]

    async def _recall_in_schema(
        self,
        schema_name: str,
        query: str,
        agent_id: str,
        limit: int,
        query_embedding: list[float] | None = None,
    ) -> list[RecallItem]:
        if self._pool is None:
            raise RuntimeError("Connection pool is required for schema-scoped recall.")

        weights = HybridWeights(
            vector=self._settings.recall_weight_vector,
            text=self._settings.recall_weight_text,
            recency=self._settings.recall_weight_recency,
        )
        half_life = self._settings.recall_recency_half_life_hours

        async with graph_scoped_connection(self._pool, schema_name, agent_id=agent_id) as conn:
            if query_embedding is not None:
                emb_str = str(query_embedding)
                node_rows = await conn.fetch(
                    """SELECT id, name, content, source, type_id,
                              ts_rank(tsv, plainto_tsquery('english', $1)) AS text_rank,
                              CASE WHEN embedding IS NOT NULL
                                   THEN 1 - (embedding <=> $2::vector)
                                   ELSE NULL
                              END AS vector_sim,
                              created_at
                       FROM node
                       WHERE tsv @@ plainto_tsquery('english', $1)
                          OR (embedding IS NOT NULL AND (embedding <=> $2::vector) < $3)
                       ORDER BY text_rank DESC NULLS LAST
                       LIMIT $4""",
                    query,
                    emb_str,
                    self._settings.recall_vector_distance_threshold,
                    limit,
                )
                escaped_query = _escape_ilike(query)
                episode_rows = await conn.fetch(
                    """SELECT id, content, source_type, created_at,
                              CASE WHEN embedding IS NOT NULL
                                   THEN 1 - (embedding <=> $2::vector)
                                   ELSE NULL
                              END AS vector_sim
                       FROM episode
                       WHERE content ILIKE '%' || $1 || '%' ESCAPE '\\'
                          OR (embedding IS NOT NULL AND (embedding <=> $2::vector) < $3)
                       ORDER BY created_at DESC
                       LIMIT $4""",
                    escaped_query,
                    emb_str,
                    self._settings.recall_vector_distance_threshold,
                    limit,
                )
            else:
                # Text-only path — no regression from existing behavior
                node_rows = await conn.fetch(
                    """SELECT id, name, content, source, type_id,
                              ts_rank(tsv, plainto_tsquery('english', $1)) AS text_rank,
                              NULL::double precision AS vector_sim,
                              created_at
                       FROM node
                       WHERE tsv @@ plainto_tsquery('english', $1)
                       ORDER BY text_rank DESC
                       LIMIT $2""",
                    query,
                    limit,
                )
                escaped_query = _escape_ilike(query)
                episode_rows = await conn.fetch(
                    """SELECT id, content, source_type, created_at,
                              NULL::double precision AS vector_sim
                       FROM episode
                       WHERE content ILIKE '%' || $1 || '%' ESCAPE '\\'
                       ORDER BY created_at DESC
                       LIMIT $2""",
                    escaped_query,
                    limit,
                )

            type_rows = await conn.fetch("SELECT id, name FROM node_type")

        type_names = {int(row["id"]): str(row["name"]) for row in type_rows}

        results: list[RecallItem] = []
        for row in node_rows:
            text_rank = float(row["text_rank"]) if row["text_rank"] is not None else None
            vector_sim = float(row["vector_sim"]) if row["vector_sim"] is not None else None
            created_at = row["created_at"]
            recency = compute_recency_score(created_at, half_life) if created_at else 0.5
            score = compute_hybrid_score(vector_sim, text_rank, recency, weights)
            results.append(
                RecallItem(
                    item_id=int(row["id"]),
                    name=str(row["name"]),
                    content=str(row["content"] or ""),
                    item_type=type_names.get(int(row["type_id"]), "Unknown"),
                    score=score,
                    source=str(row["source"]) if row["source"] is not None else None,
                    source_kind="node",
                    graph_name=schema_name,
                )
            )

        for row in episode_rows:
            vector_sim = float(row["vector_sim"]) if row["vector_sim"] is not None else None
            created_at = row["created_at"]
            recency = compute_recency_score(created_at, half_life) if created_at else 0.5
            score = compute_hybrid_score(vector_sim, None, recency, weights)
            results.append(
                RecallItem(
                    item_id=int(row["id"]),
                    name=f"Episode #{int(row['id'])}",
                    content=str(row["content"]),
                    item_type="Episode",
                    score=score,
                    source=str(row["source_type"]) if row["source_type"] is not None else None,
                    source_kind="episode",
                    graph_name=schema_name,
                )
            )

        results.sort(key=lambda item: item.score, reverse=True)
        return results

    async def _get_type_names(self, type_ids: set[int]) -> dict[int, str]:
        if not type_ids:
            return {}

        names: dict[int, str] = {}
        for type_id in type_ids:
            node_type = await self._graph.get_node_type(type_id)
            if node_type is not None:
                names[type_id] = node_type.name
        return names

    async def _get_types(self, table_name: str, count_table: str, agent_id: str | None = None) -> list[TypeInfo]:
        if self._pool is None or self._router is None or agent_id is None:
            return await self._get_types_from_public(table_name=table_name, count_table=count_table)

        schemas = await self._router.route_discover(agent_id)
        aggregated: dict[str, TypeInfo] = {}

        for schema_name in schemas:
            rows = await self._fetch_types_in_schema(schema_name, table_name, agent_id)
            counts = await self._fetch_type_counts_in_schema(schema_name, count_table, agent_id)
            for row in rows:
                type_name = str(row["name"])
                current = aggregated.get(type_name)
                description = str(row["description"]) if row["description"] is not None else None
                count = counts.get(int(row["id"]), 0)
                if current is None:
                    aggregated[type_name] = TypeInfo(
                        id=0,
                        name=type_name,
                        description=description,
                        count=count,
                    )
                    continue

                current.count += count
                if current.description is None and description is not None:
                    current.description = description

        return [
            TypeInfo(
                id=index,
                name=item.name,
                description=item.description,
                count=item.count,
            )
            for index, item in enumerate(sorted(aggregated.values(), key=lambda item: item.name), start=1)
        ]

    async def _get_types_from_public(self, table_name: str, count_table: str) -> list[TypeInfo]:
        if self._pg is None:
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

        rows = await self._pg.fetch(f"SELECT id, name, description FROM {table_name} ORDER BY name")
        counts = await self._pg.fetch(f"SELECT type_id AS id, count(*) AS count FROM {count_table} GROUP BY type_id")
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

    async def _fetch_types_in_schema(self, schema_name: str, table_name: str, agent_id: str) -> list[asyncpg.Record]:
        if self._pool is None:
            raise RuntimeError("Connection pool is required for schema-scoped type lookups.")

        async with graph_scoped_connection(self._pool, schema_name, agent_id=agent_id) as conn:
            return await conn.fetch(f"SELECT id, name, description FROM {table_name} ORDER BY name")

    async def _fetch_type_counts_in_schema(self, schema_name: str, count_table: str, agent_id: str) -> dict[int, int]:
        if self._pool is None:
            raise RuntimeError("Connection pool is required for schema-scoped type counts.")

        async with graph_scoped_connection(self._pool, schema_name, agent_id=agent_id) as conn:
            rows = await conn.fetch(f"SELECT type_id AS id, count(*) AS count FROM {count_table} GROUP BY type_id")
        return {int(row["id"]): int(row["count"]) for row in rows}

    async def _get_stats_in_schema(self, schema_name: str, agent_id: str) -> GraphStats:
        if self._pool is None:
            raise RuntimeError("Connection pool is required for schema-scoped stats.")

        async with graph_scoped_connection(self._pool, schema_name, agent_id=agent_id) as conn:
            row = await conn.fetchrow("""SELECT
                       (SELECT count(*) FROM node) AS total_nodes,
                       (SELECT count(*) FROM edge) AS total_edges,
                       (SELECT count(*) FROM episode) AS total_episodes""")
        if row is None:
            raise RuntimeError(f"Failed to fetch graph stats for schema '{schema_name}'.")

        return GraphStats(
            total_nodes=int(row["total_nodes"]),
            total_edges=int(row["total_edges"]),
            total_episodes=int(row["total_episodes"]),
        )


def _deduplicate_recall_items(items: Iterable[RecallItem]) -> list[RecallItem]:
    deduplicated: list[RecallItem] = []
    seen: set[tuple[str, int, str | None]] = set()

    for item in items:
        key = (item.source_kind, item.item_id, item.graph_name)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(item)

    return deduplicated
