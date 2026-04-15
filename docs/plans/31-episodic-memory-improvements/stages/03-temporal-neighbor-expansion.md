# Stage 3: Temporal Neighbor Expansion in Recall

**Goal**: When an episode is matched during recall, optionally expand it by fetching the 1 immediately preceding and 2 immediately following episodes in the same session, mirroring MemMachine's nucleus+neighbors cluster strategy.
**Dependencies**: Stage 1 (session_id), Stage 2 (FOLLOWS edges — not strictly required, but session_id must exist)

---

## Background

MemMachine's key insight is that a single matched episode is often insufficient: the relevant information is spread across adjacent conversational turns. Their ablation shows multi-session accuracy climbs from 0.797 to 0.872 when retrieval depth is increased, and the nucleus+neighbors strategy provides the context window needed for the answer LLM to reason correctly.

Currently `_recall_in_schema` in `db/adapter.py` returns episodes as atomic units. This stage adds an optional second pass: for each matched episode, fetch its session neighbors and append them to the result set (deduplicating by episode ID). Neighbor episodes are tagged with a reduced score (they weren't directly matched) so they don't displace primary hits in the top-K ranking.

---

## Steps

### 1. Add `recall_expand_neighbors` setting to `MCPSettings`

File: `src/neocortex/mcp_settings.py`

Find the recall-related settings block (around lines 52–104). Add:

```python
recall_expand_neighbors: bool = True
recall_neighbor_window: int = 3  # 1 before + 2 after = 3 neighbors max
recall_neighbor_score_factor: float = 0.6  # score multiplier for neighbor episodes
```

### 2. Add `_fetch_episode_neighbors` helper to the adapter

File: `src/neocortex/db/adapter.py`

Add a new private async method to `GraphServiceAdapter` (near the `_recall_in_schema` method, around line 2004). `recall_neighbor_window` controls the total neighbor budget: floor(window/3) episodes before, window - floor(window/3) episodes after. With the default `window=3` this is 1 before + 2 after.

```python
async def _fetch_episode_neighbors(
    self,
    conn,
    schema: str,
    episode_id: int,
    session_id: str,
    created_at,  # datetime of the nucleus episode
    window: int = 3,
) -> list[dict]:
    """Return up to `window` neighboring episodes in the same session.

    Allocates floor(window/3) slots before and the remainder after the nucleus.
    With the default window=3: 1 preceding + 2 following.
    Episodes are returned as asyncpg Record objects (dict-like) so the caller
    can access columns by name.
    """
    before_limit = max(1, window // 3)
    after_limit = max(1, window - before_limit)
    # 1 before (default)
    before = await conn.fetch(
        f"""
        SELECT id, content, source_type, metadata,
               access_count, last_accessed_at, importance, consolidated,
               created_at, session_id, session_sequence
        FROM {schema}.episode
        WHERE session_id = $1
          AND id != $2
          AND created_at < $3
        ORDER BY created_at DESC
        LIMIT {before_limit}
        """,
        session_id, episode_id, created_at,
    )
    # 2 after (default)
    after = await conn.fetch(
        f"""
        SELECT id, content, source_type, metadata,
               access_count, last_accessed_at, importance, consolidated,
               created_at, session_id, session_sequence
        FROM {schema}.episode
        WHERE session_id = $1
          AND id != $2
          AND created_at > $3
        ORDER BY created_at ASC
        LIMIT {after_limit}
        """,
        session_id, episode_id, created_at,
    )
    return list(before) + list(after)
```

### 3. Add `session_id` and `session_sequence` to the episode SELECT queries

File: `src/neocortex/db/adapter.py`

In `_recall_in_schema` (line 2004), the episode `SELECT` query (around line 2051) currently does **not** include `session_id` or `session_sequence`. These columns are needed both for neighbor expansion (this stage) and for output formatting (Stage 5). Add them to the projection now so the `asyncpg.Record` rows returned from `conn.fetch` carry these fields.

Find the episode SELECT that starts with:
```python
episode_rows = await conn.fetch(
    """SELECT id, content, source_type,
              access_count, last_accessed_at, importance,
```
and extend the column list to include `session_id, session_sequence`.

Do the same in the text-only branch (the second `conn.fetch` for episodes that runs when `query_embedding is None`).

### 4. Wire neighbor expansion into `_recall_in_schema`

File: `src/neocortex/db/adapter.py`

**Important**: The expansion code operates on `asyncpg.Record` objects (the raw rows returned by `conn.fetch`), not on the final `RecallItem` Pydantic instances. Insert the expansion pass **after the episode scoring loop** (around line 2241) but **before** the point where scored episodes are assembled into `RecallItem` objects and the final top-K is cut.

Add `expand_neighbors: bool = True` to `_recall_in_schema`'s parameter signature.

Then, after the episode scoring loop, insert:

```python
if expand_neighbors and self._settings.recall_expand_neighbors:
    # scored_episode_rows is the list of (score, asyncpg.Record) tuples
    # built during the episode scoring loop above.
    neighbor_ids_seen = {row["id"] for _, row in scored_episode_rows}
    expansion: list[tuple[float, asyncpg.Record]] = []

    for score, ep_row in scored_episode_rows:
        if ep_row["session_id"] is None:
            continue
        neighbors = await self._fetch_episode_neighbors(
            conn=conn,
            schema=schema_name,
            episode_id=ep_row["id"],
            session_id=ep_row["session_id"],
            created_at=ep_row["created_at"],
            window=self._settings.recall_neighbor_window,
        )
        for nb in neighbors:
            if nb["id"] in neighbor_ids_seen:
                continue
            neighbor_ids_seen.add(nb["id"])
            neighbor_score = score * self._settings.recall_neighbor_score_factor
            expansion.append((neighbor_score, nb))

    scored_episode_rows.extend(expansion)
```

Note: the exact variable name for the scored episode rows (e.g. `scored_episode_rows`) must match whatever accumulator the episode scoring loop already uses in the method. Read the loop to confirm the variable name before inserting.

### 5. Expose `expand_neighbors` in the top-level `recall()` method (line 253)

File: `src/neocortex/db/adapter.py`

The `recall()` method at line 253 calls `_recall_in_schema` via `asyncio.gather`. Thread `expand_neighbors` from settings:

```python
expand_neighbors = self._settings.recall_expand_neighbors
results_per_schema = await asyncio.gather(
    *(
        self._recall_in_schema(
            schema_name, query, agent_id, limit,
            query_embedding=query_embedding,
            expand_neighbors=expand_neighbors,
        )
        for schema_name in schemas
    )
)
```

### 6. Sort final results chronologically within each session cluster

File: `src/neocortex/db/adapter.py`

After the top-K cut, apply a secondary sort: within groups of episodes from the same session (including neighbors), sort by `created_at`. This mirrors MemMachine's explicit "Sort Chronologically" step and ensures the answer LLM receives episodes in temporal order.

This sort operates on the final `RecallItem` list (after construction), using `RecallItem` attribute access. Add after the score-sorted top-K slice:

```python
def _chronological_stable_sort(items: list[RecallItem]) -> list[RecallItem]:
    """Preserve overall score ranking but sort session clusters chronologically."""
    result: list[RecallItem] = []
    seen: set[int] = set()
    for item in items:
        if item.item_id in seen:
            continue
        seen.add(item.item_id)
        sid = getattr(item, "session_id", None)
        if sid:
            cluster = [
                x for x in items
                if getattr(x, "session_id", None) == sid and x.item_id not in seen
            ]
            cluster.sort(key=lambda x: getattr(x, "created_at", None) or "")
            result.append(item)
            for c in cluster:
                seen.add(c.item_id)
                result.append(c)
        else:
            result.append(item)
    return result

top_results = _chronological_stable_sort(top_results)
```

### 7. Update `MemoryRepository` protocol if needed

File: `src/neocortex/db/protocol.py`

If the protocol defines a typed `recall` method signature, add `expand_neighbors: bool = True` as a keyword argument. Update `db/mock.py` to accept (and ignore) this parameter so tests don't break.

---

## Verification

- [ ] `uv run pytest tests/ -v` passes
- [ ] Unit test: ingest 4 episodes with the same `session_id` in order, recall with a query that matches episode #3. Assert that the result includes episodes #2 and #4 as neighbors (tagged with `_neighbor_of`).
- [ ] Disable neighbors via `recall_expand_neighbors: false` in settings and confirm neighbors are not returned.
- [ ] Confirm neighbor episodes appear AFTER their nucleus in the chronological sort: within the session cluster, episode #2 < #3 < #4.
- [ ] Confirm episodes from DIFFERENT sessions are NOT expanded into neighbors of each other.

---

## Commit

`feat(recall): expand recalled episodes with temporal session neighbors (MemMachine nucleus+context)`
