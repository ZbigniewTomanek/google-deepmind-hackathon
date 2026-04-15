# Stage 3: Temporal Neighbor Expansion in Recall

**Goal**: When a personal episode is matched during recall, optionally expand it with the 1 immediately preceding and 2 immediately following personal episodes in the same session, carrying explicit `neighbor_of` provenance.
**Dependencies**: Stage 1 (`session_id`, `session_sequence`); Stage 2 is not required for SQL neighbor expansion.

---

## Background

Current `_recall_in_schema` fetches `episode_rows` inside the DB connection, exits the connection scope, then scores rows into `result_dicts`. There is no `scored_episode_rows` accumulator. Neighbor expansion must therefore either happen inside the connection scope or prefetch neighbor rows before the connection closes.

This stage uses the latter approach:

1. Fetch primary episode rows as dicts.
2. While still inside the connection scope, fetch neighbor rows for each primary personal episode.
3. During scoring, build primary episode result dicts and append neighbor result dicts with `score = nucleus_score * recall_neighbor_score_factor`.
4. Convert dicts to `RecallItem` objects with session/neighbor metadata.

Neighbor expansion is personal-only: only schemas whose name ends in `__personal` are expanded.

---

## Steps

### 1. Add recall neighbor settings

File: `src/neocortex/mcp_settings.py`

In the recall settings block, add:

```python
recall_expand_neighbors: bool = True
recall_neighbor_window: int = 3  # default: 1 before + 2 after
recall_neighbor_score_factor: float = 0.6
```

### 2. Add RecallItem temporal fields

File: `src/neocortex/schemas/memory.py`

Add to `RecallItem`:

```python
created_at: datetime | None = None
session_id: str | None = None
session_sequence: int | None = None
neighbor_of: int | None = None
```

Import `datetime` if needed. These fields are used by recall sorting and Stage 5 output.

### 3. Update repository recall signatures

Files:
- `src/neocortex/db/protocol.py`
- `src/neocortex/db/adapter.py`
- `src/neocortex/db/mock.py`
- `src/neocortex/tools/recall.py`

Change recall signatures to accept:

```python
expand_neighbors: bool = True
```

In `GraphServiceAdapter.recall`, pass `expand_neighbors` through the `asyncio.gather(...)` call into `_recall_in_schema`. Add the same keyword to `_recall_in_schema`:

```python
async def _recall_in_schema(
    self,
    schema_name: str,
    query: str,
    agent_id: str,
    limit: int,
    query_embedding: list[float] | None = None,
    expand_neighbors: bool = True,
) -> list[RecallItem]:
    ...
```

In `tools/recall.py`, pass:

```python
results = await repo.recall(
    query=query,
    agent_id=agent_id,
    limit=limit,
    query_embedding=query_embedding,
    expand_neighbors=settings.recall_expand_neighbors,
)
```

In `InMemoryRepository.recall`, accept the parameter. Either ignore it with a comment or implement simple same-session expansion. PostgreSQL integration tests are required for the production behavior.

### 4. Add `_fetch_episode_neighbors`

File: `src/neocortex/db/adapter.py`

Add a private helper near `_recall_in_schema`. It receives an open scoped connection and uses unqualified table names.

```python
async def _fetch_episode_neighbors(
    self,
    conn: asyncpg.Connection,
    episode_id: int,
    session_id: str,
    created_at,
    session_sequence: int | None,
    window: int = 3,
) -> list[dict]:
    before_limit = max(1, window // 3)
    after_limit = max(1, window - before_limit)

    before = await conn.fetch(
        f"""
        SELECT id, content, source_type,
               access_count, last_accessed_at, importance, consolidated,
               created_at, session_id, session_sequence,
               NULL::double precision AS vector_sim,
               NULL::float[] AS embedding_vec
        FROM episode
        WHERE session_id = $1
          AND id <> $2
          AND (
            (session_sequence IS NOT NULL AND $4::int IS NOT NULL AND session_sequence < $4)
            OR ($4::int IS NULL AND (created_at, id) < ($3, $2))
          )
        ORDER BY session_sequence DESC NULLS LAST, created_at DESC, id DESC
        LIMIT {before_limit}
        """,
        session_id,
        episode_id,
        created_at,
        session_sequence,
    )
    after = await conn.fetch(
        f"""
        SELECT id, content, source_type,
               access_count, last_accessed_at, importance, consolidated,
               created_at, session_id, session_sequence,
               NULL::double precision AS vector_sim,
               NULL::float[] AS embedding_vec
        FROM episode
        WHERE session_id = $1
          AND id <> $2
          AND (
            (session_sequence IS NOT NULL AND $4::int IS NOT NULL AND session_sequence > $4)
            OR ($4::int IS NULL AND (created_at, id) > ($3, $2))
          )
        ORDER BY session_sequence ASC NULLS LAST, created_at ASC, id ASC
        LIMIT {after_limit}
        """,
        session_id,
        episode_id,
        created_at,
        session_sequence,
    )
    rows: list[dict] = []
    rows.extend(dict(r) | {"neighbor_position": "before"} for r in before)
    rows.extend(dict(r) | {"neighbor_position": "after"} for r in after)
    return rows
```

The `LIMIT` values are integers computed by trusted code, not user input. Keep them bounded by the setting validation/defaults.

### 5. Fetch session columns and prefetch neighbors inside `_recall_in_schema`

File: `src/neocortex/db/adapter.py`

