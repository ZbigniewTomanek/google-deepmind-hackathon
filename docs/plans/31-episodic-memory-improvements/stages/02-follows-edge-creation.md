# Stage 2: FOLLOWS Edge Creation in Extraction

**Goal**: After each episode is extracted and consolidated, look up the immediately preceding episode in the same session and create a `FOLLOWS` edge between them in the personal knowledge graph, giving the graph an explicit temporal spine.
**Dependencies**: Stage 1 (session_id column must exist)

---

## Background

The `FOLLOWS` edge type already exists in the seed ontology (`migrations/graph/003_seed_ontology.sql`, line 16). It has always been available but has never been used. MemMachine's contextualized retrieval depends on traversing temporal neighbors; creating these edges enables future graph traversal to cheaply expand episode context.

The extraction pipeline marks an episode as `consolidated = true` after the librarian agent finishes. This is the right hook for creating FOLLOWS edges: at that point the episode is committed to the graph and we can safely link it to its predecessor.

**Architecture note**: `pipeline.py` works exclusively through the `MemoryRepository` protocol — it never holds a raw `asyncpg.Pool` reference. FOLLOWS edge creation must be implemented as a new protocol method, with the DB logic in `GraphServiceAdapter` (which has pool access), exactly the same pattern as `mark_episode_consolidated`.

---

## Steps

### 1. Add `link_episode_to_session_predecessor` to `MemoryRepository` protocol

File: `src/neocortex/db/protocol.py`

Add the following method signature after `mark_episode_consolidated` (line 274):

```python
async def link_episode_to_session_predecessor(
    self,
    agent_id: str,
    episode_id: int,
    target_schema: str | None = None,
) -> None:
    """Find the preceding episode in the same session and create a FOLLOWS edge.

    Looks up the session_id of `episode_id`, queries for the most recent prior
    episode in the same session, creates a FOLLOWS edge between them in the
    graph, and updates session_sequence for the current episode.

    No-op when: episode has no session_id, no predecessor exists, or no nodes
    were extracted from one of the episodes (so there is nothing to link).

    Args:
        agent_id: The agent who owns the episode.
        episode_id: ID of the newly-consolidated episode (the later one).
        target_schema: The graph schema that holds this episode. When None,
            the agent's personal schema is used (same convention as
            store_episode_to / mark_episode_consolidated).
    """
    ...
```

### 2. Implement in `GraphServiceAdapter`

File: `src/neocortex/db/adapter.py`

Add the implementation after `mark_episode_consolidated`. The method must:

