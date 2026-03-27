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
                         │                     StubProcessor(repo: MemoryRepository)
                    Auth: Bearer token              │
                    (reuses load_token_map())  [future: ExtractionPipeline]
                         │
                    create_services() ← shared with server.py
                         │
                    PostgreSQL
```

## Stages

### Stage 1: Extract shared service factory from server.py

Refactor `server.py` to extract the service initialization sequence into a reusable factory, so both the MCP server and the ingestion API share a single source of truth.

1. Create `src/neocortex/services.py`:
   - Define `ServiceContext` TypedDict with keys: `repo`, `pg`, `graph`, `schema_mgr`, `router`, `settings`
   - `async def create_services(settings: MCPSettings) -> ServiceContext` — contains the current `server.py` init sequence: `PostgresService` → `GraphService` → `SchemaManager` → `GraphRouter` → `GraphServiceAdapter`
   - `async def shutdown_services(ctx: ServiceContext) -> None` — calls `pg.disconnect()`
   - For `mock_db=True`: returns `ServiceContext` with `repo=InMemoryRepository()` and `None` for pg/graph/schema_mgr/router
2. Extract `load_token_map(settings: MCPSettings) -> dict[str, str]` from `DevTokenAuth.__init__` into `src/neocortex/auth/tokens.py`:
   - Loads `dev_tokens.json` if configured, falls back to single `dev_token`/`dev_user_id`
   - `DevTokenAuth.__init__` calls `load_token_map()` instead of inlining the logic
3. Update `server.py` to use `create_services()` / `shutdown_services()` in its lifespan

**Verification**: `uv run pytest tests/ -v` (existing tests still pass)

**Commit**: `refactor: extract shared service factory and token-map loader`

---

### Stage 2: Package skeleton, protocol, models

Create `src/neocortex/ingestion/` package with:

1. `__init__.py` — empty
2. `protocol.py` — `IngestionProcessor` typing Protocol with three methods:
   - `async def process_text(agent_id: str, text: str, metadata: dict) -> IngestionResult`
   - `async def process_document(agent_id: str, filename: str, content: bytes, content_type: str, metadata: dict) -> IngestionResult`
   - `async def process_events(agent_id: str, events: list[dict], metadata: dict) -> IngestionResult`
3. `models.py` — Pydantic request/response models:
   - `TextIngestionRequest(text: str, metadata: dict = Field(default_factory=dict))`
   - `EventsIngestionRequest(events: list[dict], metadata: dict = Field(default_factory=dict))`
   - `IngestionResult(status: Literal["stored", "failed", "partial"], episodes_created: int, message: str)`
4. `stub_processor.py` — `StubProcessor` implementing the protocol:
   - Constructor: `__init__(self, repo: MemoryRepository)` — stores repo as instance attribute
   - `process_text`: calls `repo.store_episode(agent_id, text, source_type="ingestion_text")`, returns `IngestionResult(status="stored", episodes_created=1, ...)`
   - `process_document`: calls `repo.store_episode(agent_id, content.decode("utf-8", errors="replace"), source_type="ingestion_document")`, stores entire raw content as a single episode (chunking deferred to future `ExtractionPipeline`)
   - `process_events`: wraps all `repo.store_episode(agent_id, json.dumps(event), source_type="ingestion_event")` calls in a single logical batch — if any call raises, returns `IngestionResult(status="partial", episodes_created=<count_so_far>, message="...")`. On full success returns `status="stored"`

**Verification**: `uv run python -c "from neocortex.ingestion.protocol import IngestionProcessor; from neocortex.ingestion.models import TextIngestionRequest, IngestionResult; print('OK')"`

**Commit**: `feat(ingestion): add ingestion protocol, models, and stub processor`

---

### Stage 3: FastAPI app with auth and lifespan

1. Add `fastapi`, `uvicorn`, and `python-multipart` to `pyproject.toml` dependencies
2. Create `src/neocortex/ingestion/auth.py`:
   - `get_agent_id(...)` — FastAPI `Depends()` that reads `Authorization: Bearer <token>`, calls `load_token_map(settings)` (from `auth/tokens.py`) to resolve token → agent_id. Raises `HTTPException(401)` on invalid token. Returns `"anonymous"` when `auth_mode="none"`
3. Create `src/neocortex/ingestion/app.py`:
   - `create_app(settings: MCPSettings | None = None) -> FastAPI`
   - Async lifespan: calls `create_services(settings)` from `services.py`, instantiates `StubProcessor(repo=ctx["repo"])`
   - Stores `services_ctx`, `processor`, `settings` in `app.state`
   - On shutdown: calls `shutdown_services(ctx)`
   - `GET /health` endpoint
4. Create `src/neocortex/ingestion/__main__.py`:
   - Loads `MCPSettings`, calls `create_app()`, runs via `uvicorn.run()` on port 8001

**Verification**: `NEOCORTEX_MOCK_DB=true uv run python -m neocortex.ingestion &` then `curl localhost:8001/health`

**Commit**: `feat(ingestion): add FastAPI app with auth and lifespan`

---

### Stage 4: Wire up the three ingestion endpoints

1. Create `src/neocortex/ingestion/routes.py`:
   - `router = APIRouter(prefix="/ingest", tags=["ingestion"])`
   - `POST /text` — accepts `TextIngestionRequest` JSON body, calls `processor.process_text()`
   - `POST /document` — accepts `UploadFile` (read fully via `await file.read()`) + optional `metadata` JSON form field. Max upload size: 10 MB (reject with 413 if exceeded). Accepted content types: `text/plain`, `application/json`, `text/markdown`, `text/csv` (reject others with 415). Calls `processor.process_document(agent_id, file.filename, content_bytes, file.content_type, metadata)`
   - `POST /events` — accepts `EventsIngestionRequest` JSON body, calls `processor.process_events()`
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

### Stage 5: Docker Compose service

1. Create `docker/ingestion/Dockerfile`:
   - Same base image (`python:3.13-slim`) and build steps as `docker/mcp/Dockerfile`
   - `EXPOSE 8001`
   - CMD: `uv run python -m neocortex.ingestion`
2. Add shared env block to `docker-compose.yml` using YAML anchor:
   ```yaml
   x-common-env: &common-env
     NEOCORTEX_MOCK_DB: "false"
     NEOCORTEX_AUTH_MODE: "dev_token"
     NEOCORTEX_DEV_TOKENS_FILE: "/app/dev_tokens.json"
     POSTGRES_HOST: postgres
     POSTGRES_PORT: "5432"
     POSTGRES_USER: neocortex
     POSTGRES_PASSWORD: neocortex
     POSTGRES_DATABASE: neocortex
   ```
3. Update `neocortex-mcp` to use `environment: { <<: *common-env, NEOCORTEX_TRANSPORT: http, NEOCORTEX_SERVER_HOST: "0.0.0.0" }`
4. Add `neocortex-ingestion` service:
   - `environment: { <<: *common-env }`
   - Port `8001:8001`
   - Same `volumes` for `dev_tokens.json`
   - `depends_on: postgres: condition: service_healthy`

**Verification**: `docker compose config --services` shows `neocortex-ingestion`

**Commit**: `feat(ingestion): add Docker Compose service`

---

### Stage 6: Tests

1. Create `tests/test_ingestion_models.py` — validates Pydantic models (defaults, validation errors, status literal)
2. Create `tests/test_stub_processor.py` — unit tests with `InMemoryRepository`:
   - `process_text` stores one episode with `source_type="ingestion_text"`
   - `process_document` stores raw content as single episode with `source_type="ingestion_document"`
   - `process_events` stores N episodes with `source_type="ingestion_event"`, verifies count
   - Partial failure scenario for `process_events`
3. Create `tests/test_ingestion_api.py` — FastAPI TestClient integration tests:
   - Health endpoint
   - Text ingestion (auth ok, auth fail, anonymous mode)
   - Document upload (valid type, rejected type → 415, oversized → 413)
   - Events ingestion
   - All using mock DB

**Verification**: `uv run pytest tests/test_ingestion*.py -v`

**Commit**: `test(ingestion): add unit and integration tests`

---

### Stage 7: Validation

1. Run full test suite: `uv run pytest tests/ -v`
2. Run lint: `uv run ruff check src/neocortex/ingestion/ src/neocortex/services.py src/neocortex/auth/tokens.py`
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
| 1 | Extract shared service factory | DONE | Created services.py (ServiceContext, create_services, shutdown_services), auth/tokens.py (load_token_map), updated server.py and dev.py |
| 2 | Package skeleton, protocol, models | DONE | Created ingestion package: protocol.py (IngestionProcessor), models.py (request/response), stub_processor.py (StubProcessor) |
| 3 | FastAPI app with auth and lifespan | DONE | Created auth.py (get_agent_id dependency), app.py (create_app with lifespan), __main__.py (uvicorn entrypoint). Added fastapi, uvicorn, python-multipart deps. |
| 4 | Wire ingestion endpoints | DONE | Created routes.py with POST /ingest/text, /ingest/document (10MB limit, content-type validation), /ingest/events. Registered router in app.py. |
| 5 | Docker Compose service | DONE | Created docker/ingestion/Dockerfile, added x-common-env YAML anchor and neocortex-ingestion service to docker-compose.yml |
| 6 | Tests | PENDING | |
| 7 | Validation | PENDING | |

Last stage completed: Stage 5 — Docker Compose service
Last updated by: plan-runner-agent