Add `session_id`, `session_sequence`, and `created_at` to both episode SELECT projections. Current SELECTs start around `episode_rows = await conn.fetch(...)`.

After `episode_rows` is fetched, while still inside `async with graph_scoped_connection(...)`, convert rows to dicts and prefetch neighbors:

```python
episode_row_dicts = [dict(r) for r in episode_rows]
neighbors_by_nucleus: dict[int, list[dict]] = {}

if expand_neighbors and self._settings.recall_expand_neighbors and schema_name.endswith("__personal"):
    seen_episode_ids = {int(r["id"]) for r in episode_row_dicts}
    for ep in episode_row_dicts:
        if ep.get("session_id") is None:
            continue
        neighbors = await self._fetch_episode_neighbors(
            conn=conn,
            episode_id=int(ep["id"]),
            session_id=str(ep["session_id"]),
            created_at=ep["created_at"],
            session_sequence=ep.get("session_sequence"),
            window=self._settings.recall_neighbor_window,
        )
        unique_neighbors: list[dict] = []
        for nb in neighbors:
            nb_id = int(nb["id"])
            if nb_id in seen_episode_ids:
                continue
            seen_episode_ids.add(nb_id)
            nb["neighbor_of"] = int(ep["id"])
            unique_neighbors.append(nb)
        if unique_neighbors:
            neighbors_by_nucleus[int(ep["id"])] = unique_neighbors
```

Use `episode_row_dicts` for the later episode scoring loop instead of the raw `episode_rows`.

### 6. Score primary episodes and append neighbor result dicts

File: `src/neocortex/db/adapter.py`

Refactor the current episode loop at [adapter.py](/Users/zbigniewtomanek/work/neocortex/src/neocortex/db/adapter.py):2191 into a small local helper that turns a row dict into a result dict:

```python
def _episode_result_dict(row: dict, score: float, activation: float | None, importance: float) -> dict:
    return {
        "score": score,
        "embedding": list(row["embedding_vec"]) if row.get("embedding_vec") is not None else None,
        "item_id": int(row["id"]),
        "name": f"Episode #{int(row['id'])}",
        "content": str(row["content"]),
        "item_type": "Episode",
        "activation_score": activation,
        "importance": importance,
        "source": str(row["source_type"]) if row.get("source_type") is not None else None,
        "source_kind": "episode",
        "graph_name": schema_name,
        "created_at": row.get("created_at"),
        "session_id": row.get("session_id"),
        "session_sequence": row.get("session_sequence"),
        "neighbor_of": row.get("neighbor_of"),
    }
```

For each primary episode row:

- Compute its existing hybrid score exactly as today.
- Append the primary result dict with `neighbor_of=None`.
- For each row in `neighbors_by_nucleus.get(primary_id, [])`, append a neighbor result dict with:
  - `score = primary_score * self._settings.recall_neighbor_score_factor`
  - `neighbor_of = primary_id`
  - activation/importance can be computed from the neighbor row using the same formulas, but do not recompute text/vector relevance for neighbors.

Do not mutate `asyncpg.Record` objects.

### 7. Convert temporal fields into RecallItem

File: `src/neocortex/db/adapter.py`

When converting `result_dicts` to `RecallItem`, add:

```python
created_at=d.get("created_at"),
session_id=d.get("session_id"),
session_sequence=d.get("session_sequence"),
neighbor_of=d.get("neighbor_of"),
```

Node result dicts may leave these fields absent/`None`.

### 8. Sort final merged results chronologically within session clusters

File: `src/neocortex/db/adapter.py`

After `_deduplicate_recall_items(merged_results)[:limit]` in top-level `recall()`, apply a stable cluster sort. The sort must reorder the entire cluster, including the nucleus, not append the current item before earlier neighbors.

```python
def _sort_session_clusters_chronologically(items: list[RecallItem]) -> list[RecallItem]:
    result: list[RecallItem] = []
    consumed: set[tuple[str, int, str | None]] = set()

    def key_for(item: RecallItem) -> tuple[str, int, str | None]:
        return (item.source_kind, item.item_id, item.graph_name)

    for item in items:
        key = key_for(item)
        if key in consumed:
            continue
        if item.source_kind != "episode" or not item.session_id:
            consumed.add(key)
            result.append(item)
            continue

        cluster = [
            x for x in items
            if x.source_kind == "episode"
            and x.graph_name == item.graph_name
            and x.session_id == item.session_id
            and key_for(x) not in consumed
        ]
        cluster.sort(key=lambda x: (x.session_sequence is None, x.session_sequence or 0, x.created_at or "", x.item_id))
        for c in cluster:
            consumed.add(key_for(c))
            result.append(c)

    return result
```

Use:

```python
deduped = _deduplicate_recall_items(merged_results)
top_results = deduped[:limit]
return _sort_session_clusters_chronologically(top_results)
```

---

## Verification

- [ ] `uv run pytest tests/ -v` passes.
- [ ] PostgreSQL integration test: store 4 personal episodes with the same `session_id`; recall a query matching episode #3; assert episodes #2 and #4 are included with `neighbor_of == id_of_episode_3`.
- [ ] Disable `recall_expand_neighbors` and confirm only direct matches are returned.
- [ ] Confirm chronological cluster order is #2, #3, #4 even when #3 has the highest score.
- [ ] Confirm episodes from different sessions are not returned as neighbors.
- [ ] Confirm shared/domain schema episode matches do not expand neighbors.

---

## Commit

`feat(recall): expand personal episode recall with temporal neighbors`
