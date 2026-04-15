# Stage 2: Personal FOLLOWS Edge Creation in Extraction

**Goal**: After personal-graph extraction finishes, link the current episode to the immediately preceding personal episode in the same session with a `FOLLOWS` edge. Shared/domain extraction must not create temporal edges.
**Dependencies**: Stage 1 (`session_id`, `session_sequence`, and `idx_node_source_episode` migration must exist)

---

## Background

The `FOLLOWS` edge type already exists in `migrations/graph/003_seed_ontology.sql`. It has not been created automatically.

Temporal ordering is personal-memory behavior. Domain graphs can receive facts extracted from personal episodes, but they must not receive session chronology edges. Domain-routed extraction uses `target_schema=<shared>` and `source_schema="__personal__"`; explicit target-graph ingestion uses `target_schema=<shared>`. Both cases are non-personal for `FOLLOWS` creation.

The extraction pipeline works through the `MemoryRepository` protocol. Add repository methods for consolidation and personal temporal linking; keep raw DB logic inside `GraphServiceAdapter`.

---

## Steps

### 1. Make consolidation target-aware

Files:
- `src/neocortex/db/protocol.py`
- `src/neocortex/db/adapter.py`
- `src/neocortex/db/mock.py`
- `src/neocortex/extraction/pipeline.py`

Change the protocol signature:

```python
async def mark_episode_consolidated(
    self,
    agent_id: str,
    episode_id: int,
    target_schema: str | None = None,
) -> None:
    """Mark an episode as consolidated in the schema where the episode row lives."""
```

Implementation rules:

- When `target_schema is None`, mark the agent's personal schema, preserving current behavior.
- When `target_schema` is set, mark that schema using `graph_scoped_connection`.
- In `pipeline.py`, pass the schema used to read the episode row, not the schema used to write extracted nodes.

The pipeline already computes:

```python
read_schema: str | None = target_schema if source_schema is _UNSET else source_schema
```

Use `read_schema` for consolidation:

```python
await repo.mark_episode_consolidated(agent_id, episode_id, target_schema=read_schema)
```

In the fallback helper `_persist_payload`, add an `episode_schema: str | None = None` parameter and pass `episode_schema=read_schema` from `run_extraction`. Use that value in its consolidation call.

### 2. Add personal-only link method to MemoryRepository

File: `src/neocortex/db/protocol.py`

Add after `mark_episode_consolidated`:

```python
async def link_personal_episode_to_session_predecessor(
    self,
    agent_id: str,
    episode_id: int,
) -> None:
    """Create a personal-graph FOLLOWS edge from this episode to its predecessor.

    Always operates on the agent's personal schema. No-op when the episode has
    no session_id, no predecessor exists, no extracted nodes exist for either
    episode, or the FOLLOWS type is missing.
    """
    ...
```

Do not include `target_schema` in this method. The absence is intentional: `FOLLOWS` is personal-only.

### 3. Implement personal-only linking in GraphServiceAdapter

File: `src/neocortex/db/adapter.py`

Add the implementation after `mark_episode_consolidated`.

Rules:

- Resolve the personal schema with `await self._router.route_store(agent_id)` or the existing personal-schema helper used by the router.
- Use `schema_scoped_connection(self._pool, personal_schema)`.
- Inside the scoped connection, query unqualified table names (`episode`, `node`, `edge_type`, `edge`) to follow existing scoped-connection conventions.
- Do not accept or use `target_schema`.
- Use a transaction and advisory lock keyed on `(personal_schema, agent_id, session_id)` to serialize concurrent linking for the same personal session.
- Do not assign `session_sequence` here; Stage 1 assigns it at storage time.
- Compare `_source_episode` as text to match the Stage 1 index: `properties->>'_source_episode' = $1`, passing `str(episode_id)`.
- When inserting JSONB properties, use `json.dumps(...)` and `$n::jsonb`.

Implementation outline:

