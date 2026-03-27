import re

import asyncpg
from loguru import logger

_MAX_SUB_LENGTH = 46
_SAFE_CHARS = re.compile(r"[^a-z0-9_]")
_VALID_ROLE = re.compile(r"^[a-z0-9_]+$")


def _validate_role_name(role_name: str) -> None:
    """Raise ValueError if role_name contains characters unsafe for SQL interpolation."""
    if not _VALID_ROLE.match(role_name):
        raise ValueError(f"Invalid PG role name: {role_name!r}")


def oauth_sub_to_pg_role(oauth_sub: str) -> str:
    """Map an OAuth subject claim to a PostgreSQL role name."""
    sanitized = _SAFE_CHARS.sub("_", oauth_sub.lower())[:_MAX_SUB_LENGTH]
    return f"neocortex_agent_{sanitized}"


async def ensure_pg_role(pool: asyncpg.Pool, role_name: str) -> None:
    """Create an agent PG role if it does not already exist."""
    _validate_role_name(role_name)
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", role_name)
        if exists:
            return

        await conn.execute(f'CREATE ROLE "{role_name}" NOLOGIN INHERIT IN ROLE neocortex_agent')
        logger.info("Created PG role: {}", role_name)
