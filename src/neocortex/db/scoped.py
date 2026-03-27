from contextlib import asynccontextmanager

import asyncpg

from neocortex.db.roles import ensure_pg_role, oauth_sub_to_pg_role


@asynccontextmanager
async def scoped_connection(pool: asyncpg.Pool, oauth_sub: str):
    """Run queries inside a transaction scoped to the agent PG role."""
    role_name = oauth_sub_to_pg_role(oauth_sub)
    await ensure_pg_role(pool, role_name)
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(f'SET LOCAL ROLE "{role_name}"')
        yield conn
