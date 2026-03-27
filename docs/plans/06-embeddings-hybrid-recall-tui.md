# Plan 06: Embedding Service, Hybrid Recall, and Developer TUI

## Overview

Three tightly coupled deliverables that turn NeoCortex from "episode storage with text search" into
"knowledge graph with semantic search" — the actual hackathon pitch:

1. **Embedding Service** — thin async wrapper around `google-genai` SDK's `embed_content` using
   Gemini Embedding 2 (768-dim MRL truncation, normalized). Wired into `remember` and ingestion
   so every episode gets an embedding on write.
2. **Hybrid Recall** — extend `_recall_in_schema` and `_recall_via_graph` to combine three signals:
   pgvector cosine similarity, tsvector `ts_rank`, and recency decay into a single weighted score.
   Skeleton designed for easy weight tuning later.
3. **Developer TUI** — Textual-based terminal UI for interacting with the MCP server during
   development: remember, recall, discover, view episodes, inspect ontology. Replaces ad-hoc
   `curl` / script usage.

### Key design decisions

- **768-dim embeddings** — the schema already uses `vector(768)`. Gemini Embedding 2 supports MRL
  truncation to 768 which cuts storage 75% vs default 3072 with minimal quality loss.
- **Normalize after truncation** — per Gemini best practices, we normalize vectors after MRL
  truncation to keep cosine similarity accurate.
- **`google-genai` SDK** — transitive dependency via `pydantic-ai-slim[google]>=1.72.0`.
  Import as `from google import genai` and `from google.genai import types`.
  Async support via `client.aio.models.embed_content()`.
- **HNSW index** — the graph schema template already creates HNSW indexes on both `node.embedding`
  and `episode.embedding` (`vector_cosine_ops`, m=16, ef_construction=64). No migration needed.
- **Mock fallback** — when `NEOCORTEX_MOCK_DB=true`, `EmbeddingService` is not instantiated (set to
  `None` in `ServiceContext`). When `GOOGLE_API_KEY` is unset, the service is still instantiated
  but `embed()` returns `None` internally, and recall falls back to text-only. No breaking changes.
- **Textual TUI** — `textual` is the standard Python TUI framework (built on `rich`, already
  installed). We add it as a dependency. The TUI connects to the running MCP server using
  `fastmcp.Client` with streamable-HTTP transport (the same protocol MCP clients use).

### References

- pgvector cosine distance operator: `<=>` (returns distance; similarity = `1 - distance`)
- Gemini Embedding 2 API: `client.aio.models.embed_content(model="gemini-embedding-exp-03-07", contents=..., config=EmbedContentConfig(outputDimensionality=768))`
- pgvector article: dev.to/googleai/a-guide-to-embeddings-and-pgvector-df0
- Existing code: `GraphService.search_by_vector()` and `search_episodes_by_vector()` already
  implement the SQL correctly — they just need to be called from the recall path.

---

## Stage 1: Embedding Service

**Goal**: Create `src/neocortex/embedding_service.py` — async service that generates 768-dim
normalized embeddings via Gemini, with graceful fallback when API key is unavailable.

### Steps

1. **Create `src/neocortex/embedding_service.py`**
   - Class `EmbeddingService` with:
     - `__init__(self, model: str | None = None, dimensions: int = 768)` — reads model from
       `settings.embedding_model` (see below), defaults to `"gemini-embedding-exp-03-07"`
     - Lazy-init `google.genai.Client` from `GOOGLE_API_KEY` env var. If the env var is unset,
       `self._client` stays `None` and all `embed*` calls return `None` gracefully.
     - `async def embed(self, text: str) -> list[float] | None` — returns normalized 768-dim
       vector or `None` if client unavailable / API errors
     - `async def embed_batch(self, texts: list[str]) -> list[list[float] | None]` — batch embed
       (Gemini supports list of contents in a single call)
     - Private `_normalize(vector: list[float]) -> list[float]` — L2 normalization
   - Imports: `from google import genai` and `from google.genai import types`
   - The `embed_content` call:
     ```python
     from google import genai
     from google.genai import types

     response = await self._client.aio.models.embed_content(
         model=self._model,
         contents=text,
         config=types.EmbedContentConfig(outputDimensionality=self._dimensions),
     )
     values = response.embeddings[0].values
     return self._normalize(values)
     ```
   - Wrap API call in `try/except` to gracefully return `None` on failure (log warning via loguru)

