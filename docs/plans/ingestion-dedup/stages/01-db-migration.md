# Stage 1: DB Migration — Add content_hash Column

**Goal**: Add a `content_hash` column and index to the episode table in both the public schema and the per-agent schema template.
**Dependencies**: None

---

## Steps

1. **Create migration `011_episode_content_hash.sql`**
   - File: `migrations/init/011_episode_content_hash.sql`
   - Details: Add `content_hash TEXT` column (nullable — existing episodes won't have one) and a B-tree index on `(agent_id, content_hash)` for fast dedup lookups. No unique constraint — the `force` flag allows intentional duplicates.
   ```sql
   -- Add content hash for ingestion deduplication
   ALTER TABLE episode ADD COLUMN IF NOT EXISTS content_hash TEXT;
   CREATE INDEX IF NOT EXISTS idx_episode_content_hash
       ON episode (agent_id, content_hash)
       WHERE content_hash IS NOT NULL;
   ```

2. **Update the per-agent schema template**
   - File: `migrations/templates/graph_schema.sql`
   - Details: Add `content_hash TEXT` to the `CREATE TABLE episode` block (after `source_type`). Add a matching index. Search for the pattern `source_type     TEXT,` in the episode table DDL and add the new column after it. Add the index after the existing episode indexes.
   ```sql
   -- In CREATE TABLE:
   content_hash    TEXT,

   -- After existing episode indexes:
   CREATE INDEX IF NOT EXISTS idx_{schema_name}_episode_content_hash
       ON {schema_name}.episode (agent_id, content_hash)
       WHERE content_hash IS NOT NULL;
   ```

3. **Add per-schema migration method to SchemaManager**
   - File: `src/neocortex/schema_manager.py`
   - Details: Add an `ensure_content_hash()` method following the same pattern as `ensure_alias_tables()`. It should:
     - Check `{schema_name}._migration` for `'011_episode_content_hash'`
     - If not applied: `ALTER TABLE {schema_name}.episode ADD COLUMN IF NOT EXISTS content_hash TEXT` + create index
     - Insert migration record
   - Call this method from wherever `ensure_alias_tables()` is called (likely `ensure_schema_up_to_date()` or similar).

---

## Verification

- [ ] `migrations/init/011_episode_content_hash.sql` exists with correct SQL
- [ ] `migrations/templates/graph_schema.sql` includes `content_hash TEXT` in episode table and index
- [ ] `schema_manager.py` has `ensure_content_hash()` method
- [ ] `uv run pytest tests/ -v -x` — all existing tests pass (no regressions)

---

## Commit

`feat(db): add content_hash column to episode table for ingestion dedup`
