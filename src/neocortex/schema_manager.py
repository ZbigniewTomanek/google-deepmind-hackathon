from __future__ import annotations

import re
from typing import TYPE_CHECKING

import asyncpg.exceptions

from neocortex.postgres_service import PostgresService
from neocortex.schemas.graph import GraphInfo

if TYPE_CHECKING:
    from neocortex.migrations import MigrationRunner

_SCHEMA_NAME_PATTERN = re.compile(r"^ncx_[a-z0-9]+__[a-z0-9_]+$")
_NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")
_NON_ALNUM_UNDERSCORE_PATTERN = re.compile(r"[^a-z0-9_]+")
_REPEATED_UNDERSCORES_PATTERN = re.compile(r"_+")


class SchemaManager:
    """Manage lifecycle for isolated graph schemas registered in `public.graph_registry`."""

    def __init__(self, pg: PostgresService, migration_runner: MigrationRunner | None = None):
        self._pg = pg
        if migration_runner is None:
            from neocortex.migrations import MigrationRunner

            migration_runner = MigrationRunner(pg)
        self._migration_runner = migration_runner

    async def create_graph(self, agent_id: str, purpose: str, is_shared: bool = False) -> str:
        """Create or return a registered graph schema name for the agent/purpose pair."""
        existing = await self.get_graph(agent_id=agent_id, purpose=purpose)
        if existing is not None:
            return existing.schema_name

        schema_name = self.make_schema_name(agent_id=agent_id, purpose=purpose)

        try:
            await self._migration_runner.run_for_schema(schema_name)

            async with self._pg.pool.acquire() as conn, conn.transaction():
                duplicate = await conn.fetchrow(
                    """
                    SELECT id, agent_id, purpose, schema_name, is_shared, created_at
                    FROM graph_registry
                    WHERE agent_id = $1 AND purpose = $2
                    """,
                    agent_id,
                    purpose,
                )
                if duplicate is not None:
                    return str(duplicate["schema_name"])

                if is_shared:
                    provenance_sql = self._build_shared_provenance_block(schema_name)
                    await conn.execute(provenance_sql)

                row = await conn.fetchrow(
                    """
                    INSERT INTO graph_registry (agent_id, purpose, schema_name, is_shared)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id, agent_id, purpose, schema_name, is_shared, created_at
                    """,
                    agent_id,
                    purpose,
                    schema_name,
                    is_shared,
                )
        except asyncpg.exceptions.UniqueViolationError:
            # CREATE SCHEMA IF NOT EXISTS has a race condition under concurrent
            # transactions — the catalog check and insert aren't atomic, so a
            # parallel process can win the race.  Re-check the registry.
            existing = await self.get_graph(agent_id=agent_id, purpose=purpose)
            if existing is not None:
                return existing.schema_name
            return schema_name

        if row is None:
            raise RuntimeError(f"Failed to register graph schema '{schema_name}'.")
        return str(row["schema_name"])

    async def drop_graph(self, schema_name: str) -> bool:
        """Drop a graph schema and remove its registry entry."""
        self._validate_schema_name(schema_name)
        async with self._pg.pool.acquire() as conn, conn.transaction():
            deleted = await conn.fetchrow(
                """
                DELETE FROM graph_registry
                WHERE schema_name = $1
                RETURNING id
                """,
                schema_name,
            )
            await conn.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
        return deleted is not None

    async def list_graphs(self, agent_id: str | None = None) -> list[GraphInfo]:
        """List registered graphs, optionally filtered by agent identifier."""
        if agent_id is None:
            rows = await self._pg.fetch("""
                SELECT id, agent_id, purpose, schema_name, is_shared, created_at
                FROM graph_registry
                ORDER BY agent_id, purpose
                """)
        else:
            rows = await self._pg.fetch(
                """
                SELECT id, agent_id, purpose, schema_name, is_shared, created_at
                FROM graph_registry
                WHERE agent_id = $1
                ORDER BY purpose
                """,
                agent_id,
            )
        return [GraphInfo.model_validate(dict(row)) for row in rows]

    async def get_graph(self, agent_id: str, purpose: str) -> GraphInfo | None:
        """Look up a specific graph by agent and purpose."""
        row = await self._pg.fetchrow(
            """
            SELECT id, agent_id, purpose, schema_name, is_shared, created_at
            FROM graph_registry
            WHERE agent_id = $1 AND purpose = $2
            """,
            agent_id,
            purpose,
        )
        if row is None:
            return None
        return GraphInfo.model_validate(dict(row))

    async def ensure_default_graphs(self, agent_id: str) -> str:
        """Ensure the agent has a default personal graph and return its schema name."""
        graph = await self.get_graph(agent_id=agent_id, purpose="personal")
        if graph is not None:
            return graph.schema_name
        return await self.create_graph(agent_id=agent_id, purpose="personal")

    @staticmethod
    def make_schema_name(agent_id: str, purpose: str) -> str:
        """Generate a validated schema name using the `ncx_{agent}__{purpose}` convention."""
        normalized_agent = _sanitize_agent_id(agent_id)
        normalized_purpose = _sanitize_purpose(purpose)
        schema_name = f"ncx_{normalized_agent}__{normalized_purpose}"
        SchemaManager._validate_schema_name(schema_name)
        return schema_name

    @staticmethod
    def _validate_schema_name(schema_name: str) -> None:
        if not _SCHEMA_NAME_PATTERN.fullmatch(schema_name):
            raise ValueError(f"Invalid graph schema name: {schema_name}")

    @staticmethod
    def _build_shared_provenance_block(schema_name: str) -> str:
        statements = [
            f"-- Shared graph provenance provisioned for {schema_name}.",
            "DO $$",
            "BEGIN",
            "    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'neocortex_agent') THEN",
            "        CREATE ROLE neocortex_agent NOLOGIN;",
            "    END IF;",
            "END",
            "$$;",
            f"GRANT USAGE ON SCHEMA {schema_name} TO neocortex_agent;",
            (
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {schema_name}.node, "
                f"{schema_name}.edge, {schema_name}.episode, {schema_name}.node_alias TO neocortex_agent;"
            ),
            f"GRANT SELECT, INSERT ON TABLE {schema_name}.node_type, {schema_name}.edge_type TO neocortex_agent;",
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema_name} TO neocortex_agent;",
            f"ALTER TABLE {schema_name}.node ADD COLUMN IF NOT EXISTS owner_role TEXT DEFAULT current_user;",
            f"ALTER TABLE {schema_name}.edge ADD COLUMN IF NOT EXISTS owner_role TEXT DEFAULT current_user;",
            f"ALTER TABLE {schema_name}.episode ADD COLUMN IF NOT EXISTS owner_role TEXT DEFAULT current_user;",
            f"CREATE INDEX IF NOT EXISTS idx_{schema_name}_node_owner ON {schema_name}.node (owner_role);",
            f"CREATE INDEX IF NOT EXISTS idx_{schema_name}_edge_owner ON {schema_name}.edge (owner_role);",
            f"CREATE INDEX IF NOT EXISTS idx_{schema_name}_episode_owner ON {schema_name}.episode (owner_role);",
        ]
        return "\n".join(statements)


def _sanitize_agent_id(value: str) -> str:
    normalized = _NON_ALNUM_PATTERN.sub("", value.strip().lower())
    if not normalized:
        raise ValueError("agent_id must contain at least one ASCII letter or digit")
    return normalized


def _sanitize_purpose(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    normalized = _NON_ALNUM_UNDERSCORE_PATTERN.sub("_", normalized)
    normalized = _REPEATED_UNDERSCORES_PATTERN.sub("_", normalized).strip("_")
    if not normalized:
        raise ValueError("purpose must contain at least one ASCII letter or digit")
    return normalized