2. **Add embedding settings to `mcp_settings.py`**
   ```python
   # Embedding model (experimental names may rotate; fallback: "text-embedding-004")
   embedding_model: str = "gemini-embedding-exp-03-07"
   ```

3. **Wire into `ServiceContext`**
   - In `services.py`: add `embeddings: EmbeddingService | None` to `ServiceContext` TypedDict
   - In `create_services()`: **always** instantiate `EmbeddingService(model=settings.embedding_model)`
     when `mock_db=False`, set to `None` when `mock_db=True`. The service itself handles missing
     `GOOGLE_API_KEY` by returning `None` from `embed()` — no double-gating.
   - Tools access via `ctx.lifespan_context["embeddings"]`

4. **Wire into `remember` tool**
   - In `tools/remember.py`: after `store_episode()`, if embeddings service is available,
     generate embedding and update the episode:
     ```python
     embeddings = ctx.lifespan_context.get("embeddings")
     if embeddings:
         vector = await embeddings.embed(text)
         if vector:
             await repo.update_episode_embedding(episode_id, vector, agent_id)
     ```

5. **Add `update_episode_embedding` to `MemoryRepository` protocol and both implementations**
   - Protocol signature in `db/protocol.py`:
     ```python
     async def update_episode_embedding(
         self, episode_id: int, embedding: list[float], agent_id: str
     ) -> None:
         """Attach a vector embedding to an existing episode."""
     ```
   - `InMemoryRepository` (`db/mock.py`): find the episode in `_episodes` by id and set its
     `embedding` field (or store as a dict attribute — the mock doesn't persist to SQL)
   - `GraphServiceAdapter` (`db/adapter.py`):
     ```python
     async def update_episode_embedding(
         self, episode_id: int, embedding: list[float], agent_id: str
     ) -> None:
         if self._pool is None or self._router is None:
             # Public schema fallback — use GraphService directly
             emb_str = str(embedding)
             await self._pg.execute(
                 "UPDATE episode SET embedding = $1::vector WHERE id = $2",
                 emb_str, episode_id,
             )
             return
         # Route to the agent's personal schema (same schema where store_episode writes)
         schema_name = await self._router.route_store(agent_id)
         async with schema_scoped_connection(self._pool, schema_name) as conn:
             emb_str = str(embedding)
             await conn.execute(
                 "UPDATE episode SET embedding = $1::vector WHERE id = $2",
                 emb_str, episode_id,
             )
     ```
     Note: `route_store()` returns the same schema used by `store_episode()`, so the episode
     ID is guaranteed to exist there. Uses `schema_scoped_connection` (not `graph_scoped_connection`)
     because per-agent schemas don't use RLS.

6. **Wire into ingestion `StubProcessor`**
   - In `ingestion/stub_processor.py`: accept optional `EmbeddingService`, generate embedding
     before storing episode

7. **Unit tests**
   - `tests/test_embedding_service.py`:
     - Test `_normalize` produces unit vectors
     - Test `embed` returns `None` when no API key
     - Test with mocked `google.genai.Client` returning known values
     - Test `embed_batch` for multiple inputs

### Verification

```bash
uv run pytest tests/test_embedding_service.py -v
# With real API key:
GOOGLE_API_KEY=... python3 -c "
import asyncio
from neocortex.embedding_service import EmbeddingService
async def main():
    svc = EmbeddingService()
    v = await svc.embed('hello world')
    print(f'dims={len(v)}, norm={sum(x*x for x in v):.4f}')
asyncio.run(main())
"
# Expected: dims=768, norm=1.0000
```

### Commit

```
feat(embeddings): add Gemini embedding service with 768-dim MRL support
```

---

## Stage 2: Hybrid Recall Scoring

**Goal**: Extend recall to combine vector similarity + text rank + recency into a single score.
The weights are configurable constants designed for easy tuning.

### Steps

1. **Add scoring constants to `mcp_settings.py`**
   ```python
   # Hybrid recall weights (must sum to 1.0)
   recall_weight_vector: float = 0.4
   recall_weight_text: float = 0.35
   recall_weight_recency: float = 0.25
   recall_recency_half_life_hours: float = 168.0  # 7 days
   # Vector distance threshold: cosine distance below this counts as a match.
   # 0.5 distance = 0.5 similarity. Tune up for stricter matching, down for broader.
   recall_vector_distance_threshold: float = 0.5
   ```

2. **Create `src/neocortex/scoring.py`**
   - `compute_recency_score(created_at: datetime, half_life_hours: float) -> float`
     - Exponential decay: `score = 2 ** (-hours_ago / half_life_hours)`
     - Returns value in [0, 1] range
   - `compute_hybrid_score(vector_sim: float | None, text_rank: float | None, recency: float, weights: HybridWeights) -> float`
     - `HybridWeights` is a simple dataclass/NamedTuple with `vector`, `text`, `recency` floats
     - When `vector_sim` is `None`, redistribute its weight proportionally to the other signals
     - When `text_rank` is `None`, same redistribution
     - This graceful degradation means the system works identically to today when no embeddings
       exist, but improves as embeddings are added

3. **Extend `_recall_in_schema` in `adapter.py`**

   **Important context**: this method uses `graph_scoped_connection(pool, schema, agent_id)`,
   which sets both `search_path` AND `SET LOCAL ROLE` for RLS enforcement on shared schemas.
   All SQL modifications must work correctly under RLS.

   - Accept `query_embedding: list[float] | None` and `settings: MCPSettings` parameters
   - **Branch on whether `query_embedding` is available**:

   **When `query_embedding` is `None`** — keep the existing text-only queries unchanged (current
   behavior, no regression).

   **When `query_embedding` is provided** — replace the two separate queries with combined ones:

   **Node query** (nodes have `tsv` column):
     ```sql
     SELECT id, name, content, source, type_id,
            ts_rank(tsv, plainto_tsquery('english', $1)) AS text_rank,
            CASE WHEN embedding IS NOT NULL
                 THEN 1 - (embedding <=> $2::vector)
                 ELSE NULL
            END AS vector_sim,
            created_at
     FROM node
     WHERE tsv @@ plainto_tsquery('english', $1)
        OR (embedding IS NOT NULL AND (embedding <=> $2::vector) < $3)
     ORDER BY text_rank DESC NULLS LAST
     LIMIT $4
     ```
     Pass `settings.recall_vector_distance_threshold` as `$3`.

   **Episode query** (episodes do NOT have a `tsv` column — only `content TEXT`):
     ```sql
     SELECT id, content, source_type, created_at,
            CASE WHEN embedding IS NOT NULL
                 THEN 1 - (embedding <=> $2::vector)
                 ELSE NULL
            END AS vector_sim
     FROM episode
     WHERE content ILIKE '%' || $1 || '%' ESCAPE '\\'
        OR (embedding IS NOT NULL AND (embedding <=> $2::vector) < $3)
     ORDER BY created_at DESC
     LIMIT $4
     ```
     For episodes, `text_rank` is `None` (no tsvector available). The hybrid scorer
     will redistribute the text weight to vector + recency automatically.

   - Compute `hybrid_score` for each result using `compute_hybrid_score()`:
     - Nodes: `text_rank` from `ts_rank`, `vector_sim` from cosine, `recency` from `created_at`
     - Episodes: `text_rank=None`, `vector_sim` from cosine, `recency` from `created_at`

4. **Extend `_recall_via_graph` in `adapter.py`**

   This is the fallback path used when `self._router is None` (no multi-schema routing — e.g.
   simpler setups or when pool is unavailable). Currently searches public schema only.

   **Merge strategy** when `query_embedding` is provided:
   ```python
   async def _recall_via_graph(self, query, agent_id, limit, query_embedding=None):
       # 1. Text search (existing) — returns nodes with ts_rank
       text_hits = await self._graph.search_by_text(query, limit=limit)

       # 2. Vector search (new) — returns nodes with cosine similarity
       vector_hits = []
       if query_embedding:
           vector_hits = await self._graph.search_by_vector(query_embedding, limit=limit)

       # 3. Episode search — text (ILIKE, existing) + vector (new)
       episodes = await self._graph.list_episodes(agent_id=agent_id, limit=max(limit * 5, 20))
       vector_episodes = []
       if query_embedding:
           vector_episodes = await self._graph.search_episodes_by_vector(
               query_embedding, agent_id=agent_id, limit=limit
           )

       # 4. Merge into a single dict keyed by (source_kind, id)
       #    For nodes seen in both text_hits and vector_hits, combine signals.
       #    For nodes seen in only one, the missing signal is None.
       merged = {}  # key: ("node", id) or ("episode", id) -> {text_rank, vector_sim, created_at}
       for hit in text_hits:
           merged[("node", hit["id"])] = {"text_rank": hit["rank"], "vector_sim": None, ...}
       for hit in vector_hits:
           key = ("node", hit["id"])
           if key in merged:
               merged[key]["vector_sim"] = hit["similarity"]
           else:
               merged[key] = {"text_rank": None, "vector_sim": hit["similarity"], ...}
       # ... same pattern for episodes (ILIKE matches + vector_episodes)

       # 5. Score each merged result via compute_hybrid_score(), sort, return top `limit`
   ```
   The key insight: a result may appear in both text and vector hits. Merge first, then score once.

5. **Update `recall` in `MemoryRepository` protocol**
   - Add optional `query_embedding: list[float] | None = None` parameter
   - Update both `InMemoryRepository` and `GraphServiceAdapter` implementations

6. **Update `recall` tool**
   - In `tools/recall.py`: get embedding service, embed the query, pass to `repo.recall()`:
     ```python
     embeddings = ctx.lifespan_context.get("embeddings")
     query_embedding = None
     if embeddings:
         query_embedding = await embeddings.embed(query)
     results = await repo.recall(query=query, agent_id=agent_id, limit=limit, query_embedding=query_embedding)
     ```

7. **Unit tests**
   - `tests/test_scoring.py`:
     - `test_recency_score_now` → ~1.0
     - `test_recency_score_one_half_life_ago` → ~0.5
     - `test_recency_score_very_old` → ~0.0
     - `test_hybrid_score_all_signals` → weighted combination
     - `test_hybrid_score_no_vector` → redistributes weight
     - `test_hybrid_score_no_text` → redistributes weight

### Verification

```bash
uv run pytest tests/test_scoring.py tests/ -v
# Integration test with real DB:
# 1. Store episodes with embeddings (via remember)
# 2. Recall with a semantically similar but lexically different query
# 3. Verify vector-matched results appear (wouldn't with text-only)
```

### Commit

```
feat(recall): implement hybrid scoring with vector + text + recency signals
```

---

## Stage 3: Developer TUI

**Goal**: Textual-based TUI for interacting with a running NeoCortex MCP server via MCP protocol.
Supports remember, recall, discover, and episode browsing.

### Steps

1. **Add dependencies**
   - In `pyproject.toml`: add `"textual>=3.0"` and `"click>=8.0"` to dependencies
   - `textual` — TUI framework; `click` — CLI argument parsing for the entry point
   - Run `uv sync`

2. **Create `src/neocortex/tui/` package**
   - `__init__.py`
   - `__main__.py` — entry point (`python -m neocortex.tui`)
   - `app.py` — main Textual `App` subclass
   - `client.py` — async MCP client that talks to the server via streamable-HTTP transport

3. **Implement `client.py`**
   - Class `NeoCortexClient`:
     - `__init__(self, base_url: str, token: str | None = None)`
     - Uses `fastmcp.Client` with streamable-HTTP transport to talk MCP protocol.
       The MCP server does NOT expose REST endpoints for tools — it uses the MCP
       protocol exclusively. The client invokes tools via `client.call_tool()`.
     - Example connection:
       ```python
       from fastmcp import Client
       from fastmcp.client.transports import StreamableHttpTransport

       transport = StreamableHttpTransport(
           url=f"{base_url}/mcp",
           headers={"Authorization": f"Bearer {token}"} if token else {},
       )
       client = Client(transport=transport)
       async with client:
           result = await client.call_tool("remember", {"text": "hello"})
       ```
     - Wrapper methods mapping to MCP tools:
       - `async def remember(self, text: str, context: str | None = None) -> dict`
       - `async def recall(self, query: str, limit: int = 10) -> dict`
       - `async def discover(self) -> dict`
     - Each method calls `self._client.call_tool(tool_name, args)` and parses the result

4. **Implement `app.py` — main TUI**
   - Layout with three panels:
     - **Left sidebar**: tool selector (Remember / Recall / Discover) + connection status
     - **Main area**: input form (top) + results display (bottom)
     - **Footer**: status bar with server URL, agent ID, key bindings
   - Screens/modes:
     - **Remember mode**: TextArea for content input, optional context field, submit button
       → shows confirmation with episode ID
     - **Recall mode**: Input field for query, limit slider, submit → shows ranked results
       as a DataTable (score, type, name, content preview, source, graph)
     - **Discover mode**: auto-fetches on enter → shows ontology tree (node types with counts,
       edge types with counts, graph stats)
   - Key bindings: `r` = remember, `q` = recall (query), `d` = discover, `ctrl+q` = quit
   - Color theme: use `rich` markup for scores (green = high, yellow = mid, red = low)

5. **Implement `__main__.py`**
   ```python
   import click
   from neocortex.tui.app import NeoCortexApp

   @click.command()
   @click.option("--url", default="http://localhost:8000", help="MCP server URL")
   @click.option("--token", default=None, help="Auth token")
   def main(url: str, token: str | None):
       app = NeoCortexApp(server_url=url, token=token)
       app.run()

   main()
   ```

6. **Add to README Quick Start**
   - Add TUI section:
     ```bash
     # Run TUI (connect to running MCP server)
     uv run python -m neocortex.tui --url http://localhost:8000 --token dev-token-neocortex
     ```

### Verification

```bash
# Start MCP server in one terminal:
NEOCORTEX_MOCK_DB=true uv run python -m neocortex
# Run TUI in another:
uv run python -m neocortex.tui --url http://localhost:8000
# Manually test:
# 1. Press 'r', type a memory, submit → see "stored" confirmation
# 2. Press 'q', type a query, submit → see recall results
# 3. Press 'd' → see ontology overview
```

### Commit

```
feat(tui): add Textual-based developer TUI for MCP server interaction
```

---

## Stage 4: Integration Verification

**Goal**: End-to-end test proving embeddings + hybrid recall work together through MCP tools.

### Steps

1. **Create `scripts/e2e_hybrid_recall_test.py`**
   - Requires running PostgreSQL + MCP server with real Gemini API key
   - **Client approach**: use `fastmcp.Client` with streamable-HTTP transport (same as the TUI
     client) to call MCP tools on the running server. This tests the full stack including auth,
     transport, and tool dispatch — not just the repository layer.
     ```python
     from fastmcp import Client
     from fastmcp.client.transports import StreamableHttpTransport

     transport = StreamableHttpTransport(
         url="http://localhost:8000/mcp",
         headers={"Authorization": "Bearer dev-token-neocortex"},
     )
     async with Client(transport=transport) as client:
         await client.call_tool("remember", {"text": "PostgreSQL supports JSONB..."})
         results = await client.call_tool("recall", {"query": "flexible data storage"})
     ```
   - Flow:
     1. `remember` 5-10 diverse facts (e.g., "PostgreSQL supports JSONB for flexible schemas",
        "The team decided to use React for the frontend", "Authentication uses OAuth2 with PKCE")
     2. Embeddings are generated synchronously within the `remember` tool call — no wait needed
     3. `recall` with semantically similar but lexically different queries:
        - "flexible data storage formats" → should find the JSONB fact
        - "frontend technology choice" → should find the React fact
        - "security protocol for login" → should find the OAuth2 fact
     4. Verify vector-matched results appear with non-zero vector scores
     5. `recall` with exact keyword match → verify text results still work
     6. `discover` → verify stats show episodes

2. **Verify scoring behavior**
   - Store an old fact and a new fact about the same topic
   - Recall → verify the newer one scores higher (recency boost)
   - Store a fact with exact keyword match → recall with that keyword
   - Verify text rank contributes to score

### Verification

```bash
# With Docker + API key:
docker compose up -d postgres
GOOGLE_API_KEY=... NEOCORTEX_AUTH_MODE=dev_token \
    NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
    uv run python scripts/e2e_hybrid_recall_test.py
```

### Commit

```
test(recall): add e2e test for hybrid recall with embeddings
```

---

## Execution Protocol

### Pre-requisites
- Python 3.13, `uv`, Docker (for integration tests)
- `GOOGLE_API_KEY` env var (for live embedding tests; unit tests mock it)

### For each stage
1. Read the stage steps
2. Implement all changes
3. Run verification commands
4. Run full test suite: `uv run pytest tests/ -v`
5. If lint/format issues: `uv run ruff check --fix src/ && uv run black src/`
6. Commit with the specified message + `Co-Authored-By`
7. Update progress tracker below

### If blocked
- If Gemini API returns errors: check model name (may have changed), fall back to `text-embedding-004`
- If pgvector cast fails: verify `::vector` cast syntax with asyncpg (may need string representation `'[0.1, 0.2, ...]'`)
- If Textual rendering breaks: simplify layout, test with `textual console` debug mode

---

## Progress Tracker

| Stage | Status | Notes |
|-------|--------|-------|
| 1. Embedding Service | DONE | EmbeddingService with Gemini 768-dim MRL, wired into remember + ingestion, 10 unit tests |
| 2. Hybrid Recall Scoring | PENDING | |
| 3. Developer TUI | PENDING | |
| 4. Integration Verification | PENDING | |

**Last stage completed**: 1. Embedding Service
**Last updated by**: plan-runner-agent
