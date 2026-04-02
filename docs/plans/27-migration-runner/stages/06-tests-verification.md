# Stage 6: Tests & End-to-End Verification

**Goal**: Add unit tests for MigrationRunner and verify the full system works end-to-end.
**Dependencies**: Stages 1-5 (all changes complete)

---

## Steps

1. **Create `tests/test_migration_runner.py`**
   - File: `tests/test_migration_runner.py`
   - Tests should work without Docker (use mock DB or in-memory patterns from
     existing test suite — check `tests/conftest.py` for fixtures).

   **Test cases:**

   a. `test_list_migrations_sorted` — verify `_list_migrations()` returns files
      sorted by numeric prefix, skips non-SQL files.

   b. `test_ensure_tracking_table_idempotent` — calling `_ensure_tracking_table`
      twice doesn't error; table has expected columns including `checksum`.

   c. `test_run_public_applies_all` — with a mock/temp migration directory containing
      2-3 small SQL files, verify `run_public()` applies them all and returns correct count.

   d. `test_run_public_skips_applied` — pre-insert a migration name into tracking table,
      verify it's skipped on next run.

   e. `test_run_public_idempotent` — run twice, second returns 0 applied.

   f. `test_run_for_schema_replaces_placeholder` — verify `{schema}` is replaced
      with actual schema name before execution.

   g. `test_legacy_name_mapping` — pre-insert `009_node_alias` into a schema's
      `_migration` table, verify `004_node_alias.sql` is treated as applied.

   h. `test_checksum_mismatch_warning` — apply a migration, change the file content,
      run again, verify a warning is logged (not re-applied).

2. **Update existing test files that instantiate SchemaManager**
   - `tests/conftest.py` has no direct `SchemaManager` instantiation or migration
     path references — no changes needed there.
   - File: `tests/test_scoped_connections.py` — instantiates `SchemaManager(pg_service)`
     at lines 21, 51, 73, 93. Update each to pass a `MigrationRunner` (or mock) as
     the second argument.
   - File: `tests/test_server_lifespan.py` — instantiates `SchemaManager(pg_service)`
     at line 20. Update to pass a `MigrationRunner` (or mock).
   - Search for any other `SchemaManager(` constructor calls across the test suite
     to catch any missed instances.

3. **Verify mock DB mode**
   - Run: `NEOCORTEX_MOCK_DB=true uv run python -m neocortex`
   - Verify: starts without errors, no migration runner code is executed.

4. **Verify CLI entry point**
   - If a local PostgreSQL is available:
     ```bash
     POSTGRES_HOST=localhost POSTGRES_PORT=5432 POSTGRES_USER=neocortex \
       POSTGRES_PASSWORD=neocortex POSTGRES_DATABASE=neocortex \
       uv run python -m neocortex.migrations
     ```
   - Should print summary like: `Applied 11 public + 0 graph-schema migrations`
     (on fresh DB) or `Applied 0 public + 0 graph-schema migrations` (on already-migrated DB).

5. **Full test suite**
   - Run: `uv run pytest tests/ -v`
   - All tests must pass.

---

## Verification

- [ ] `tests/test_migration_runner.py` exists with >= 6 test functions
- [ ] `uv run pytest tests/test_migration_runner.py -v` — all pass
- [ ] `uv run pytest tests/ -v` — full suite passes
- [ ] `NEOCORTEX_MOCK_DB=true uv run python -m neocortex` — starts cleanly
- [ ] No references to `ensure_alias_tables` or `ensure_content_hash` remain in code
- [ ] No references to `migrations/init` remain in code (except plan docs, git history)
- [ ] No references to `graph_schema.sql` template remain in code (except plan docs)

---

## Commit

`test(migrations): add MigrationRunner tests and verify end-to-end`