```python
async def link_personal_episode_to_session_predecessor(self, agent_id: str, episode_id: int) -> None:
    if self._pool is None or self._router is None:
        return

    import hashlib

    schema_name = await self._router.route_store(agent_id)
    async with schema_scoped_connection(self._pool, schema_name) as conn:
        current = await conn.fetchrow(
            """
            SELECT id, session_id, session_sequence, created_at
            FROM episode
            WHERE id = $1 AND agent_id = $2
            """,
            episode_id,
            agent_id,
        )
        if current is None or current["session_id"] is None:
            return

        session_id = str(current["session_id"])
        lock_material = f"{schema_name}:{agent_id}:{session_id}"
        lock_key = int(hashlib.sha256(lock_material.encode()).hexdigest()[:16], 16) % (2**63 - 1)

        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_key)

            previous = await conn.fetchrow(
                """
                SELECT id
                FROM episode
                WHERE agent_id = $1
                  AND session_id = $2
                  AND id <> $3
                  AND (
                    (session_sequence IS NOT NULL AND $4::int IS NOT NULL AND session_sequence < $4)
                    OR ($4::int IS NULL AND (created_at, id) < ($5, $3))
                  )
                ORDER BY session_sequence DESC NULLS LAST, created_at DESC, id DESC
                LIMIT 1
                """,
                agent_id,
                session_id,
                episode_id,
                current["session_sequence"],
                current["created_at"],
            )
            if previous is None:
                return

            prev_id = int(previous["id"])
            prev_node_id = await conn.fetchval(
                """
                SELECT id FROM node
                WHERE properties->>'_source_episode' = $1
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                str(prev_id),
            )
            curr_node_id = await conn.fetchval(
                """
                SELECT id FROM node
                WHERE properties->>'_source_episode' = $1
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                str(episode_id),
            )
            if prev_node_id is None or curr_node_id is None:
                return

            follows_type_id = await conn.fetchval("SELECT id FROM edge_type WHERE name = 'FOLLOWS'")
            if follows_type_id is None:
                return

            await conn.execute(
                """
                INSERT INTO edge (source_id, target_id, type_id, weight, properties)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                ON CONFLICT (source_id, target_id, type_id) DO NOTHING
                """,
                curr_node_id,
                prev_node_id,
                follows_type_id,
                0.9,
                json.dumps({"episode_follows": episode_id, "episode_precedes": prev_id}),
            )
```

### 4. Stub in InMemoryRepository

File: `src/neocortex/db/mock.py`

Add a no-op implementation:

```python
async def link_personal_episode_to_session_predecessor(self, agent_id: str, episode_id: int) -> None:
    pass
```

This plan validates `FOLLOWS` creation with PostgreSQL integration tests, not the mock.

### 5. Call only from personal extraction paths

File: `src/neocortex/extraction/pipeline.py`

At both consolidation sites:

- Pass `read_schema` / `episode_schema` into `mark_episode_consolidated`.
- Call `link_personal_episode_to_session_predecessor(...)` only when both:
  - `target_schema is None`
  - the episode read schema is personal (`read_schema is None`)

Tool-driven path:

```python
await repo.mark_episode_consolidated(agent_id, episode_id, target_schema=read_schema)
if target_schema is None and read_schema is None:
    await repo.link_personal_episode_to_session_predecessor(agent_id, episode_id)
```

Fallback path:

```python
await repo.mark_episode_consolidated(agent_id, episode_id, target_schema=episode_schema)
if target_schema is None and episode_schema is None:
    await repo.link_personal_episode_to_session_predecessor(agent_id, episode_id)
```

Do not pass `target_schema` to the link method.

---

## Verification

- [ ] `uv run pytest tests/ -v` passes.
- [ ] PostgreSQL integration test: store and extract two personal episodes with the same `session_id`; verify one `FOLLOWS` edge in `ncx_<agent>__personal`.
- [ ] PostgreSQL integration test: store and extract two personal episodes with different `session_id` values; verify no `FOLLOWS` edge between them.
- [ ] PostgreSQL integration test: domain-routed extraction (`target_schema=<shared>`, `source_schema="__personal__"`) creates no `FOLLOWS` edge in the shared schema.
- [ ] PostgreSQL integration test: explicit `target_graph` extraction creates no `FOLLOWS` edge in that shared schema.
- [ ] Verify the `_source_episode` index with a matching text predicate:
  ```sql
  EXPLAIN SELECT id
  FROM ncx_anonymous__personal.node
  WHERE properties->>'_source_episode' = '42';
  ```
  Expected: index scan on `idx_node_source_episode` when the planner chooses the expression index.
- [ ] Query personal FOLLOWS edges:
  ```sql
  SELECT e.id,
         e.properties->>'episode_follows' AS follows,
         e.properties->>'episode_precedes' AS precedes
  FROM ncx_anonymous__personal.edge e
  JOIN ncx_anonymous__personal.edge_type et ON et.id = e.type_id
  WHERE et.name = 'FOLLOWS';
  ```

---

## Commit

`feat(extraction): link personal episodes with FOLLOWS edges`
