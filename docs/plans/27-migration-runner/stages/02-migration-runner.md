# Stage 2: MigrationRunner Class

**Goal**: Implement the core `MigrationRunner` class that applies public and per-schema graph migrations with tracking, checksums, and advisory locking.
**Dependencies**: Stage 1 (graph migration files must exist)

---

## Steps

1. **Create `src/neocortex/migrations/__init__.py`**
   - File: `src/neocortex/migrations/__init__.py`
   - Export `MigrationRunner` from `runner.py`.

2. **Create `src/neocortex/migrations/runner.py`**
   - File: `src/neocortex/migrations/runner.py`
   - Class: `MigrationRunner`

   **All DB-touching methods are `async`** — the codebase uses asyncpg throughout.

   **Connection pattern**: Acquire connections via `async with self._pg.pool.acquire() as conn:`.
   Each individual migration file is executed within its own transaction:
   `async with conn.transaction():`. Advisory locks are acquired on the outer
   connection, outside the per-migration transaction.

   **Constructor** `__init__(self, pg: PostgresService)`:
   - Store reference to `PostgresService`
   - Resolve `migrations/public/` and `migrations/graph/` paths relative to
     project root. Use the same resolution pattern as `schema_manager.py` line 21:
     `Path(__file__).resolve().parents[2] / "migrations"`.
   - Define legacy name mapping:
     ```python
     _LEGACY_GRAPH_NAMES: dict[str, str] = {
         "009_node_alias": "004_node_alias.sql",
         "011_episode_content_hash": "005_content_hash.sql",
     }
     ```

   **`async _ensure_tracking_table(conn, schema: str | None = None)`** (private, static):
   - If schema is None, target `public._migration`; else `{schema}._migration`.
   - `CREATE TABLE IF NOT EXISTS` with columns: `id SERIAL PRIMARY KEY`,
     `name TEXT UNIQUE NOT NULL`, `checksum TEXT`,
     `applied_at TIMESTAMPTZ DEFAULT now()`.
   - `ALTER TABLE ... ADD COLUMN IF NOT EXISTS checksum TEXT` for upgrading
     existing tables that lack the column.

   **`_list_migrations(directory: Path) -> list[tuple[str, Path]]`** (private):
   - Glob `*.sql`, sort by filename, return list of `(filename, path)` tuples.

   **`async _get_applied(conn, schema: str | None = None) -> dict[str, str | None]`** (private):
   - Query `SELECT name, checksum FROM {target}._migration`.
   - Return dict of `name -> checksum`.

   **`async def run_public(self) -> int`** (public):
   - Acquire advisory lock: `SELECT pg_advisory_lock(hashtext('neocortex_migration_public'))`.
   - Call `_ensure_tracking_table(conn)`.
   - Call `_list_migrations(self._public_dir)`.
   - Call `_get_applied(conn)`.
   - For each unapplied migration: read SQL, execute in transaction, record in
     `_migration` with name + MD5 checksum.
   - For already-applied: if checksum column is populated and doesn't match current
     file content, log a warning (do not re-apply).
   - Release advisory lock in `finally` block.
   - Return count of applied migrations.

   **`async def run_graph_schemas(self) -> int`** (public):
   - Acquire advisory lock: `SELECT pg_advisory_lock(hashtext('neocortex_migration_graph'))`.
   - Query `SELECT schema_name FROM graph_registry`.
   - For each schema: call `run_for_schema(schema_name)`.
   - Release advisory lock in `finally` block.
   - Return total count.

   **`async def run_for_schema(self, schema_name: str) -> int`** (public):
   - No advisory lock here — callers are either within `run_graph_schemas()`'s
     lock (bulk startup) or protected by CREATE SCHEMA IF NOT EXISTS + registry
     uniqueness constraint (`create_graph`). Individual schema runs are idempotent.
   - Validate schema name against `^ncx_[a-z0-9]+__[a-z0-9_]+$`.
   - Call `_ensure_tracking_table(conn, schema_name)`.
   - Call `_list_migrations(self._graph_dir)`.
   - Call `_get_applied(conn, schema_name)`.
   - Check legacy names: if `_LEGACY_GRAPH_NAMES` maps an old name that exists in
     applied set, treat the new filename as already applied (insert mapping entry).
   - For each unapplied migration: read SQL, replace `{schema}` with `schema_name`,
     execute in transaction, record in `{schema}._migration`.
   - Return count of applied migrations.

   **Logging**: Use `loguru.logger` with structured fields (`migration=name`,
   `schema=schema`, `action="applied"|"skipped"|"checksum_mismatch"`).

3. **Create `src/neocortex/migrations/__main__.py`**
   - File: `src/neocortex/migrations/__main__.py`
   - Standalone CLI entry point: `python -m neocortex.migrations`
   - Creates `PostgresConfig`, connects `PostgresService`, runs `run_public()` +
     `run_graph_schemas()`, prints summary, disconnects.
   - Uses `asyncio.run()`.

---

## Verification

- [ ] `uv run python -c "from neocortex.migrations import MigrationRunner"` — imports without error
- [ ] `uv run python -m neocortex.migrations --help` or just runs cleanly (may fail on DB connection if no PG — that's expected)
- [ ] Code review: no string interpolation of user input in SQL (only validated schema names and parameterized queries)
- [ ] `uv run pytest tests/ -v -x` — existing tests still pass

---

## Commit

`feat(migrations): add MigrationRunner with public and per-schema support`
