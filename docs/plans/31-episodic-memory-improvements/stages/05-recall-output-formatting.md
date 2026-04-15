# Stage 5: Recall Output Formatting & Provenance

**Goal**: Include `session_id`, `session_sequence`, and `_neighbor_of` in recalled episode results, and format multi-episode session clusters as structured JSON blocks so the answer LLM can read conversational flow without ambiguity.
**Dependencies**: Stages 1, 3 (session_id + neighbor expansion)

---

## Background

MemMachine's ablation shows +2.0% from structured context formatting (JSON-str with explicit field names vs. wall-of-text concatenation). The paper also shows +1.4% from role bias correction — prepending "user:" to search queries corrects for assistant messages dominating embedding space.

Currently NeoCortex's recall tool returns episode content as raw text strings. When the MCP tool returns multiple episodes to the agent, there's no structural cue about which episodes belong to the same session, what order they occurred in, or which ones are direct hits vs. context neighbors. This stage:

1. Adds temporal metadata to episode recall results
2. Formats session clusters as structured JSON in the returned text
3. Applies query-role bias correction to the vector embedding search

---

## Steps

### 1. Add session metadata to the `RecallItem` model

File: `src/neocortex/schemas/memory.py`

The recall tool's output model is `RecallItem` (lines 24–36), **not** `EpisodeResult`. `src/neocortex/models.py` contains the DB-layer `Episode` model which is not the recall output. Add the following optional fields to `RecallItem`:

```python
session_id: str | None = None
session_sequence: int | None = None
neighbor_of: int | None = None  # item_id of the nucleus episode if this is an expansion
```

### 2. Propagate session fields when constructing `RecallItem` from episode rows

File: `src/neocortex/db/adapter.py`

The `session_id` and `session_sequence` columns are already added to the episode SELECT in Stage 3 (Step 3). Here, propagate them when constructing `RecallItem` instances from scored episode rows. Also carry `_neighbor_of` (the nucleus episode's id) through from the expansion step (Stage 3) into the `neighbor_of` field.

Find the code that builds `RecallItem(..., source_kind="episode", ...)` and add:

```python
session_id=ep_row.get("session_id"),
session_sequence=ep_row.get("session_sequence"),
neighbor_of=ep_row.get("_neighbor_of"),
```

### 3. Format session clusters as structured JSON in the recall tool response

File: `src/neocortex/tools/recall.py`

Currently the tool formats results as plain text. Add a formatter that groups episodes by `session_id` and renders session clusters as structured objects. This affects only the text returned to the MCP caller — not the internal scoring or storage.

The formatter receives `RecallItem` Pydantic objects (not raw dicts), so use attribute access, not `ep.get(...)`. Implement a helper `_format_episode_results(episodes: list[RecallItem]) -> str`:

```python
def _format_episode_results(episodes: list[RecallItem]) -> str:
    """Format recalled episodes for LLM consumption.

    Episodes within the same session are grouped into clusters and rendered
    as structured JSON objects. Isolated episodes (no session_id) are rendered
    as simple JSON objects. Clusters are sorted chronologically within the session.
    """
    import json
    from collections import defaultdict

    clustered: dict[str, list[RecallItem]] = defaultdict(list)
    isolated: list[RecallItem] = []

    for ep in episodes:
        if ep.session_id:
            clustered[ep.session_id].append(ep)
        else:
            isolated.append(ep)

    parts = []

    for sid, cluster in clustered.items():
        cluster.sort(key=lambda e: (e.session_sequence or 0))
        cluster_obj = {
            "session_id": sid,
            "episodes": [
                {
                    "id": ep.item_id,
                    "content": ep.content,
                    "is_context_neighbor": ep.neighbor_of is not None,
                    "score": round(ep.score, 4),
                }
                for ep in cluster
            ],
        }
        parts.append(json.dumps(cluster_obj, ensure_ascii=False, indent=2))

    for ep in isolated:
        parts.append(
            json.dumps(
                {
                    "id": ep.item_id,
                    "content": ep.content,
                    "score": round(ep.score, 4),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    return "\n---\n".join(parts) if parts else "(no episodes recalled)"
```

Call this formatter for the episode section of the recall tool response, passing only the `RecallItem` entries where `r.source_kind == "episode"`.

### 4. Apply query-role bias correction to the **episode** vector search only

File: `src/neocortex/db/adapter.py`

MemMachine observed +1.4% by prepending "user:" to search queries for conversational memory. The bias is only meaningful for personal episode retrieval; applying it to shared domain schemas (scientific facts, entity graphs) is inappropriate.

In `_recall_in_schema`, apply the bias **only for the episode `conn.fetch` call**, not for the node query. Scope it further to personal schemas (schema name ends in `__personal`):

```python
# Role bias correction for episode search: user queries about personal memory
# typically reference user-turn content. Only applied to personal schemas.
# Ref: MemMachine ablation (+1.4%).
if schema_name.endswith("__personal") and not query.lower().startswith(("user:", "assistant:")):
    episode_query_text = f"user: {query}"
    if query_embedding is not None:
        episode_query_embedding = await self._embedding_service.embed(episode_query_text)
    else:
        episode_query_embedding = None
else:
    episode_query_text = query
    episode_query_embedding = query_embedding
```

Use `episode_query_embedding` and `episode_query_text` only for the episode `conn.fetch` calls. The node search continues using the original `query` / `query_embedding`.

### 5. Add `session_id` + neighbor info to recall audit log

File: `src/neocortex/tools/recall.py`

The recall tool's `logger.bind(action_log=True).info(...)` audit entry is at **lines 210–216** (not 176–183; those lines are the access recording block). Add `session_ids_returned` and `neighbor_episodes_included` to the audit entry so operators can observe how often neighbor expansion is triggered:

```python
logger.bind(action_log=True).info(
    "recall_with_graph_traversal",
    agent_id=agent_id,
    query=query,
    total_results=len(all_results),
    node_results_with_context=sum(1 for r in all_results if r.graph_context is not None),
    session_ids_returned=list({r.session_id for r in final_results if r.session_id}),
    neighbor_episodes_included=sum(1 for r in final_results if r.neighbor_of is not None),
)
```

---

## Verification

- [ ] `uv run pytest tests/ -v` passes
- [ ] Recall a query and assert that the returned text contains `"session_id"` and `"created_at"` keys when episodes have sessions.
- [ ] Recall a query that matches a session cluster and assert the returned JSON has `"episodes"` array sorted by `session_sequence`.
- [ ] Recall a query that matches an isolated episode (no `session_id`) and assert it renders as a simple JSON object without `"episodes"` nesting.
- [ ] Confirm `is_context_neighbor: true` appears for neighbor episodes and `false` for directly-matched ones.
- [ ] Confirm role bias correction: log or debug-print the biased query for a plain search and confirm "user: " prefix is prepended. Confirm it is NOT prepended if query already starts with "user:" or "assistant:".
- [ ] Run full `uv run pytest tests/ -v` with mock DB mode:
  ```bash
  NEOCORTEX_MOCK_DB=true uv run pytest tests/ -v
  ```

---

## Commit

`feat(tools): structured session-cluster formatting and role bias correction for recalled episodes`
