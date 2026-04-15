# Stage 1: Episode Session Tagging

**Goal**: Add `session_id` and `session_sequence` columns to the `episode` table so consecutive episodes within a conversation can be grouped and ordered without relying on insertion-time heuristics.
**Dependencies**: None

---

## Steps

### 1. Write public schema migration

Create `migrations/public/013_episode_session.sql`:

```sql
-- Plan 31, Stage 1: add session grouping to public episodes table
ALTER TABLE episode
    ADD COLUMN IF NOT EXISTS session_id TEXT,
    ADD COLUMN IF NOT EXISTS session_sequence INTEGER;

CREATE INDEX IF NOT EXISTS idx_episode_session
    ON episode (agent_id, session_id, session_sequence)
    WHERE session_id IS NOT NULL;
```

### 2. Write per-graph schema migration

Create `migrations/graph/007_episode_session.sql`:

```sql
-- Plan 31, Stage 1: add session grouping to per-agent graph episodes table
ALTER TABLE {schema}.episode
    ADD COLUMN IF NOT EXISTS session_id TEXT,
    ADD COLUMN IF NOT EXISTS session_sequence INTEGER;

CREATE INDEX IF NOT EXISTS idx_episode_session
    ON {schema}.episode (agent_id, session_id, session_sequence)
    WHERE session_id IS NOT NULL;
```

The `{schema}` placeholder is substituted by `MigrationRunner` at apply time (same pattern as all other graph-schema migrations).

### 3. Add `session_id` to the ingestion text endpoint request model

File: `src/neocortex/ingestion/routes.py` (for import context) and the ingestion models file it imports from.

Find the `TextIngestionRequest` Pydantic model — it is **defined in the ingestion models file** that `routes.py` imports from, not inline in `routes.py` itself. Add an optional `session_id: str | None = None` field. When the caller supplies it, it is stored on the episode. When absent, generate a UUID with `str(uuid.uuid4())` as a per-request fallback so every episode always has a session_id.

Also add `session_id` to the events ingestion request model (`EventsIngestionRequest`) — it is defined in the same models file.

### 4. Propagate `session_id` through episode creation

File: `src/neocortex/ingestion/episode_processor.py`

The `_store_episode` private method (around lines 123–126) makes two repo calls depending on whether a target schema is set:
- `self._repo.store_episode_to(agent_id, target_schema, text, source_type=..., content_hash=...)` — explicit-schema path
- `self._repo.store_episode(agent_id, text, source_type=..., content_hash=...)` — default-schema path

Add `session_id=session_id` to both calls. Also add `session_id: str | None = None` to `_store_episode`'s own parameter list and thread it from the caller. When not provided, default to a fresh UUID (same fallback as step 3).

The `session_sequence` column will be populated in Stage 2. For now, leave it `NULL` to keep this stage atomic.

### 5. Verify `MemoryRepository` protocol accepts session_id

File: `src/neocortex/db/protocol.py`

Locate the `store_episode` method signature. If it takes keyword arguments via a dict or `**kwargs`, no change is needed. If it takes positional fields, add `session_id: str | None = None` as a parameter. Ensure `db/mock.py` (in-memory repo) also handles the new field — add it to the in-memory episode data structure without failing.

### 6. Confirm `InMemoryRepository` stores session_id

File: `src/neocortex/db/mock.py`

Find the episode storage dict/list. Ensure `session_id` is stored and retrievable. The mock doesn't need to enforce ordering or uniqueness.

---

## Verification

- [ ] `uv run pytest tests/ -v -k episode` passes with no new failures
- [ ] Apply the migrations manually against the test DB and confirm columns exist:
  ```sql
  SELECT column_name FROM information_schema.columns
  WHERE table_name = 'episode' AND column_name IN ('session_id', 'session_sequence');
  ```
  Expected: 2 rows returned.
- [ ] Ingest a test episode via the API with an explicit `session_id` and confirm it is stored:
  ```bash
  .claude/skills/neocortex/scripts/ingest.sh text \
    --content "Test session tagging" \
    --session-id "test-session-001"
  ```
  Then query the DB: `SELECT session_id FROM episode WHERE content = 'Test session tagging'` — should return `test-session-001`.
- [ ] Ingest an episode WITHOUT `session_id` and confirm a UUID is auto-assigned (non-null).

---

## Commit

`feat(episodes): add session_id and session_sequence columns for temporal grouping`
