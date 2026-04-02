# Plan: Unified Migration Runner

**Date**: 2026-04-02
**Branch**: feat/migration-runner
**Predecessors**: None
**Goal**: Replace the fragile, multi-path migration system with a single Python-based `MigrationRunner` that handles both public schema and dynamic per-agent graph schema migrations.

---

## Context

The current migration system has **three separate code paths** that apply SQL
migrations, leading to duplication and fragility:

1. **Docker entrypoint** (`docker-compose.yml:23`): mounts `migrations/init/` to
   `/docker-entrypoint-initdb.d/` — runs only on fresh container creation, no tracking.
2. **Shell script** (`scripts/manage.sh:112-133`): iterates `migrations/init/*.sql`
   alphabetically, checks/records in `public._migration` table using `psql` with
   unquoted variable interpolation.
3. **Python ensure_* methods** (`schema_manager.py:142-216`): two hand-coded methods
   (`ensure_alias_tables`, `ensure_content_hash`) that iterate all registered graph
   schemas on every startup and apply inline SQL. Each new per-schema migration
   requires a new method.

Additionally, `migrations/templates/graph_schema.sql` (170 lines) duplicates content
from init migrations 002, 003, 004, 009, 010, 011 — any schema change must be synced
in two places.

**Key pain points:**
- Template duplication between `migrations/init/` and `migrations/templates/`
- Each new per-schema migration requires a new hand-coded method
- Shell script uses unquoted SQL interpolation
- No rollback support, no checksum validation
- Three code paths for the same concern

**Decision: Custom solution over external libraries.**
- **Alembic**: pulls in SQLAlchemy (~2.5MB) for a raw-SQL + asyncpg project; its
  multi-schema support requires custom `env.py` hacking and assumes schemas are
  known at dev-time, not created dynamically at runtime.
- **yoyo-migrations**: primarily synchronous, less maintained, poor fit for N-dynamic-schemas.
- **dbmate**: external Go binary, can't participate in asyncpg transactions, not pip-installable.

The project's core requirement — applying the same migration to N dynamically-created
schemas — is unsupported by all three. The existing `postgres_service.apply_migration()`
method proves the pattern works; it just needs generalization.

---

## Strategy

**Phase A (Foundation — Stages 1-2)**: Create `migrations/graph/` directory by
splitting the monolithic template into individual migration files. Build the
`MigrationRunner` class with public and per-schema migration support.

**Phase B (Integration — Stages 3-5)**: Wire the runner into `services.py` and
`schema_manager.py`, update `manage.sh`, remove Docker entrypoint mount, delete
the old template and ensure_* methods.

**Phase C (Verification — Stage 6)**: End-to-end validation, test updates, cleanup.

---

## Success Criteria

| Metric | Baseline | Target | Rationale |
|--------|----------|--------|-----------|
| Migration code paths | 3 (Docker, shell, Python ensure_*) | 1 (MigrationRunner) | Single source of truth |
| Lines to add a per-schema migration | ~40 (new ensure_* method) | 1 SQL file | Developer friction |
| Template duplication | graph_schema.sql duplicates 6 init files | Zero duplication | Maintenance burden |
| Existing tests | All pass | All pass | No regressions |
| Migration CLI | None | `python -m neocortex.migrations` | Operational tooling |

---

## Files That May Be Changed

### New files
- `src/neocortex/migrations/__init__.py` -- Package init, exports MigrationRunner
- `src/neocortex/migrations/runner.py` -- Core MigrationRunner class
- `src/neocortex/migrations/__main__.py` -- CLI entry point
- `migrations/graph/001_base_tables.sql` -- Schema + tables (from template lines 1-90)
- `migrations/graph/002_indexes.sql` -- All graph-schema indexes (from template lines 92-141)
- `migrations/graph/003_seed_ontology.sql` -- Default node/edge types (from template lines 143-167)
- `migrations/graph/004_node_alias.sql` -- node_alias table (from ensure_alias_tables)
- `migrations/graph/005_content_hash.sql` -- episode.content_hash (from ensure_content_hash)
- `tests/test_migration_runner.py` -- Unit tests for MigrationRunner

### Modified files
- `src/neocortex/services.py` -- Replace ensure_* calls with MigrationRunner
- `src/neocortex/schema_manager.py` -- Remove ensure_*, _render_template; accept runner in create_graph
- `scripts/manage.sh` -- Replace shell migration loop with Python invocation
- `docker-compose.yml` -- Remove initdb.d volume mount

### Deleted files
- `migrations/templates/graph_schema.sql` -- Replaced by migrations/graph/

