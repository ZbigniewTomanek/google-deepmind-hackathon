"""Unit tests for MigrationRunner — no Docker/PostgreSQL required."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from neocortex.migrations.runner import MigrationRunner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeConnection:
    """In-memory mock of an asyncpg connection.

    Tracks executed SQL and simulates a ``_migration`` tracking table so that
    the runner's ``_get_applied`` / ``_ensure_tracking_table`` calls work
    without a real database.
    """

    def __init__(self):
        # Schema-keyed tracking: "public" for public, schema name for per-schema
        self._applied_by_schema: dict[str, dict[str, str | None]] = {}
        self.executed: list[str] = []
        self.execute = AsyncMock(side_effect=self._handle_execute)
        self.fetch = AsyncMock(side_effect=self._handle_fetch)

    @property
    def _applied(self) -> dict[str, str | None]:
        """Shortcut for public-schema tracking (used by most tests)."""
        return self._applied_by_schema.setdefault("public", {})

    @_applied.setter
    def _applied(self, value: dict[str, str | None]):
        self._applied_by_schema["public"] = value

    def _schema_from_sql(self, sql: str) -> str:
        """Extract schema prefix from SQL like 'INSERT INTO ncx_foo__bar._migration'."""
        import re

        m = re.search(r"(ncx_[a-z0-9]+__[a-z0-9_]+)\._migration", sql)
        if m:
            return m.group(1)
        return "public"

    async def _handle_execute(self, sql: str, *args):
        self.executed.append(sql)
        if "INSERT INTO" in sql and "_migration" in sql:
            schema = self._schema_from_sql(sql)
            applied = self._applied_by_schema.setdefault(schema, {})
            applied[args[0]] = args[1] if len(args) > 1 else None

    async def _handle_fetch(self, sql: str, *args):
        if "_migration" in sql and "SELECT" in sql:
            schema = self._schema_from_sql(sql)
            applied = self._applied_by_schema.get(schema, {})
            return [{"name": n, "checksum": c} for n, c in applied.items()]
        if "graph_registry" in sql:
            return []
        return []

    def transaction(self):
        return _FakeTransaction()


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *args):
        return False


def _make_runner(tmp_path, public_files=None, graph_files=None):
    """Build a MigrationRunner that reads migrations from *tmp_path*."""
    public_dir = tmp_path / "public"
    graph_dir = tmp_path / "graph"
    public_dir.mkdir()
    graph_dir.mkdir()

    for name, content in public_files or []:
        (public_dir / name).write_text(content)

    for name, content in graph_files or []:
        (graph_dir / name).write_text(content)

    conn = _FakeConnection()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_FakeAcquire(conn))

    pg = MagicMock()
    pg.pool = pool

    runner = MigrationRunner(pg)
    # Override directory paths to use temp dirs
    runner._public_dir = public_dir
    runner._graph_dir = graph_dir

    return runner, conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_migrations_sorted(tmp_path):
    """_list_migrations returns .sql files sorted by name, skips non-SQL."""
    d = tmp_path / "mig"
    d.mkdir()
    (d / "002_second.sql").write_text("SELECT 2;")
    (d / "001_first.sql").write_text("SELECT 1;")
    (d / "003_third.sql").write_text("SELECT 3;")
    (d / "readme.md").write_text("not sql")
    (d / "notes.txt").write_text("also not sql")

    result = MigrationRunner._list_migrations(d)

    names = [name for name, _ in result]
    assert names == ["001_first.sql", "002_second.sql", "003_third.sql"]


@pytest.mark.asyncio
async def test_ensure_tracking_table_idempotent(tmp_path):
    """Calling _ensure_tracking_table twice doesn't error."""
    conn = _FakeConnection()
    # First call
    await MigrationRunner._ensure_tracking_table(conn)
    # Second call — should not raise
    await MigrationRunner._ensure_tracking_table(conn)
    # Both calls should have executed CREATE TABLE + ALTER TABLE
    create_calls = [s for s in conn.executed if "CREATE TABLE" in s]
    assert len(create_calls) == 2  # one per invocation, both IF NOT EXISTS


@pytest.mark.asyncio
async def test_run_public_applies_all(tmp_path):
    """run_public applies all pending migrations and returns correct count."""
    runner, conn = _make_runner(
        tmp_path,
        public_files=[
            ("001_first.sql", "SELECT 1;"),
            ("002_second.sql", "SELECT 2;"),
            ("003_third.sql", "SELECT 3;"),
        ],
    )

    count = await runner.run_public()

    assert count == 3
    assert "001_first.sql" in conn._applied
    assert "002_second.sql" in conn._applied
    assert "003_third.sql" in conn._applied


@pytest.mark.asyncio
async def test_run_public_skips_applied(tmp_path):
    """run_public skips migrations already recorded in the tracking table."""
    runner, conn = _make_runner(
        tmp_path,
        public_files=[
            ("001_first.sql", "SELECT 1;"),
            ("002_second.sql", "SELECT 2;"),
        ],
    )
    # Pre-insert migration as already applied
    conn._applied["001_first.sql"] = MigrationRunner._md5("SELECT 1;")

    count = await runner.run_public()

    assert count == 1  # only 002 applied
    assert "002_second.sql" in conn._applied


