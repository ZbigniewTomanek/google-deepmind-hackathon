# Stage 1: Episode Session Tagging

**Goal**: Add `session_id` and `session_sequence` to stored episodes so conversation/request batches can be grouped and ordered without relying on extraction completion order.
**Dependencies**: None

---

## Design Constraints

- `session_id` is first-class episode data, not metadata-only.
- `EpisodeProcessor` owns fallback generation: when no caller-supplied session is present, generate exactly one `str(uuid.uuid4())` per ingestion request and apply it to every episode created by that request.
- `session_sequence` is assigned at storage time in the repository layer, not during extraction. This avoids out-of-order extraction jobs producing incorrect chronology.
- Update every path that creates episodes: text, events, document, audio, video, direct processor calls, real adapter, mock adapter, and `GraphService` fallback.
- While touching `_store_episode`, pass existing `metadata` through to the repository. The current API accepts metadata but `EpisodeProcessor` does not persist it; leaving that behavior in place would make session/provenance tests misleading.

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
    ON episode (agent_id, session_id, session_sequence, created_at, id)
    WHERE session_id IS NOT NULL;
```

Public migrations still matter for `GraphService` / pool-less fallback paths.

### 2. Write per-graph schema migration

Create `migrations/graph/007_episode_session.sql`:

```sql
-- Plan 31, Stage 1: add session grouping to per-agent graph episodes table
ALTER TABLE {schema}.episode
    ADD COLUMN IF NOT EXISTS session_id TEXT,
    ADD COLUMN IF NOT EXISTS session_sequence INTEGER;

CREATE INDEX IF NOT EXISTS idx_episode_session
    ON {schema}.episode (agent_id, session_id, session_sequence, created_at, id)
    WHERE session_id IS NOT NULL;

-- Used by personal FOLLOWS creation in Stage 2. Compare as text in queries.
CREATE INDEX IF NOT EXISTS idx_node_source_episode
    ON {schema}.node ((properties->>'_source_episode'));
```

The `{schema}` placeholder is substituted by `MigrationRunner.run_for_schema()`.

### 3. Add request/session fields to ingestion models and routes

Files:
- `src/neocortex/ingestion/models.py`
- `src/neocortex/ingestion/routes.py`
- `src/neocortex/ingestion/protocol.py`

In `TextIngestionRequest` and `EventsIngestionRequest`, add:

```python
session_id: str | None = Field(
    default=None,
    description="Conversation/session grouping id. If omitted, one UUID is generated per ingestion request.",
)
```

In `routes.py`:

- Pass `body.session_id` to `processor.process_text(...)`.
- Pass `body.session_id` to `processor.process_events(...)`.
- Add `session_id: str | None = Form(default=None)` to `/document`, `/audio`, and `/video`.
- Pass that `session_id` to the matching processor methods.

In `IngestionProcessor` (`src/neocortex/ingestion/protocol.py`), add `session_id: str | None = None` to `process_text`, `process_events`, `process_document`, `process_audio`, and `process_video`.

### 4. Propagate session_id and metadata in EpisodeProcessor

File: `src/neocortex/ingestion/episode_processor.py`

Import `uuid`.

Update `_store_episode` to accept and forward both `metadata` and `session_id`:

```python
async def _store_episode(
    self,
    agent_id: str,
    text: str,
    source_type: str,
    target_schema: str | None = None,
    content_hash: str | None = None,
    metadata: dict | None = None,
    session_id: str | None = None,
) -> int:
    if session_id is None:
        session_id = str(uuid.uuid4())
    if target_schema:
        return await self._repo.store_episode_to(
            agent_id,
            target_schema,
            text,
            source_type=source_type,
            content_hash=content_hash,
            metadata=metadata,
            session_id=session_id,
        )
    return await self._repo.store_episode(
        agent_id,
        text,
        source_type=source_type,
        content_hash=content_hash,
        metadata=metadata,
        session_id=session_id,
    )
