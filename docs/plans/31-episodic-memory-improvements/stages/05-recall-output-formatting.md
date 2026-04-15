# Stage 5: Recall Output Formatting & Provenance

**Goal**: Expose session/neighbor provenance in structured recall results and add an optional JSON-formatted context block for LLM consumption without replacing the existing `RecallResult` model.
**Dependencies**: Stage 3 (`RecallItem` already has `created_at`, `session_id`, `session_sequence`, and `neighbor_of`)

---

## Background

Current `tools/recall.py` returns a `RecallResult` Pydantic object. FastMCP exposes that as structured content; there is no plain-text formatter path to replace. This stage preserves the structured API and adds a deliberate formatted field instead of mutating episode `content`.

The role-bias correction from MemMachine applies to episode vector search only. The current tool embeds the query before calling `repo.recall`, and `GraphServiceAdapter` does not own an embedding service. Therefore, compute the biased episode embedding in `tools/recall.py` and pass it explicitly through the repository contract.

---

## Steps

### 1. Add formatted_context to RecallResult

File: `src/neocortex/schemas/memory.py`

`RecallItem` temporal fields were added in Stage 3. Add a new optional field to `RecallResult`:

```python
formatted_context: str | None = None
```

This is the caller-facing JSON context block. The existing `results`, `total`, and `query` fields remain unchanged.

### 2. Pass separate episode vector embedding through recall

Files:
- `src/neocortex/db/protocol.py`
- `src/neocortex/db/adapter.py`
- `src/neocortex/db/mock.py`
- `src/neocortex/tools/recall.py`

Extend `MemoryRepository.recall`:

```python
async def recall(
    self,
    query: str,
    agent_id: str,
    limit: int = 10,
    query_embedding: list[float] | None = None,
    expand_neighbors: bool = True,
    episode_query_embedding: list[float] | None = None,
) -> list[RecallItem]:
    ...
```

In `tools/recall.py`:

```python
query_embedding = None
episode_query_embedding = None
episode_query_text = query
if embeddings:
    query_embedding = await embeddings.embed(query)
    if not query.lower().startswith(("user:", "assistant:")):
        episode_query_text = f"user: {query}"
        episode_query_embedding = await embeddings.embed(episode_query_text)

results = await repo.recall(
    query=query,
    agent_id=agent_id,
    limit=limit,
    query_embedding=query_embedding,
    expand_neighbors=settings.recall_expand_neighbors,
    episode_query_embedding=episode_query_embedding,
)
```

In `GraphServiceAdapter._recall_in_schema`:

- Add `episode_query_embedding: list[float] | None = None` to `_recall_in_schema`.
- Thread the parameter from `GraphServiceAdapter.recall` through the `asyncio.gather(...)` call.
- Keep node search on the original `query_embedding`.
- Keep episode `ILIKE` text matching on the original `query`, not the `"user: "` text.
- Use `episode_query_embedding or query_embedding` for the episode vector similarity.
- Apply this only for personal schemas; for non-personal schemas, ignore `episode_query_embedding` and use the original `query_embedding`.

In `InMemoryRepository.recall`, accept `episode_query_embedding` and ignore it unless the mock gains vector behavior.

### 3. Build structured JSON context from RecallItem objects

File: `src/neocortex/tools/recall.py`

Add helper:

```python
def _format_recall_context(results: list[RecallItem]) -> str:
    """Return JSON blocks for recalled episodes, grouped by session."""
    import json
    from collections import defaultdict

    episodes = [r for r in results if r.source_kind == "episode"]
    clustered: dict[tuple[str, str | None], list[RecallItem]] = defaultdict(list)
    isolated: list[RecallItem] = []

    for ep in episodes:
        if ep.session_id:
            clustered[(ep.session_id, ep.graph_name)].append(ep)
        else:
            isolated.append(ep)

    parts: list[str] = []
    for (session_id, graph_name), cluster in clustered.items():
        cluster.sort(key=lambda e: (e.session_sequence is None, e.session_sequence or 0, e.created_at or "", e.item_id))
        parts.append(
            json.dumps(
                {
                    "session_id": session_id,
                    "graph_name": graph_name,
                    "episodes": [
                        {
                            "id": ep.item_id,
                            "created_at": ep.created_at.isoformat() if ep.created_at else None,
                            "session_sequence": ep.session_sequence,
                            "content": ep.content,
                            "is_context_neighbor": ep.neighbor_of is not None,
                            "neighbor_of": ep.neighbor_of,
                            "score": round(ep.score, 4),
                        }
                        for ep in cluster
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    for ep in isolated:
        parts.append(
            json.dumps(
                {
                    "id": ep.item_id,
                    "graph_name": ep.graph_name,
                    "created_at": ep.created_at.isoformat() if ep.created_at else None,
                    "content": ep.content,
                    "score": round(ep.score, 4),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    return "\n---\n".join(parts) if parts else "(no episodes recalled)"
```

After `final_results` is computed, call:

```python
formatted_context = _format_recall_context(final_results)
```

Return it:

```python
return RecallResult(
    results=final_results,
    total=len(final_results),
    query=query,
    formatted_context=formatted_context,
)
```

### 4. Add recall audit fields

File: `src/neocortex/tools/recall.py`

Extend the existing audit entry at the end of the tool:

```python
logger.bind(action_log=True).info(
    "recall_with_graph_traversal",
    agent_id=agent_id,
    query=query,
    total_results=len(all_results),
    node_results_with_context=sum(1 for r in all_results if r.graph_context is not None),
    session_ids_returned=list({r.session_id for r in final_results if r.session_id}),
    neighbor_episodes_included=sum(1 for r in final_results if r.neighbor_of is not None),
    episode_role_bias_applied=episode_query_embedding is not None,
)
```

### 5. Update MCP tests

Files:
- `tests/mcp/test_tools.py`
- Add focused tests near existing recall tests, or create `tests/test_recall_session_output.py`

Tests should assert structured model output, not plain text:

- `structured_content["results"]` contains episode items with `session_id`, `session_sequence`, `neighbor_of`, and `created_at` where applicable.
- `structured_content["formatted_context"]` contains JSON with `"session_id"`, `"created_at"`, and `"is_context_neighbor"`.
- Isolated episodes render as single JSON objects without an `"episodes"` array.
- Cluster episodes sort by `session_sequence`, falling back to `created_at`.
- Role-bias correction is applied only when embeddings are available and the query lacks `user:` / `assistant:` prefix. Use a fake embedding service that records the strings embedded.

---

## Verification

- [ ] `uv run pytest tests/ -v` passes.
- [ ] `NEOCORTEX_MOCK_DB=true uv run pytest tests/ -v` passes.
- [ ] Recall a query with a session cluster and confirm `formatted_context` contains `"episodes"` sorted chronologically.
- [ ] Confirm `is_context_neighbor: true` for neighbor episodes and `false` for direct hits.
- [ ] Confirm role bias embeds `"user: <query>"` for plain personal recall queries and does not double-prefix queries that already start with `user:` or `assistant:`.
- [ ] Confirm node search still uses the original query embedding.

---

## Commit

`feat(tools): expose structured session recall context`