@pytest.mark.asyncio
async def test_run_public_idempotent(tmp_path):
    """Running run_public twice applies 0 on the second run."""
    runner, _conn = _make_runner(
        tmp_path,
        public_files=[
            ("001_first.sql", "SELECT 1;"),
            ("002_second.sql", "SELECT 2;"),
        ],
    )

    first = await runner.run_public()
    second = await runner.run_public()

    assert first == 2
    assert second == 0


@pytest.mark.asyncio
async def test_run_for_schema_replaces_placeholder(tmp_path):
    """run_for_schema replaces {schema} with the actual schema name."""
    runner, conn = _make_runner(
        tmp_path,
        graph_files=[
            ("001_base.sql", "CREATE TABLE {schema}.test_table (id INT);"),
        ],
    )

    await runner.run_for_schema("ncx_agent1__personal")

    # Find the SQL that was executed (skip CREATE SCHEMA / tracking table DDL)
    table_creates = [s for s in conn.executed if "test_table" in s]
    assert len(table_creates) == 1
    assert "ncx_agent1__personal.test_table" in table_creates[0]
    assert "{schema}" not in table_creates[0]


@pytest.mark.asyncio
async def test_legacy_name_mapping(tmp_path):
    """Pre-existing legacy name (009_node_alias) prevents re-applying 004_node_alias.sql."""
    runner, conn = _make_runner(
        tmp_path,
        graph_files=[
            ("004_node_alias.sql", "CREATE TABLE {schema}.node_alias (id INT);"),
        ],
    )
    # Simulate legacy tracking entry in the target schema
    schema_applied = conn._applied_by_schema.setdefault("ncx_agent1__personal", {})
    schema_applied["009_node_alias"] = None

    count = await runner.run_for_schema("ncx_agent1__personal")

    assert count == 0
    # The legacy mapping should have inserted the new name into tracking
    assert "004_node_alias.sql" in conn._applied_by_schema["ncx_agent1__personal"]


@pytest.mark.asyncio
async def test_checksum_mismatch_warning(tmp_path, caplog):
    """When a migration file changes after being applied, a warning is logged."""
    runner, conn = _make_runner(
        tmp_path,
        public_files=[
            ("001_first.sql", "SELECT 1;"),
        ],
    )
    # Pre-insert with a different checksum (simulating file content change)
    conn._applied["001_first.sql"] = "stale_checksum_does_not_match"

    with caplog.at_level("WARNING"):
        count = await runner.run_public()

    assert count == 0  # should not re-apply
    # Actual warning assertion is in test_checksum_mismatch_warning_logged below


@pytest.mark.asyncio
async def test_checksum_mismatch_warning_logged(tmp_path, monkeypatch):
    """Checksum mismatch emits a loguru warning (verified via monkeypatch)."""
    from loguru import logger

    warnings = []
    monkeypatch.setattr(logger, "warning", lambda *a, **kw: warnings.append((a, kw)))

    runner, conn = _make_runner(
        tmp_path,
        public_files=[
            ("001_first.sql", "SELECT 1;"),
        ],
    )
    conn._applied["001_first.sql"] = "wrong_checksum"

    count = await runner.run_public()

    assert count == 0
    assert len(warnings) == 1
    assert "checksum_mismatch" in str(warnings[0])


@pytest.mark.asyncio
async def test_run_graph_schemas_iterates_registry(tmp_path):
    """run_graph_schemas applies graph migrations to every schema in graph_registry."""
    runner, conn = _make_runner(
        tmp_path,
        graph_files=[
            ("001_base.sql", "CREATE TABLE {schema}.t (id INT);"),
        ],
    )

    # Simulate graph_registry returning two schemas
    original_fetch = conn._handle_fetch

    async def patched_fetch(sql, *args):
        if "graph_registry" in sql:
            return [
                {"schema_name": "ncx_a__personal"},
                {"schema_name": "ncx_b__personal"},
            ]
        return await original_fetch(sql, *args)

    conn.fetch = AsyncMock(side_effect=patched_fetch)

    total = await runner.run_graph_schemas()

    assert total == 2
    # Both schemas should have had their migration applied
    schema_creates = [s for s in conn.executed if "CREATE SCHEMA" in s]
    assert any("ncx_a__personal" in s for s in schema_creates)
    assert any("ncx_b__personal" in s for s in schema_creates)


@pytest.mark.asyncio
async def test_run_for_schema_rejects_invalid_name():
    """run_for_schema raises ValueError for invalid schema names."""
    pg = MagicMock()
    runner = MigrationRunner(pg)

    with pytest.raises(ValueError, match="Invalid graph schema name"):
        await runner.run_for_schema("not_a_valid_schema")

    with pytest.raises(ValueError, match="Invalid graph schema name"):
        await runner.run_for_schema("ncx_; DROP TABLE--")