### Renamed directories
- `migrations/init/` -> `migrations/public/` -- Clarifies purpose; filenames preserved for tracking compatibility

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [Split graph template](stages/01-graph-migrations.md) | DONE | Renamed init→public, created graph/001-005, deleted template, updated SchemaManager._render_template to read graph/ files | `refactor(migrations): split graph template into individual migration files` |
| 2 | [MigrationRunner class](stages/02-migration-runner.md) | DONE | Created migrations package: __init__.py, runner.py (MigrationRunner with public/graph/per-schema support, advisory locks, checksums, legacy name mapping), __main__.py (CLI) | `feat(migrations): add MigrationRunner with public and per-schema support` |
| 3 | [Wire into services](stages/03-wire-services.md) | DONE | Replaced ensure_alias_tables/ensure_content_hash with MigrationRunner.run_public() + run_graph_schemas() in correct order; mock DB path untouched | `refactor(services): replace ensure_* methods with MigrationRunner at startup` |
| 4 | [Update SchemaManager](stages/04-update-schema-manager.md) | DONE | Replaced _render_template with MigrationRunner.run_for_schema in create_graph; deleted ensure_alias_tables, ensure_content_hash, _render_template; removed apply_migration from postgres_service; fixed runner path resolution (parents[2]→[3]) and added CREATE SCHEMA before tracking table | `refactor(schema): replace template rendering with MigrationRunner in SchemaManager` |
| 5 | [Shell script & Docker cleanup](stages/05-shell-docker-cleanup.md) | DONE | Replaced shell migration loops in manage.sh and run_e2e_auth0.sh with `uv run python -m neocortex.migrations`; removed Docker initdb mount; updated migrations/init refs in CLAUDE.md and docs/development.md | `refactor(ops): replace shell migration loop with Python runner, remove Docker initdb mount` |
| 6 | [Tests & verification](stages/06-tests-verification.md) | DONE | Created test_migration_runner.py (10 tests: list/sort, idempotent tracking, apply/skip/idempotent public, schema placeholder, legacy mapping, checksum warning, invalid name); all 770+10 tests pass; no stale refs; mock DB starts clean | `test(migrations): add MigrationRunner tests and verify end-to-end` |

Statuses: `PENDING` -> `IN_PROGRESS` -> `DONE` | `BLOCKED` | `SKIPPED`

---

## Execution Protocol

To execute this plan, follow this loop for each stage:

1. **Read the progress tracker** above and find the first stage that is not DONE
2. **Read the stage file** -- follow the link in the tracker to the stage's .md file
3. **Read resources** -- if the stage references shared resources,
   find them in the `resources/` directory
4. **Clarify ambiguities** -- if anything is unclear or multiple approaches exist,
   ask the user before implementing. Do not guess.
5. **Implement** -- execute the steps described in the stage
6. **Validate** -- run the verification checks listed in the stage.
   If validation fails, fix the issue before proceeding. Do not skip verification.
7. **Update this index** -- mark the stage as DONE in the progress tracker,
   add brief notes about what was done and any deviations
8. **Commit** -- create an atomic commit with the message specified in the stage.
   Include all changed files (code, config, docs, and this plan's index.md).

Repeat until all stages are DONE or a stage is BLOCKED.

**If a stage cannot be completed**: mark it BLOCKED in the tracker with a note
explaining why, and stop. Do not proceed to subsequent stages.

**If assumptions are wrong**: stop, document the issue in the Issues section below,
revise affected stages, and get user confirmation before continuing.

---

## Issues

[Document any problems discovered during execution]

---

## Decisions

1. **Custom runner over Alembic/yoyo/dbmate** — The dynamic N-schema pattern is
   unsupported by existing libraries. Adding SQLAlchemy for Alembic would be
   a large dependency for a project that uses raw SQL. The existing
   `postgres_service.apply_migration()` proves the pattern works.

2. **Graph migrations use `{schema}` placeholder** — Same pattern as the current
   template but split into individual files. The runner renders each file by replacing
   `{schema}` with the target schema name.

3. **RLS provisioning stays in Python** — The `{rls_block}` in the current template
   is conditionally applied only for shared graphs. This conditional logic is better
   expressed in `SchemaManager._apply_shared_provenance()` than in a SQL migration
   with conditional execution.

4. **Legacy name mapping for transition** — Old per-schema tracking entries
   (`009_node_alias`, `011_episode_content_hash`) map to new filenames
   (`004_node_alias.sql`, `005_content_hash.sql`) so existing schemas are not
   re-migrated.

5. **Advisory lock for concurrency** — The runner acquires `pg_advisory_lock` before
   starting to prevent concurrent migration runs from multiple app instances.
