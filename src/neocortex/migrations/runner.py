"""Unified migration runner for public and per-schema graph migrations."""

import hashlib
import re
from pathlib import Path

from loguru import logger

from neocortex.postgres_service import PostgresService

_SCHEMA_NAME_PATTERN = re.compile(r"^ncx_[a-z0-9]+__[a-z0-9_]+$")

# Old per-schema migration names → new filenames.
# Prevents re-applying migrations that were already tracked under legacy names.
_LEGACY_GRAPH_NAMES: dict[str, str] = {
    "009_node_alias": "004_node_alias.sql",
    "011_episode_content_hash": "005_content_hash.sql",
}


class MigrationRunner:
    """Applies public and per-schema graph migrations with tracking, checksums, and advisory locking."""

    def __init__(self, pg: PostgresService) -> None:
        self._pg = pg
        migrations_root = Path(__file__).resolve().parents[3] / "migrations"
        self._public_dir = migrations_root / "public"
        self._graph_dir = migrations_root / "graph"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_public(self) -> int:
        """Apply pending public-schema migrations. Returns count of newly applied."""
        async with self._pg.pool.acquire() as conn:
            try:
                await conn.execute("SELECT pg_advisory_lock(hashtext('neocortex_migration_public'))")
                await self._ensure_tracking_table(conn)
                migrations = self._list_migrations(self._public_dir)
                applied = await self._get_applied(conn)
                count = 0
                for name, path in migrations:
                    sql = path.read_text(encoding="utf-8")
                    checksum = self._md5(sql)
                    if name in applied:
                        if applied[name] is not None and applied[name] != checksum:
                            logger.warning(
                                "checksum_mismatch",
                                migration=name,
                                action="checksum_mismatch",
                            )
                        continue
                    async with conn.transaction():
                        await conn.execute(sql)
                        await conn.execute(
                            "INSERT INTO public._migration (name, checksum) VALUES ($1, $2)",
                            name,
                            checksum,
                        )
                    logger.info("applied", migration=name, schema="public", action="applied")
                    count += 1
                return count
            finally:
                await conn.execute("SELECT pg_advisory_unlock(hashtext('neocortex_migration_public'))")

    async def run_graph_schemas(self) -> int:
        """Apply pending graph migrations to all registered schemas. Returns total count."""
        async with self._pg.pool.acquire() as conn:
            try:
                await conn.execute("SELECT pg_advisory_lock(hashtext('neocortex_migration_graph'))")
                rows = await conn.fetch("SELECT schema_name FROM graph_registry")
                total = 0
                for row in rows:
                    total += await self.run_for_schema(row["schema_name"])
                return total
            finally:
                await conn.execute("SELECT pg_advisory_unlock(hashtext('neocortex_migration_graph'))")

    async def run_for_schema(self, schema_name: str) -> int:
        """Apply pending graph migrations to a single schema. Returns count of newly applied."""
        if not _SCHEMA_NAME_PATTERN.fullmatch(schema_name):
            raise ValueError(f"Invalid graph schema name: {schema_name}")

        async with self._pg.pool.acquire() as conn:
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
            await self._ensure_tracking_table(conn, schema_name)
            migrations = self._list_migrations(self._graph_dir)
            applied = await self._get_applied(conn, schema_name)

            # Map legacy tracking names to new filenames so we don't re-apply.
            for old_name, new_filename in _LEGACY_GRAPH_NAMES.items():
                if old_name in applied and new_filename not in applied:
                    await conn.execute(
                        f"INSERT INTO {schema_name}._migration (name, checksum) VALUES ($1, $2)",
                        new_filename,
                        None,
                    )
                    applied[new_filename] = None
                    logger.info(
                        "legacy_mapped",
                        migration=new_filename,
                        legacy_name=old_name,
                        schema=schema_name,
                        action="skipped",
                    )

            count = 0
            for name, path in migrations:
                if name in applied:
                    continue
                sql = path.read_text(encoding="utf-8")
                rendered = sql.replace("{schema}", schema_name)
                checksum = self._md5(sql)
                async with conn.transaction():
                    await conn.execute(rendered)
                    await conn.execute(
                        f"INSERT INTO {schema_name}._migration (name, checksum) VALUES ($1, $2)",
                        name,
                        checksum,
                    )
                logger.info("applied", migration=name, schema=schema_name, action="applied")
                count += 1
            return count

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _ensure_tracking_table(conn, schema: str | None = None) -> None:
        """Create the _migration tracking table if it doesn't exist."""
        target = f"{schema}." if schema else "public."
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {target}_migration (
                id          SERIAL PRIMARY KEY,
                name        TEXT UNIQUE NOT NULL,
                checksum    TEXT,
                applied_at  TIMESTAMPTZ DEFAULT now()
            )
        """)
        # Upgrade existing tables that lack the checksum column.
        await conn.execute(f"ALTER TABLE {target}_migration ADD COLUMN IF NOT EXISTS checksum TEXT")

    @staticmethod
    def _list_migrations(directory: Path) -> list[tuple[str, Path]]:
        """Return sorted list of (filename, path) for all .sql files in directory."""
        return sorted(
            ((f.name, f) for f in directory.glob("*.sql")),
            key=lambda t: t[0],
        )

    @staticmethod
    async def _get_applied(conn, schema: str | None = None) -> dict[str, str | None]:
        """Return dict of migration name → checksum for already-applied migrations."""
        target = f"{schema}." if schema else "public."
        rows = await conn.fetch(f"SELECT name, checksum FROM {target}_migration")
        return {row["name"]: row["checksum"] for row in rows}

    @staticmethod
    def _md5(content: str) -> str:
        return hashlib.md5(content.encode("utf-8")).hexdigest()
