# Plan: FastAPI Ingestion API

## Overview

Create a standalone FastAPI application exposing REST endpoints for bulk data ingestion (text, documents, events). It reuses NeoCortex's PostgreSQL infrastructure (`PostgresConfig`, `MemoryRepository` protocol) and mirrors the same dev-token auth so a single bearer token works for both MCP and ingestion. Internally, an `IngestionProcessor` protocol decouples endpoint handlers from parsing logic — stub implementation stores raw episodes; real extraction pipeline plugs in later.

Three endpoints: `POST /ingest/text`, `POST /ingest/document`, `POST /ingest/events`.

## Architecture

```
                    FastAPI App (:8001)
                    ├── /health
                    ├── /ingest/text      ─┐
                    ├── /ingest/document   ─┼── IngestionProcessor protocol
                    └── /ingest/events    ─┘        │
                         │                     StubProcessor (store_episode)
                    Auth: Bearer token              │
                    (same dev_tokens.json)     [future: ExtractionPipeline]
                         │
                    PostgresService (shared config)
                         │
                    PostgreSQL
```

## Stages

### Stage 1: Package skeleton, protocol, models

Create `src/neocortex/ingestion/` package with:

1. `__init__.py` — empty
2. `protocol.py` — `IngestionProcessor` typing Protocol with three methods:
   - `async def process_text(agent_id: str, text: str, metadata: dict) -> IngestionResult`
   - `async def process_document(agent_id: str, filename: str, content: bytes, content_type: str, metadata: dict) -> IngestionResult`
   - `async def process_events(agent_id: str, events: list[dict], metadata: dict) -> IngestionResult`
3. `models.py` — Pydantic request/response models:
   - `TextIngestionRequest(text: str, metadata: dict = {})`
   - `EventsIngestionRequest(events: list[dict], metadata: dict = {})`
   - `IngestionResult(status: str, episodes_created: int, message: str)`
4. `stub_processor.py` — `StubProcessor` implementing the protocol. Each method:
   - Calls `repo.store_episode()` for each chunk/event
   - Returns `IngestionResult` with count

**Verification**: `uv run python -c "from neocortex.ingestion.protocol import IngestionProcessor; from neocortex.ingestion.models import TextIngestionRequest, IngestionResult; print('OK')"`

**Commit**: `feat(ingestion): add ingestion protocol, models, and stub processor`

---

### Stage 2: FastAPI app with auth and lifespan

1. Add `fastapi` and `python-multipart` to `pyproject.toml` dependencies
2. Create `src/neocortex/ingestion/auth.py`:
   - `resolve_token_map(settings: MCPSettings) -> dict[str, str]` — same logic as `DevTokenAuth.__init__`
   - `get_agent_id(...)` — FastAPI `Depends()` that reads `Authorization: Bearer <token>`, looks up in token map, returns agent_id. Raises 401 on invalid token. Returns "anonymous" when auth_mode=none.
3. Create `src/neocortex/ingestion/app.py`:
   - `create_app(settings: MCPSettings | None = None) -> FastAPI`
   - Async lifespan: connects `PostgresService`, creates `GraphService` + `SchemaManager` + `GraphRouter` + `GraphServiceAdapter` (same as MCP server.py), instantiates `StubProcessor`
   - Stores `repo`, `processor`, `settings`, `pg` in `app.state`
   - `GET /health` endpoint
4. Create `src/neocortex/ingestion/__main__.py`:
   - Loads `MCPSettings`, calls `create_app()`, runs via `uvicorn.run()` on port 8001

**Verification**: `NEOCORTEX_MOCK_DB=true uv run python -m neocortex.ingestion &` then `curl localhost:8001/health`

**Commit**: `feat(ingestion): add FastAPI app with auth and lifespan`

---

### Stage 3: Wire up the three ingestion endpoints

1. Create `src/neocortex/ingestion/routes.py`:
   - `router = APIRouter(prefix="/ingest", tags=["ingestion"])`
   - `POST /text` — accepts `TextIngestionRequest` body, calls `processor.process_text()`
   - `POST /document` — accepts `UploadFile` + optional `metadata` form field, calls `processor.process_document()`
   - `POST /events` — accepts `EventsIngestionRequest` body, calls `processor.process_events()`
   - All endpoints use `Depends(get_agent_id)` for auth
   - All return `IngestionResult`
2. Register router in `app.py`: `app.include_router(router)`

**Verification**:
```bash
NEOCORTEX_MOCK_DB=true uv run python -m neocortex.ingestion &
curl -X POST localhost:8001/ingest/text \
  -H "Content-Type: application/json" \
  -d '{"text": "hello world"}'
# Should return {"status":"stored","episodes_created":1,"message":"..."}
```

**Commit**: `feat(ingestion): wire text, document, and events endpoints`

---

### Stage 4: Docker Compose service

1. Create `docker/ingestion/Dockerfile`:
   - Same base as `docker/mcp/Dockerfile`
   - CMD: `python -m neocortex.ingestion`
2. Add `neocortex-ingestion` service to `docker-compose.yml`:
   - Port 8001:8001
   - Same env vars as `neocortex-mcp` (DB, auth)
   - Depends on `postgres: service_healthy`

**Verification**: `docker compose config --services` shows `neocortex-ingestion`

**Commit**: `feat(ingestion): add Docker Compose service`

---

### Stage 5: Tests

1. Create `tests/test_ingestion_models.py` — validates Pydantic models
2. Create `tests/test_stub_processor.py` — unit tests with `InMemoryRepository`
3. Create `tests/test_ingestion_api.py` — FastAPI TestClient integration tests:
   - Health endpoint
   - Text ingestion (auth ok, auth fail, anonymous mode)
   - Document upload
   - Events ingestion
   - All using mock DB

**Verification**: `uv run pytest tests/test_ingestion*.py -v`

**Commit**: `test(ingestion): add unit and integration tests`

---

### Stage 6: Validation

1. Run full test suite: `uv run pytest tests/ -v`
2. Run lint: `uv run ruff check src/neocortex/ingestion/`
3. Verify mock-mode startup: `NEOCORTEX_MOCK_DB=true uv run python -m neocortex.ingestion`

**Commit**: (no commit — validation only)

---

## Execution Protocol

Stages are executed sequentially. Each stage:
1. Implement all steps
2. Run verification
3. Update progress tracker
4. Commit (one commit per stage)

## Progress Tracker

| Stage | Description | Status | Notes |
|-------|-------------|--------|-------|
| 1 | Package skeleton, protocol, models | PENDING | |
| 2 | FastAPI app with auth and lifespan | PENDING | |
| 3 | Wire ingestion endpoints | PENDING | |
| 4 | Docker Compose service | PENDING | |
| 5 | Tests | PENDING | |
| 6 | Validation | PENDING | |

Last stage completed: —
Last updated by: —
