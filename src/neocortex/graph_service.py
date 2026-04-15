import json
from typing import Any

import asyncpg

from neocortex.models import Edge, EdgeType, Episode, Node, NodeType
from neocortex.postgres_service import PostgresService


def _record_to_dict(row: asyncpg.Record | None) -> dict[str, Any]:
    """Convert asyncpg Record to dict (helps the type checker)."""
    if row is None:
        raise ValueError("Expected a database row but got None")
    return dict(row.items())


class GraphService:
    """Graph layer for ontology manipulation and data CRUD on the NeoCortex knowledge graph."""

    def __init__(self, pg: PostgresService):
        self._pg = pg

    # ── Ontology: Node Types ─────────────────────────────────────

    async def create_node_type(self, name: str, description: str | None = None) -> NodeType:
        row = await self._pg.fetchrow(
            "INSERT INTO node_type (name, description) VALUES ($1, $2) RETURNING *",
            name,
            description,
        )
        return NodeType(**_record_to_dict(row))

    async def get_node_type(self, id: int) -> NodeType | None:
        row = await self._pg.fetchrow("SELECT * FROM node_type WHERE id = $1", id)
        return NodeType(**_record_to_dict(row)) if row else None

    async def get_node_type_by_name(self, name: str) -> NodeType | None:
        row = await self._pg.fetchrow("SELECT * FROM node_type WHERE name = $1", name)
        return NodeType(**_record_to_dict(row)) if row else None

    async def list_node_types(self) -> list[NodeType]:
        rows = await self._pg.fetch("SELECT * FROM node_type ORDER BY name")
        return [NodeType(**_record_to_dict(r)) for r in rows]

    async def update_node_type(
        self, id: int, name: str | None = None, description: str | None = None
    ) -> NodeType | None:
        row = await self._pg.fetchrow(
            """UPDATE node_type SET name = COALESCE($1, name), description = COALESCE($2, description)
               WHERE id = $3 RETURNING *""",
            name,
            description,
            id,
        )
        return NodeType(**_record_to_dict(row)) if row else None

    async def delete_node_type(self, id: int) -> bool:
        result = await self._pg.execute("DELETE FROM node_type WHERE id = $1", id)
        return result == "DELETE 1"

    # ── Ontology: Edge Types ─────────────────────────────────────

    async def create_edge_type(self, name: str, description: str | None = None) -> EdgeType:
        row = await self._pg.fetchrow(
            "INSERT INTO edge_type (name, description) VALUES ($1, $2) RETURNING *",
            name,
            description,
        )
        return EdgeType(**_record_to_dict(row))

    async def get_edge_type(self, id: int) -> EdgeType | None:
        row = await self._pg.fetchrow("SELECT * FROM edge_type WHERE id = $1", id)
        return EdgeType(**_record_to_dict(row)) if row else None

    async def get_edge_type_by_name(self, name: str) -> EdgeType | None:
        row = await self._pg.fetchrow("SELECT * FROM edge_type WHERE name = $1", name)
        return EdgeType(**_record_to_dict(row)) if row else None

    async def list_edge_types(self) -> list[EdgeType]:
        rows = await self._pg.fetch("SELECT * FROM edge_type ORDER BY name")
        return [EdgeType(**_record_to_dict(r)) for r in rows]

    async def update_edge_type(
        self, id: int, name: str | None = None, description: str | None = None
    ) -> EdgeType | None:
        row = await self._pg.fetchrow(
            """UPDATE edge_type SET name = COALESCE($1, name), description = COALESCE($2, description)
               WHERE id = $3 RETURNING *""",
            name,
            description,
            id,
        )
        return EdgeType(**_record_to_dict(row)) if row else None

    async def delete_edge_type(self, id: int) -> bool:
        result = await self._pg.execute("DELETE FROM edge_type WHERE id = $1", id)
        return result == "DELETE 1"

    # ── Nodes ────────────────────────────────────────────────────

    async def create_node(
        self,
        type_id: int,
        name: str,
        content: str | None = None,
        properties: dict | None = None,
        embedding: list[float] | None = None,
        source: str | None = None,
    ) -> Node:
        props_json = json.dumps(properties or {})
        emb_str = str(embedding) if embedding else None
        row = await self._pg.fetchrow(
            """INSERT INTO node (type_id, name, content, properties, embedding, source)
               VALUES ($1, $2, $3, $4::jsonb, $5::vector, $6)
               RETURNING id, type_id, name, content, properties, source, created_at, updated_at""",
            type_id,
            name,
            content,
            props_json,
            emb_str,
            source,
        )
        return self._row_to_node(row)

    async def get_node(self, id: int) -> Node | None:
        row = await self._pg.fetchrow(
            "SELECT id, type_id, name, content, properties, source, created_at, updated_at FROM node WHERE id = $1",
            id,
        )
        return self._row_to_node(row) if row else None

    async def list_nodes(self, type_id: int | None = None, limit: int = 100, offset: int = 0) -> list[Node]:
        if type_id is not None:
            rows = await self._pg.fetch(
                """SELECT id, type_id, name, content, properties, source, created_at, updated_at
                   FROM node WHERE type_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3""",
                type_id,
                limit,
                offset,
            )
        else:
            rows = await self._pg.fetch(
                """SELECT id, type_id, name, content, properties, source, created_at, updated_at
                   FROM node ORDER BY created_at DESC LIMIT $1 OFFSET $2""",
                limit,
                offset,
            )
        return [self._row_to_node(r) for r in rows]

    async def update_node(
        self,
        id: int,
        name: str | None = None,
        content: str | None = None,
        properties: dict | None = None,
        embedding: list[float] | None = None,
    ) -> Node | None:
        props_json = json.dumps(properties) if properties is not None else None
        emb_str = str(embedding) if embedding is not None else None
        row = await self._pg.fetchrow(
            """UPDATE node SET
                name = COALESCE($1, name),
                -- Content: prefer new value, keep old only when new is NULL
                content = COALESCE($2, content),
                properties = COALESCE($3::jsonb, properties),
                embedding = COALESCE($4::vector, embedding),
                updated_at = now()
               WHERE id = $5
               RETURNING id, type_id, name, content, properties, source, created_at, updated_at""",
            name,
            content,
            props_json,
            emb_str,
            id,
        )
        return self._row_to_node(row) if row else None

    async def delete_node(self, id: int) -> bool:
        result = await self._pg.execute("DELETE FROM node WHERE id = $1", id)
        return result == "DELETE 1"

    # ── Edges ────────────────────────────────────────────────────

    async def create_edge(
        self,
        source_id: int,
        target_id: int,
        type_id: int,
        weight: float = 1.0,
        properties: dict | None = None,
    ) -> Edge:
        props_json = json.dumps(properties or {})
        row = await self._pg.fetchrow(
            """INSERT INTO edge (source_id, target_id, type_id, weight, properties)
               VALUES ($1, $2, $3, $4, $5::jsonb)
               RETURNING *""",
            source_id,
            target_id,
            type_id,
            weight,
            props_json,
        )
        return self._row_to_edge(row)

    async def get_edge(self, id: int) -> Edge | None:
        row = await self._pg.fetchrow("SELECT * FROM edge WHERE id = $1", id)
        return self._row_to_edge(row) if row else None

    async def get_edges_from(self, source_id: int, type_id: int | None = None) -> list[Edge]:
        if type_id is not None:
            rows = await self._pg.fetch(
                "SELECT * FROM edge WHERE source_id = $1 AND type_id = $2 ORDER BY weight DESC",
                source_id,
                type_id,
            )
        else:
            rows = await self._pg.fetch(
                "SELECT * FROM edge WHERE source_id = $1 ORDER BY weight DESC",
                source_id,
            )
        return [self._row_to_edge(r) for r in rows]

    async def get_edges_to(self, target_id: int, type_id: int | None = None) -> list[Edge]:
        if type_id is not None:
            rows = await self._pg.fetch(
                "SELECT * FROM edge WHERE target_id = $1 AND type_id = $2 ORDER BY weight DESC",
                target_id,
                type_id,
            )
        else:
            rows = await self._pg.fetch(
                "SELECT * FROM edge WHERE target_id = $1 ORDER BY weight DESC",
                target_id,
            )
        return [self._row_to_edge(r) for r in rows]

    async def delete_edge(self, id: int) -> bool:
        result = await self._pg.execute("DELETE FROM edge WHERE id = $1", id)
        return result == "DELETE 1"

    # ── Episodes ─────────────────────────────────────────────────

    async def create_episode(
        self,
        agent_id: str,
        content: str,
        embedding: list[float] | None = None,
        source_type: str | None = None,
        metadata: dict | None = None,
        content_hash: str | None = None,
        session_id: str | None = None,
    ) -> Episode:
        meta_json = json.dumps(metadata or {})
        emb_str = str(embedding) if embedding else None
        # Compute session_sequence if session_id is provided
        session_sequence = None
        if session_id is not None:
            seq_row = await self._pg.fetchrow(
                "SELECT COALESCE(MAX(session_sequence), 0) + 1 AS next_seq "
                "FROM episode WHERE agent_id = $1 AND session_id = $2",
                agent_id,
                session_id,
            )
            if seq_row is not None:
                session_sequence = seq_row["next_seq"]
        row = await self._pg.fetchrow(
            """INSERT INTO episode
               (agent_id, content, embedding, source_type,
                metadata, content_hash, session_id, session_sequence)
               VALUES ($1, $2, $3::vector, $4, $5::jsonb, $6, $7, $8)
               RETURNING id, agent_id, content, source_type, metadata,
                         content_hash, session_id, session_sequence,
                         created_at""",
            agent_id,
            content,
            emb_str,
            source_type,
            meta_json,
            content_hash,
            session_id,
            session_sequence,
        )
        return self._row_to_episode(row)

    async def get_episode(self, id: int) -> Episode | None:
        row = await self._pg.fetchrow(
            "SELECT id, agent_id, content, source_type, metadata, session_id, session_sequence, created_at "
            "FROM episode WHERE id = $1",
            id,
        )
        return self._row_to_episode(row) if row else None

    async def list_episodes(self, agent_id: str | None = None, limit: int = 50) -> list[Episode]:
        if agent_id is not None:
            rows = await self._pg.fetch(
                """SELECT id, agent_id, content, source_type, metadata, created_at,
                          session_id, session_sequence
                   FROM episode WHERE agent_id = $1 ORDER BY created_at DESC LIMIT $2""",
                agent_id,
                limit,
            )
        else:
            rows = await self._pg.fetch(
                """SELECT id, agent_id, content, source_type, metadata, created_at,
                          session_id, session_sequence
                   FROM episode ORDER BY created_at DESC LIMIT $1""",
                limit,
            )
        return [self._row_to_episode(r) for r in rows]

    async def delete_episode(self, id: int) -> bool:
        result = await self._pg.execute("DELETE FROM episode WHERE id = $1", id)
        return result == "DELETE 1"

    # ── Neighbors (graph traversal helper) ───────────────────────

    async def get_neighbors(self, node_id: int) -> list[dict]:
        """Get immediate neighboring nodes (1-hop). Returns list of dicts with node info and edge metadata."""
        rows = await self._pg.fetch(
            """SELECT
                n.id, n.name, n.type_id, n.content, n.source, n.created_at,
                e.id as edge_id, e.type_id as edge_type_id, e.weight,
                et.name as edge_type_name,
                'outgoing' as direction
               FROM edge e
               JOIN node n ON n.id = e.target_id
               JOIN edge_type et ON et.id = e.type_id
               WHERE e.source_id = $1
             UNION ALL
             SELECT
                n.id, n.name, n.type_id, n.content, n.source, n.created_at,
                e.id as edge_id, e.type_id as edge_type_id, e.weight,
                et.name as edge_type_name,
                'incoming' as direction
               FROM edge e
               JOIN node n ON n.id = e.source_id
               JOIN edge_type et ON et.id = e.type_id
               WHERE e.target_id = $1
             ORDER BY weight DESC""",
            node_id,
        )
        return [_record_to_dict(r) for r in rows]

    # ── Search: Vector Similarity ────────────────────────────────

    async def search_by_vector(self, embedding: list[float], limit: int = 10, type_id: int | None = None) -> list[dict]:
        """Find nodes closest to the given embedding vector (cosine distance)."""
        emb_str = str(embedding)
        if type_id is not None:
            rows = await self._pg.fetch(
                """SELECT n.id, n.type_id, n.name, n.content, n.properties, n.source,
                          n.created_at, n.updated_at,
                          COALESCE(nt.name, 'Untyped') AS resolved_type_name,
                          1 - (n.embedding <=> $1::vector) AS similarity
                   FROM node n
                   LEFT JOIN node_type nt ON nt.id = n.type_id
                   WHERE n.embedding IS NOT NULL AND n.type_id = $2
                   ORDER BY n.embedding <=> $1::vector
                   LIMIT $3""",
                emb_str,
                type_id,
                limit,
            )
        else:
            rows = await self._pg.fetch(
                """SELECT n.id, n.type_id, n.name, n.content, n.properties, n.source,
                          n.created_at, n.updated_at,
                          COALESCE(nt.name, 'Untyped') AS resolved_type_name,
                          1 - (n.embedding <=> $1::vector) AS similarity
                   FROM node n
                   LEFT JOIN node_type nt ON nt.id = n.type_id
                   WHERE n.embedding IS NOT NULL
                   ORDER BY n.embedding <=> $1::vector
                   LIMIT $2""",
                emb_str,
                limit,
            )
        return [dict(r) for r in rows]

    # ── Search: Full-Text (tsvector + ts_rank) ─────────────────────

    async def search_by_text(self, query: str, limit: int = 10, type_id: int | None = None) -> list[dict]:
        """Full-text search using PostgreSQL tsvector. Returns nodes ranked by ts_rank."""
        if type_id is not None:
            rows = await self._pg.fetch(
                """SELECT n.id, n.type_id, n.name, n.content, n.properties, n.source,
                          n.created_at, n.updated_at,
                          COALESCE(nt.name, 'Untyped') AS resolved_type_name,
                          ts_rank(n.tsv, plainto_tsquery('english', $1)) AS rank
                   FROM node n
                   LEFT JOIN node_type nt ON nt.id = n.type_id
                   WHERE n.tsv @@ plainto_tsquery('english', $1) AND n.type_id = $2
                   ORDER BY rank DESC
                   LIMIT $3""",
                query,
                type_id,
                limit,
            )
        else:
            rows = await self._pg.fetch(
                """SELECT n.id, n.type_id, n.name, n.content, n.properties, n.source,
                          n.created_at, n.updated_at,
                          COALESCE(nt.name, 'Untyped') AS resolved_type_name,
                          ts_rank(n.tsv, plainto_tsquery('english', $1)) AS rank
                   FROM node n
                   LEFT JOIN node_type nt ON nt.id = n.type_id
                   WHERE n.tsv @@ plainto_tsquery('english', $1)
                   ORDER BY rank DESC
                   LIMIT $2""",
                query,
                limit,
            )
        return [dict(r) for r in rows]

    # ── Search: Episodes by vector ───────────────────────────────

    async def search_episodes_by_vector(
        self, embedding: list[float], agent_id: str | None = None, limit: int = 10
    ) -> list[dict]:
        """Find episodes closest to the given embedding vector."""
        emb_str = str(embedding)
        if agent_id is not None:
            rows = await self._pg.fetch(
                """SELECT id, agent_id, content, source_type, metadata, created_at,
                          1 - (embedding <=> $1::vector) AS similarity
                   FROM episode
                   WHERE embedding IS NOT NULL AND agent_id = $2
                   ORDER BY embedding <=> $1::vector
                   LIMIT $3""",
                emb_str,
                agent_id,
                limit,
            )
        else:
            rows = await self._pg.fetch(
                """SELECT id, agent_id, content, source_type, metadata, created_at,
                          1 - (embedding <=> $1::vector) AS similarity
                   FROM episode
                   WHERE embedding IS NOT NULL
                   ORDER BY embedding <=> $1::vector
                   LIMIT $2""",
                emb_str,
                limit,
            )
        return [dict(r) for r in rows]

    # ── Search: Graph-aware neighbor expansion ───────────────────

    async def search_with_neighbors(self, embedding: list[float], limit: int = 5) -> list[dict]:
        """Vector search + expand results with immediate graph neighbors.
        Returns primary hits annotated with their neighbors."""
        hits = await self.search_by_vector(embedding, limit=limit)
        results = []
        for hit in hits:
            neighbors = await self.get_neighbors(hit["id"])
            hit["neighbors"] = neighbors
            results.append(hit)
        return results

    # ── Ontology stats (for `discover` MCP tool) ─────────────────

    async def get_ontology_stats(self) -> dict:
        """Return ontology overview: type counts, node counts per type, edge counts per type."""
        node_counts = await self._pg.fetch("""SELECT nt.name as type_name, count(n.id) as count
               FROM node_type nt
               LEFT JOIN node n ON n.type_id = nt.id
               GROUP BY nt.id, nt.name
               ORDER BY count DESC""")
        edge_counts = await self._pg.fetch("""SELECT et.name as type_name, count(e.id) as count
               FROM edge_type et
               LEFT JOIN edge e ON e.type_id = et.id
               GROUP BY et.id, et.name
               ORDER BY count DESC""")
        total_nodes = await self._pg.fetchval("SELECT count(*) FROM node")
        total_edges = await self._pg.fetchval("SELECT count(*) FROM edge")
        total_episodes = await self._pg.fetchval("SELECT count(*) FROM episode")
        return {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "total_episodes": total_episodes,
            "node_types": [dict(r) for r in node_counts],
            "edge_types": [dict(r) for r in edge_counts],
        }

    # ── Private helpers ──────────────────────────────────────────

    @staticmethod
    def _row_to_node(row: asyncpg.Record | None) -> Node:
        d = _record_to_dict(row)
        if isinstance(d.get("properties"), str):
            d["properties"] = json.loads(d["properties"])
        return Node(**d)

    @staticmethod
    def _row_to_edge(row: asyncpg.Record | None) -> Edge:
        d = _record_to_dict(row)
        if isinstance(d.get("properties"), str):
            d["properties"] = json.loads(d["properties"])
        return Edge(**d)

    @staticmethod
    def _row_to_episode(row: asyncpg.Record | None) -> Episode:
        d = _record_to_dict(row)
        if isinstance(d.get("metadata"), str):
            d["metadata"] = json.loads(d["metadata"])
        return Episode(**d)
