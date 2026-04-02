# Stage 4: Update SchemaManager to Use MigrationRunner

**Goal**: Replace template rendering and ensure_* methods in `SchemaManager` with delegation to `MigrationRunner.run_for_schema()`.
**Dependencies**: Stage 3 (runner is wired into services)

---

## Steps

1. **Update `SchemaManager.__init__` to accept `MigrationRunner`**
   - File: `src/neocortex/schema_manager.py`
   - Add `migration_runner: MigrationRunner` parameter to `__init__`.
   - Remove `self._template_path` resolution (no longer needed).

2. **Update `create_graph()` to use the runner**
   - File: `src/neocortex/schema_manager.py`
   - Current flow: `_render_template()` renders the monolithic SQL, executes it.
   - New flow:
     1. `CREATE SCHEMA IF NOT EXISTS {schema_name}` (single execute statement)
     2. `await self._migration_runner.run_for_schema(schema_name)` — applies all
        graph migrations in order
     3. If `is_shared`: call `self._apply_shared_provenance(conn, schema_name)` —
        this is the existing `_build_shared_provenance_block()` logic, kept as-is
     4. Insert into `graph_registry` (existing logic, kept as-is)
   - Handle the existing race-condition detection (`UniqueViolationError` on
     registry insert) — same pattern, just the schema creation method changes.

3. **Delete `_render_template()` method**
   - File: `src/neocortex/schema_manager.py`
   - Search for `def _render_template` — remove entirely.

4. **Delete `ensure_alias_tables()` method**
   - File: `src/neocortex/schema_manager.py`
   - Search for `def ensure_alias_tables` — remove entirely (~40 lines).

5. **Delete `ensure_content_hash()` method**
   - File: `src/neocortex/schema_manager.py`
   - Search for `def ensure_content_hash` — remove entirely (~35 lines).

6. **Remove `apply_migration()` from `postgres_service.py`**
   - File: `src/neocortex/postgres_service.py`
   - Search for `def apply_migration` — remove method (~14 lines).
   - This method is currently unused (all callers use ensure_* or shell script).
   - Its functionality is fully superseded by `MigrationRunner`.

7. **Update `SchemaManager` constructor call in `services.py`**
   - File: `src/neocortex/services.py`
   - Change `SchemaManager(pg)` to `SchemaManager(pg, migration_runner)`.

---

## Verification

- [ ] Grep for `_render_template` in `schema_manager.py` — zero results
- [ ] Grep for `ensure_alias_tables` in entire project — zero results (except plan docs)
- [ ] Grep for `ensure_content_hash` in entire project — zero results (except plan docs)
- [ ] Grep for `def apply_migration` in `postgres_service.py` — zero results
- [ ] Grep for `graph_schema.sql` in entire project — zero results (except plan docs)
- [ ] `uv run pytest tests/ -v -x` — all existing tests pass
- [ ] Review `create_graph()` flow: schema creation + migrations + RLS + registry

---

## Commit

`refactor(schema): replace template rendering with MigrationRunner in SchemaManager`