1. Resolve the schema (use `target_schema` when set; fall back to the agent's personal schema via `self._router`).
2. Fetch the current episode's `session_id` and `created_at`.
3. Use a PostgreSQL **advisory lock** keyed on the session to serialize concurrent sequence assignments.
4. Inside the transaction, find the predecessor, create the FOLLOWS edge, and update `session_sequence`.

```python
async def link_episode_to_session_predecessor(
    self,
    agent_id: str,
    episode_id: int,
    target_schema: str | None = None,
) -> None:
    if self._pool is None or self._router is None:
        return  # mock / pool-less path; no-op

    schema = target_schema or await self._router.get_personal_schema(agent_id)

    async with schema_scoped_connection(self._pool, schema) as conn:
        row = await conn.fetchrow(
            f"SELECT session_id, created_at FROM {schema}.episode"
            " WHERE id = $1 AND agent_id = $2",
            episode_id,
            agent_id,
        )
        if not row or not row["session_id"]:
            return

        session_id: str = row["session_id"]
        created_at = row["created_at"]

        # Advisory lock: serialize session_sequence updates for the same session
        # so two concurrent extractions don't assign duplicate sequence numbers.
        import hashlib
        lock_key = (
            int(hashlib.sha256(session_id.encode()).hexdigest()[:8], 16) % (2**31 - 1)
        )

        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_key)

            # Find the predecessor episode in the same session
            prev_id: int | None = await conn.fetchval(
                f"""
                SELECT id FROM {schema}.episode
                WHERE agent_id = $1
                  AND session_id = $2
                  AND id != $3
                  AND created_at <= $4
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                agent_id,
                session_id,
                episode_id,
                created_at,
            )

            # Update session_sequence (safe under advisory lock)
            if prev_id is None:
                await conn.execute(
                    f"UPDATE {schema}.episode SET session_sequence = 1 WHERE id = $1",
                    episode_id,
                )
                return  # First episode in this session — no edge to create

            await conn.execute(
                f"""
                UPDATE {schema}.episode
                SET session_sequence = (
                    SELECT COALESCE(MAX(session_sequence), 0) + 1
                    FROM {schema}.episode
                    WHERE session_id = $1 AND id != $2
                )
                WHERE id = $2
                """,
                session_id,
                episode_id,
            )

            # Resolve nodes to link: use the first-created node from each episode
            # (via the _source_episode property index added in the migration)
            prev_node_id: int | None = await conn.fetchval(
                f"""
                SELECT id FROM {schema}.node
                WHERE (properties->>'_source_episode')::int = $1
                ORDER BY created_at ASC
                LIMIT 1
                """,
                prev_id,
            )
            curr_node_id: int | None = await conn.fetchval(
                f"""
                SELECT id FROM {schema}.node
                WHERE (properties->>'_source_episode')::int = $1
                ORDER BY created_at ASC
                LIMIT 1
                """,
                episode_id,
            )
            if prev_node_id is None or curr_node_id is None:
                return  # One or both episodes produced no nodes; skip edge

            follows_type_id: int | None = await conn.fetchval(
                f"SELECT id FROM {schema}.edge_type WHERE name = 'FOLLOWS'"
            )
            if follows_type_id is None:
                return

            await conn.execute(
                f"""
                INSERT INTO {schema}.edge
                    (source_id, target_id, type_id, weight, properties)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (source_id, target_id, type_id) DO NOTHING
                """,
                curr_node_id,
                prev_node_id,
                follows_type_id,
                0.9,
                {"_episode_follows": episode_id, "_episode_precedes": prev_id},
            )
```

### 3. Stub in `InMemoryRepository`

File: `src/neocortex/db/mock.py`

Add a no-op stub after the `mark_episode_consolidated` stub:

```python
async def link_episode_to_session_predecessor(
    self,
    agent_id: str,
    episode_id: int,
    target_schema: str | None = None,
) -> None:
    pass  # No graph traversal in mock; session ordering not enforced
```

### 4. Call from extraction pipeline at both consolidation points

File: `src/neocortex/extraction/pipeline.py`

There are two places where `mark_episode_consolidated` is called (lines 288 and 464). Add the new call **immediately after each one**, passing the same `target_schema` that is in scope:

**Line 288 (tool-driven librarian path)**:
```python
# Mark episode as consolidated
await repo.mark_episode_consolidated(agent_id, episode_id)
# Link to preceding episode in the same session (creates FOLLOWS edge)
await repo.link_episode_to_session_predecessor(agent_id, episode_id, target_schema=target_schema)
```

**Line 464 (fallback / non-tool path)**:
```python
# Mark episode as consolidated (extraction completed)
await repo.mark_episode_consolidated(agent_id, episode_id)
# Link to preceding episode in the same session (creates FOLLOWS edge)
await repo.link_episode_to_session_predecessor(agent_id, episode_id, target_schema=target_schema)
```

### 5. Add `_source_episode` JSONB index to graph schema migration

File: `migrations/graph/007_episode_session.sql` (created in Stage 1)

Append to this migration:

```sql
-- Index _source_episode property for efficient node→episode lookups
-- (used by FOLLOWS edge creation to find representative nodes per episode)
CREATE INDEX IF NOT EXISTS idx_node_source_episode
    ON {schema}.node ((properties->>'_source_episode'));
```

---

## Verification

- [ ] `uv run pytest tests/ -v` passes with no failures
- [ ] Ingest two episodes with the same `session_id`, wait for both to extract, then query:
  ```sql
  SELECT e.id, et.name AS edge_type,
         e.properties->>'_episode_follows' AS follows,
         e.properties->>'_episode_precedes' AS precedes
  FROM ncx_anonymous__personal.edge e
  JOIN ncx_anonymous__personal.edge_type et ON et.id = e.type_id
  WHERE et.name = 'FOLLOWS'
    AND e.properties ? '_episode_follows';
  ```
  Expected: at least one row linking the two episodes.
- [ ] Ingest two episodes with **different** `session_id` values and confirm NO FOLLOWS edge is created between them.
- [ ] Ingest a single episode (no predecessor) and confirm no error is raised — just a silent skip.
- [ ] Confirm `session_sequence` is set: `SELECT id, session_id, session_sequence FROM ncx_anonymous__personal.episode WHERE session_id IS NOT NULL ORDER BY session_id, session_sequence` should show incrementing integers (starting at 1) within each session.
- [ ] Confirm `EXPLAIN SELECT id FROM ncx_anonymous__personal.node WHERE (properties->>'_source_episode')::int = 42` shows `Index Scan` on `idx_node_source_episode`.

---

## Commit

`feat(extraction): create FOLLOWS edges between consecutive episodes in the same session`
