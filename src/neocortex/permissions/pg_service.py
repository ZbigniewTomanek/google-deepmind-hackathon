from __future__ import annotations

from typing import Any

import asyncpg

from neocortex.postgres_service import PostgresService
from neocortex.schemas.permissions import AgentInfo, PermissionInfo


def _record_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    """Convert asyncpg Record to dict (helps the type checker)."""
    return dict(row.items())


class PostgresPermissionService:
    """PostgreSQL-backed permission service using agent_registry and graph_permissions tables."""

    def __init__(self, pg: PostgresService, bootstrap_admin_id: str) -> None:
        self._pg = pg
        self._bootstrap_admin_id = bootstrap_admin_id

    async def is_admin(self, agent_id: str) -> bool:
        row = await self._pg.fetchrow(
            "SELECT is_admin FROM agent_registry WHERE agent_id = $1 AND is_admin = TRUE",
            agent_id,
        )
        return row is not None

    async def ensure_admin(self, agent_id: str) -> None:
        await self._pg.execute(
            """INSERT INTO agent_registry (agent_id, is_admin)
               VALUES ($1, TRUE)
               ON CONFLICT (agent_id) DO UPDATE SET is_admin = TRUE, updated_at = now()""",
            agent_id,
        )

    async def can_read_schema(self, agent_id: str, schema_name: str) -> bool:
        if await self.is_admin(agent_id):
            return True
        # Shared schemas are world-readable
        row = await self._pg.fetchrow(
            "SELECT 1 FROM graph_registry WHERE schema_name = $1 AND is_shared = true",
            schema_name,
        )
        if row is not None:
            return True
        # Fall back to explicit grant
        row = await self._pg.fetchrow(
            "SELECT 1 FROM graph_permissions WHERE agent_id = $1 AND schema_name = $2 AND can_read = TRUE",
            agent_id,
            schema_name,
        )
        return row is not None

    async def can_write_schema(self, agent_id: str, schema_name: str) -> bool:
        if await self.is_admin(agent_id):
            return True
        row = await self._pg.fetchrow(
            "SELECT 1 FROM graph_permissions WHERE agent_id = $1 AND schema_name = $2 AND can_write = TRUE",
            agent_id,
            schema_name,
        )
        return row is not None

    async def readable_schemas(self, agent_id: str, candidates: list[str]) -> set[str]:
        if not candidates:
            return set()
        if await self.is_admin(agent_id):
            return set(candidates)
        # Shared schemas are world-readable
        shared_rows = await self._pg.fetch(
            "SELECT schema_name FROM graph_registry" " WHERE schema_name = ANY($1) AND is_shared = true",
            candidates,
        )
        result = {row["schema_name"] for row in shared_rows}
        # Union with explicitly granted schemas
        granted_rows = await self._pg.fetch(
            "SELECT schema_name FROM graph_permissions"
            " WHERE agent_id = $1 AND schema_name = ANY($2) AND can_read = TRUE",
            agent_id,
            candidates,
        )
        result.update(row["schema_name"] for row in granted_rows)
        return result

    async def grant(
        self,
        agent_id: str,
        schema_name: str,
        can_read: bool,
        can_write: bool,
        granted_by: str,
    ) -> PermissionInfo:
        row = await self._pg.fetchrow(
            """INSERT INTO graph_permissions (agent_id, schema_name, can_read, can_write, granted_by)
               VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT (agent_id, schema_name) DO UPDATE
                 SET can_read = $3, can_write = $4, granted_by = $5, updated_at = now()
               RETURNING id, agent_id, schema_name, can_read, can_write, granted_by, created_at, updated_at""",
            agent_id,
            schema_name,
            can_read,
            can_write,
            granted_by,
        )
        assert row is not None  # RETURNING always produces a row
        return PermissionInfo.model_validate(_record_to_dict(row))

    async def revoke(self, agent_id: str, schema_name: str) -> bool:
        result = await self._pg.execute(
            "DELETE FROM graph_permissions WHERE agent_id = $1 AND schema_name = $2",
            agent_id,
            schema_name,
        )
        return result != "DELETE 0"

    async def list_for_agent(self, agent_id: str) -> list[PermissionInfo]:
        rows = await self._pg.fetch(
            "SELECT id, agent_id, schema_name, can_read, can_write,"
            " granted_by, created_at, updated_at"
            " FROM graph_permissions WHERE agent_id = $1 ORDER BY schema_name",
            agent_id,
        )
        return [PermissionInfo.model_validate(_record_to_dict(row)) for row in rows]

    async def list_for_schema(self, schema_name: str) -> list[PermissionInfo]:
        rows = await self._pg.fetch(
            "SELECT id, agent_id, schema_name, can_read, can_write,"
            " granted_by, created_at, updated_at"
            " FROM graph_permissions WHERE schema_name = $1 ORDER BY agent_id",
            schema_name,
        )
        return [PermissionInfo.model_validate(_record_to_dict(row)) for row in rows]

    async def list_all_permissions(self) -> list[PermissionInfo]:
        rows = await self._pg.fetch(
            "SELECT id, agent_id, schema_name, can_read, can_write,"
            " granted_by, created_at, updated_at"
            " FROM graph_permissions ORDER BY agent_id, schema_name"
        )
        return [PermissionInfo.model_validate(_record_to_dict(row)) for row in rows]

    async def set_admin(self, agent_id: str, is_admin: bool) -> None:
        if agent_id == self._bootstrap_admin_id and not is_admin:
            raise ValueError(f"Cannot demote the bootstrap admin '{self._bootstrap_admin_id}'")
        await self._pg.execute(
            """INSERT INTO agent_registry (agent_id, is_admin)
               VALUES ($1, $2)
               ON CONFLICT (agent_id) DO UPDATE SET is_admin = $2, updated_at = now()""",
            agent_id,
            is_admin,
        )

    async def list_agents(self) -> list[AgentInfo]:
        rows = await self._pg.fetch(
            "SELECT id, agent_id, is_admin, created_at, updated_at FROM agent_registry ORDER BY agent_id"
        )
        return [AgentInfo.model_validate(_record_to_dict(row)) for row in rows]
