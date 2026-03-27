import re
from contextlib import asynccontextmanager

import asyncpg

from neocortex.db.roles import _validate_role_name, ensure_pg_role, oauth_sub_to_pg_role

_VALID_SCHEMA_NAME = re.compile(r"^ncx_[a-z0-9]+__[a-z0-9_]+$")


def _validate_schema_name(schema_name: str) -> None:
    """Raise ValueError if schema_name is unsafe or violates the graph naming convention."""
    if not _VALID_SCHEMA_NAME.fullmatch(schema_name):
        raise ValueError(f"Invalid graph schema name: {schema_name!r}")


@asynccontextmanager
async def role_scoped_connection(pool: asyncpg.Pool, oauth_sub: str):
    """Run queries inside a transaction scoped to the agent PG role."""
    role_name = oauth_sub_to_pg_role(oauth_sub)
    _validate_role_name(role_name)
    await ensure_pg_role(pool, role_name)
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(f'SET LOCAL ROLE "{role_name}"')
        yield conn


@asynccontextmanager
async def schema_scoped_connection(pool: asyncpg.Pool, schema_name: str):
    """Run queries with search_path set to the target graph schema."""
    _validate_schema_name(schema_name)
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(f"SET LOCAL search_path TO {schema_name}, public")
        yield conn


@asynccontextmanager
async def graph_scoped_connection(pool: asyncpg.Pool, schema_name: str, agent_id: str | None = None):
    """Run queries scoped to a graph schema and apply RLS role only for shared graphs."""
    _validate_schema_name(schema_name)
    async with pool.acquire() as conn, conn.transaction():
        is_shared = await conn.fetchval(
            "SELECT is_shared FROM graph_registry WHERE schema_name = $1",
            schema_name,
        )
        if is_shared is None:
            raise ValueError(f"Unknown graph schema: {schema_name}")

        if is_shared:
            if agent_id is None:
                raise ValueError("agent_id is required for shared graph access")
            role_name = oauth_sub_to_pg_role(agent_id)
            _validate_role_name(role_name)
            await ensure_pg_role(pool, role_name)
            await conn.execute(f'SET LOCAL ROLE "{role_name}"')

        await conn.execute(f"SET LOCAL search_path TO {schema_name}, public")
        yield conn


scoped_connection = role_scoped_connection