```

Update each processor method:

- Add `session_id: str | None = None` to its signature.
- At the start of each public processing method, compute `request_session_id = session_id or str(uuid.uuid4())`.
- Pass `request_session_id` to every `_store_episode` call in that request.
- Pass the existing `metadata` dict to `_store_episode`.

For `process_events`, all events in the same request must use the same `request_session_id`.

For `_process_media`, add a `session_id` parameter and pass it from `process_audio` / `process_video`.

### 5. Update MemoryRepository and storage implementations

Files:
- `src/neocortex/db/protocol.py`
- `src/neocortex/db/adapter.py`
- `src/neocortex/db/mock.py`
- `src/neocortex/graph_service.py`
- `src/neocortex/models.py`

Add optional fields to `MemoryRepository.store_episode` and `store_episode_to`:

```python
session_id: str | None = None
```

Add fields to `Episode`:

```python
session_id: str | None = None
session_sequence: int | None = None
```

In `GraphServiceAdapter.store_episode` and `store_episode_to`:

- Include `session_id` and `session_sequence` in the INSERT.
- Assign `session_sequence` before INSERT inside the same connection.
- Use a transaction and `pg_advisory_xact_lock` keyed on `schema_name`, `agent_id`, and `session_id` so concurrent stores in the same session do not assign duplicate sequence values.
- For `session_id is None`, store `NULL` and leave sequence `NULL`; `EpisodeProcessor` should normally prevent this for ingestion paths, but direct repository callers may omit it.
- Use `json.dumps(metadata)` and `$n::jsonb` as existing code does.

Concrete sequence query:

```sql
SELECT COALESCE(MAX(session_sequence), 0) + 1
FROM episode
WHERE agent_id = $1 AND session_id = $2
```

In `GraphService.create_episode`, add `session_id` and insert/read `session_id, session_sequence`. Since this fallback writes public tables directly, assign public `session_sequence` similarly or leave `NULL` only if implementing the lock is impractical in that path. Tests should cover the adapter path as primary.

In `InMemoryRepository`:

- Add `session_id` and `session_sequence` to `EpisodeRecord`.
- Store them in both `store_episode` and `store_episode_to`.
- Assign sequence by counting existing records for the same `agent_id` and `session_id` in the relevant bucket.
- Make `store_episode_to` preserve the same fields as `store_episode`: metadata, access counters, last access, importance, consolidated, and content hash.

### 6. Update episode read paths

Files:
- `src/neocortex/db/adapter.py`
- `src/neocortex/db/mock.py`
- `src/neocortex/graph_service.py`

Include `session_id` and `session_sequence` in `get_episode` SELECTs and `Episode(...)` construction. This lets tests verify the new fields through the repository contract instead of internal mock state.

---

## Verification

- [ ] `uv run pytest tests/ -v -k "episode or ingestion"` passes with no new failures.
- [ ] Apply migrations against a test DB and confirm both personal graph and public columns:
  ```sql
  SELECT column_name
  FROM information_schema.columns
  WHERE table_name = 'episode'
    AND column_name IN ('session_id', 'session_sequence');
  ```
  Expected: 2 rows for each checked schema/table.
- [ ] Ingest explicit session via raw API or an updated CLI wrapper:
  ```bash
  curl -sS -X POST http://localhost:8001/ingest/text \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer claude-code-work" \
    -d '{"text":"Test session tagging","session_id":"test-session-001"}'
  ```
  Then query the personal graph: `SELECT session_id, session_sequence FROM ncx_anonymous__personal.episode WHERE content = 'Test session tagging';`.
- [ ] Ingest without `session_id` and confirm `session_id IS NOT NULL` and `session_sequence = 1` for the new session.
- [ ] Ingest three events in one `/ingest/events` request without `session_id`; confirm all three rows have the same generated `session_id` and `session_sequence` values `1, 2, 3`.
- [ ] Document/audio/video ingestion either accepts an explicit form `session_id` or generates a non-null fallback.
- [ ] Duplicate ingestion with `force=false` may return `status="skipped"` and create no new episode; do not count this as a session-tagging failure.

---

## Commit

`feat(episodes): add session grouping and storage-time ordering`
