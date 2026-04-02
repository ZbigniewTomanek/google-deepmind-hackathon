# Stage 1: Split Graph Template into Individual Migrations

**Goal**: Create `migrations/graph/` directory with individual per-schema SQL migration files, replacing the monolithic `graph_schema.sql` template.
**Dependencies**: None

---

## Important: SQL Source

Use `resources/graph-migration-sql.md` as the source for all SQL file content — it
contains the exact, ready-to-use SQL for each file. Do **not** copy-paste directly
from `migrations/templates/graph_schema.sql`, because the placeholder has been renamed
from `{schema_name}` (old template) to `{schema}` (new files) for brevity and
consistency with the runner API.

---

## Steps

1. **Rename `migrations/init/` to `migrations/public/`**
   - This is a directory rename only; all 11 SQL filenames stay the same.
   - The `public._migration` table already has these filenames recorded, so no
     re-application will occur.

2. **Create `migrations/graph/001_base_tables.sql`**
   - File: `migrations/graph/001_base_tables.sql`
   - Source: `migrations/templates/graph_schema.sql` lines 1-90
   - Content: `CREATE SCHEMA IF NOT EXISTS {schema}`, then CREATE TABLE for
     `node_type`, `edge_type`, `node`, `node_alias`, `edge`, `episode`, `_migration`.
   - All tables use `{schema}.table_name` qualified names and `IF NOT EXISTS`.
   - Include `content_hash TEXT` in the episode table (it's in the current template).
   - The `_migration` table in each schema is part of this file since it's needed
     for tracking subsequent graph migrations.

3. **Create `migrations/graph/002_indexes.sql`**
   - File: `migrations/graph/002_indexes.sql`
   - Source: `migrations/templates/graph_schema.sql` lines 92-141
   - Content: All 13 indexes (HNSW for node/episode embeddings, GIN for tsv/trgm,
     B-tree for edges, alias lookup, episode agent, content hash, node type,
     node forgotten).
   - Index names use `idx_{schema}_*` pattern.

4. **Create `migrations/graph/003_seed_ontology.sql`**
   - File: `migrations/graph/003_seed_ontology.sql`
   - Source: `migrations/templates/graph_schema.sql` lines 143-167
   - Content: INSERT INTO `{schema}.node_type` (6 types) and
     `{schema}.edge_type` (12 types including SUPERSEDES, CORRECTS).
   - Uses `ON CONFLICT (name) DO NOTHING` for idempotency.

5. **Create `migrations/graph/004_node_alias.sql`**
   - File: `migrations/graph/004_node_alias.sql`
   - This is a **no-op migration marker**. The node_alias table and its index are
     already created in `001_base_tables.sql` and `002_indexes.sql`.
   - Content: just a SQL comment explaining this is a placeholder for legacy
     compatibility with schemas that tracked `009_node_alias` separately.
   - Purpose: the legacy name mapping in the runner will recognize both
     `009_node_alias` and `004_node_alias.sql` as the same migration.

6. **Create `migrations/graph/005_content_hash.sql`**
   - File: `migrations/graph/005_content_hash.sql`
   - Same pattern as 004: a **no-op marker** since `content_hash` is already in the
     episode table DDL in `001_base_tables.sql`.
   - Purpose: legacy compatibility with `011_episode_content_hash` tracking entries.

7. **Delete `migrations/templates/graph_schema.sql`**
   - The template is fully replaced by the graph migration files.
   - The `{rls_block}` conditional logic stays in `SchemaManager._build_shared_provenance_block()`
     (modified in Stage 4).

---

## Verification

- [ ] `migrations/public/` exists with all 11 original SQL files (001-011)
- [ ] `migrations/init/` no longer exists
- [ ] `migrations/graph/` contains 5 files: 001-005
- [ ] `migrations/templates/graph_schema.sql` no longer exists
- [ ] Combined content of graph/001 + graph/002 + graph/003 covers all DDL from the old template
- [ ] All `{schema}` placeholders are consistent (not `{schema_name}`)
- [ ] `uv run pytest tests/ -v -x` — all existing tests pass (template path references may need updating)

---

## Commit

`refactor(migrations): split graph template into individual migration files`
