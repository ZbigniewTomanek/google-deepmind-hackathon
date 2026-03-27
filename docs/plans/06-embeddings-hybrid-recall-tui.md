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
- **`google-genai` SDK** — already installed (`google-genai>=1.68.0`) via `pydantic-ai-slim[google]`.
  Async support via `client.aio.models.embed_content()`.
- **HNSW index** — the graph schema template already creates HNSW indexes on both `node.embedding`
  and `episode.embedding` (`vector_cosine_ops`, m=16, ef_construction=64). No migration needed.
- **Mock fallback** — when `NEOCORTEX_MOCK_DB=true` or `GOOGLE_API_KEY` is unset, the embedding
  service returns `None` and recall falls back to text-only (current behavior). No breaking changes.
- **Textual TUI** — `textual` is the standard Python TUI framework (built on `rich`, already
  installed). We add it as a dependency. The TUI connects via HTTP to the running MCP server.

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
     - `__init__(self, model: str = "gemini-embedding-exp-03-07", dimensions: int = 768)`
     - Lazy-init `google.genai.Client` from `GOOGLE_API_KEY` env var
     - `async def embed(self, text: str) -> list[float] | None` — returns normalized 768-dim
       vector or `None` if API unavailable
     - `async def embed_batch(self, texts: list[str]) -> list[list[float] | None]` — batch embed
       (Gemini supports list of contents in a single call)
     - Private `_normalize(vector: list[float]) -> list[float]` — L2 normalization
   - The `embed_content` call:
     ```python
     response = await self._client.aio.models.embed_content(
         model=self._model,
         contents=text,
         config=types.EmbedContentConfig(outputDimensionality=self._dimensions),
     )
     values = response.embeddings[0].values
     return self._normalize(values)
     ```
   - Wrap API call in `try/except` to gracefully return `None` on failure (log warning via loguru)

2. **Create `src/neocortex/embedding_protocol.py`**
   - Protocol class `EmbeddingProvider` with `async def embed(text: str) -> list[float] | None`
   - This lets us swap implementations (mock, cached, different model) without touching tools

3. **Wire into `ServiceContext`**
   - In `services.py`: add `embeddings: EmbeddingService | None` to `ServiceContext`
   - In `create_services()`: instantiate `EmbeddingService()` when not mock_db and
     `GOOGLE_API_KEY` is set, else `None`
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
   - Add `update_episode_embedding` to `MemoryRepository` protocol and both implementations

5. **Wire into ingestion `StubProcessor`**
   - In `ingestion/stub_processor.py`: accept optional `EmbeddingService`, generate embedding
     before storing episode

6. **Unit tests**
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
   - Accept `query_embedding: list[float] | None` parameter
   - When `query_embedding` is provided, run a **single combined SQL query** instead of two
     separate ones:
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
        OR (embedding IS NOT NULL AND (embedding <=> $2::vector) < 0.5)
     ORDER BY text_rank DESC NULLS LAST
     LIMIT $3
     ```
   - For episodes, similar combined query using `embedding <=> $2::vector` similarity
   - Compute `hybrid_score` for each result using `compute_hybrid_score()`

4. **Extend `_recall_via_graph` in `adapter.py`**
   - Same approach for the non-schema-routed path (public schema fallback)
   - Use `GraphService.search_by_vector()` alongside `search_by_text()` and merge

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

**Goal**: Textual-based TUI for interacting with a running NeoCortex MCP server over HTTP.
Supports remember, recall, discover, and episode browsing.

### Steps

1. **Add `textual` dependency**
   - In `pyproject.toml`: add `"textual>=3.0"` to dependencies
   - Run `uv sync`

2. **Create `src/neocortex/tui/` package**
   - `__init__.py`
   - `__main__.py` — entry point (`python -m neocortex.tui`)
   - `app.py` — main Textual `App` subclass
   - `client.py` — async HTTP client that talks to MCP server endpoints

3. **Implement `client.py`**
   - Class `NeoCortexClient`:
     - `__init__(self, base_url: str, token: str | None = None)`
     - Uses `httpx.AsyncClient` (already available via fastmcp deps)
     - Methods mapping to MCP tools:
       - `async def remember(self, text: str, context: str | None = None) -> dict`
       - `async def recall(self, query: str, limit: int = 10) -> dict`
       - `async def discover(self) -> dict`
       - `async def health(self) -> dict`
     - Sends requests to the MCP server's HTTP transport
     - Handles auth header if token provided

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
   - Flow:
     1. `remember` 5-10 diverse facts (e.g., "PostgreSQL supports JSONB for flexible schemas",
        "The team decided to use React for the frontend", "Authentication uses OAuth2 with PKCE")
     2. Wait briefly for embeddings to be generated
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
| 1. Embedding Service | NOT_STARTED | |
| 2. Hybrid Recall Scoring | NOT_STARTED | |
| 3. Developer TUI | NOT_STARTED | |
| 4. Integration Verification | NOT_STARTED | |

**Last stage completed**: —
**Last updated by**: —
