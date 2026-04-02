# Stage 3: Wire MigrationRunner into Service Startup

**Goal**: Replace the `ensure_alias_tables()` and `ensure_content_hash()` calls in `services.py` with `MigrationRunner`, making it the single entry point for all migrations at startup.
**Dependencies**: Stage 2 (MigrationRunner must exist)

---

## Steps

1. **Update `src/neocortex/services.py`**
   - File: `src/neocortex/services.py`
   - In `create_services()`, after `pg.connect()` and before `SchemaManager` usage,
     add the migration runner:
     ```python
     from neocortex.migrations import MigrationRunner

     migration_runner = MigrationRunner(pg)
     await migration_runner.run_public()
     ```
   - After `schema_mgr.create_graph("shared", "knowledge", ...)` and the seed domain
     graph creation loop, run per-schema migrations:
     ```python
     await migration_runner.run_graph_schemas()
     ```
   - Remove the two lines:
     ```python
     await schema_mgr.ensure_alias_tables()
     await schema_mgr.ensure_content_hash()
     ```
   - Pass `migration_runner` to `SchemaManager` constructor (see Stage 4).
   - The ordering matters: public migrations first (creates `graph_registry` table),
     then create_graph (populates registry), then graph schema migrations.

2. **Guard for mock DB mode**
   - In the mock-DB early-return path (search for `settings.mock_db`), the runner
     should NOT be instantiated — mock mode uses `InMemoryRepository` and has no
     real PostgreSQL connection.
   - The existing early return already handles this; just ensure no runner code
     runs before that guard.

3. **Store runner in ServiceContext (optional)**
   - If `ServiceContext` is a TypedDict, add `migration_runner: MigrationRunner | None`
     to make it accessible to other components if needed in the future.
   - If this is too invasive, skip — the runner is only needed at startup.

---

## Verification

- [ ] `NEOCORTEX_MOCK_DB=true uv run python -m neocortex` — mock mode starts without errors (runner is skipped)
- [ ] `uv run pytest tests/ -v -x` — all existing tests pass
- [ ] Grep for `ensure_alias_tables` and `ensure_content_hash` in `services.py` — zero results
- [ ] `services.py` calls `migration_runner.run_public()` before any `SchemaManager` usage
- [ ] `services.py` calls `migration_runner.run_graph_schemas()` after graph creation

---

## Commit

`refactor(services): replace ensure_* methods with MigrationRunner at startup`
