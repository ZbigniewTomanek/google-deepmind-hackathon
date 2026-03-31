# Development Guide

## Prerequisites

- Docker and Docker Compose
- Python 3.13+ (see `.python-version`)
- `uv` package manager
- Port 5432 free (PostgreSQL)
- **ffmpeg** and **ffprobe** on PATH (required for audio/video media ingestion)

## Quick Start

### 1. Start PostgreSQL

```bash
docker compose up -d postgres
```

This starts PostgreSQL 16 with pgvector and applies all migrations from `migrations/init/` automatically on first run.

### 2. Install Dependencies

```bash
uv sync
```

### 3. Run the MCP Server

```bash
# With mock DB (no PostgreSQL needed)
NEOCORTEX_MOCK_DB=true uv run python -m neocortex

# With PostgreSQL
NEOCORTEX_AUTH_MODE=dev_token \
NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
uv run python -m neocortex
```

### 3b. Run the Ingestion API

The ingestion API is a separate FastAPI service on port 8001 for bulk data loading (text, documents, events). It reuses the same service stack and auth as the MCP server.

```bash
# With mock DB
NEOCORTEX_MOCK_DB=true uv run python -m neocortex.ingestion

# With PostgreSQL
NEOCORTEX_AUTH_MODE=dev_token \
NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
uv run python -m neocortex.ingestion
```

Ingestion endpoints:

```
POST /ingest/text      — body: {text, metadata, target_graph?}
POST /ingest/events    — body: {events, metadata, target_graph?}
POST /ingest/document  — multipart form with optional target_graph field
```

When `target_graph` is set, the agent must have write permission to the specified shared graph schema. Without it, data is stored in the agent's personal graph.

#### Media ingestion (audio/video)

The ingestion API also supports audio and video uploads. Media files go through a two-stage pipeline: ffmpeg compression followed by Gemini 3 Flash Preview multimodal inference to generate a text description. The description is stored as an episode (feeding the existing extraction pipeline), and the compressed file is persisted on the filesystem.

```
POST /ingest/audio  — multipart form: file + optional metadata + target_graph
POST /ingest/video  — multipart form: file + optional metadata + target_graph
```

Supported audio types: `audio/mpeg`, `audio/wav`, `audio/x-wav`, `audio/ogg`, `audio/flac`, `audio/aac`, `audio/mp4`, `audio/webm`

Supported video types: `video/mp4`, `video/mpeg`, `video/webm`, `video/quicktime`, `video/x-msvideo`, `video/x-matroska`, `video/3gpp`

Upload size limit: 100 MB (configurable via `NEOCORTEX_MEDIA_MAX_UPLOAD_BYTES`).

Example usage:

```bash
# Upload audio
curl -X POST localhost:8001/ingest/audio \
  -H "Authorization: Bearer claude-code-work" \
  -F "file=@recording.wav;type=audio/wav" \
  -F "metadata={\"source\": \"meeting\"}"

# Upload video
curl -X POST localhost:8001/ingest/video \
  -H "Authorization: Bearer claude-code-work" \
  -F "file=@clip.mp4;type=video/mp4" \
  -F "target_graph=ncx_shared__media"
```

Response includes a `media_ref` with the relative path to the stored compressed file:

```json
{
  "status": "stored",
  "episodes_created": 1,
  "message": "...",
  "media_ref": {
    "relative_path": "dev-user/abcd1234.ogg",
    "original_filename": "recording.wav",
    "content_type": "audio/wav",
    "compressed_size": 8192,
    "duration_seconds": 30.5
  }
}
```

**Media storage layout**: Compressed files are saved under `{NEOCORTEX_MEDIA_STORE_PATH}/{agent_id}/{uuid}.{ext}`. Paths in `media_ref` are relative to the store root. Audio is compressed to 64 kbps mono Opus (`.ogg`), video to 480p CRF-30 H.264 with 64 kbps mono audio (`.mp4`).

**Mock mode**: When `NEOCORTEX_MOCK_DB=true`, compression is skipped and a placeholder description is generated. Media files are still saved to the media store. This allows endpoint testing without ffmpeg or a Gemini API key.

Admin API (mounted on the same ingestion server):

```
POST   /admin/permissions                    Grant/update permission
DELETE /admin/permissions/{agent_id}/{schema} Revoke permission
GET    /admin/permissions                    List permissions (?agent_id=X or ?schema_name=X)
GET    /admin/permissions/{agent_id}         List permissions for agent
GET    /admin/agents                         List registered agents
PUT    /admin/agents/{agent_id}/admin        Promote to admin
DELETE /admin/agents/{agent_id}/admin        Demote from admin
POST   /admin/graphs                         Create shared graph
GET    /admin/graphs                         List all graphs
DELETE /admin/graphs/{schema_name}           Drop shared graph
```

All `/admin/` endpoints require admin auth (bearer token resolving to an agent with `is_admin=true`).

### 3c. Run the Developer TUI

The TUI connects to a running MCP server via streamable-HTTP transport. Start the server first, then launch the TUI.

```bash
# Connect to running MCP server
uv run python -m neocortex.tui --url http://localhost:8000 --token tui-dev
```

Key bindings: `r` = remember, `q` = recall, `d` = discover, `Ctrl+Q` = quit.

### 4. Run Tests

```bash
# Unit tests (no Docker needed)
uv run pytest tests/ -v

# With RLS integration tests (requires Docker PostgreSQL)
NEOCORTEX_RUN_RLS_TESTS=1 uv run pytest tests/ -v
```

## Docker Compose Services

| Service | Description |
|---------|-------------|
| `postgres` | PostgreSQL 16 + pgvector, port 5432, auto-applies init migrations |
| `neocortex-mcp` | MCP server container (FastMCP), port 8000, connects to PostgreSQL |
| `neocortex-ingestion` | Ingestion API container (FastAPI), port 8001, connects to PostgreSQL |

```bash
# Full stack
docker compose up -d

# Clean restart (wipes data)
docker compose down -v && docker compose up -d
```

## Configuration

All configuration via environment variables (Pydantic BaseSettings):

### PostgreSQL (`config.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | `localhost` | Database host |
| `POSTGRES_PORT` | `5432` | Database port |
| `POSTGRES_DB` | `neocortex` | Database name |
| `POSTGRES_USER` | `neocortex` | Database user |
| `POSTGRES_PASSWORD` | `neocortex` | Database password |

### MCP Server (`mcp_settings.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `NEOCORTEX_AUTH_MODE` | `none` | Auth mode: `none`, `dev_token`, `google_oauth` |
| `NEOCORTEX_MOCK_DB` | `false` | Use in-memory mock instead of PostgreSQL |
| `NEOCORTEX_DEV_TOKENS_FILE` | `` | Path to JSON file mapping tokens → agent IDs |
| `NEOCORTEX_DEV_TOKEN` | `dev-token-neocortex` | Single dev token (deprecated fallback) |

### Embeddings & Hybrid Recall (`mcp_settings.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_API_KEY` | _(unset)_ | Google AI API key for Gemini embeddings. When unset, embedding calls return `None` and recall falls back to text-only |
| `NEOCORTEX_EMBEDDING_MODEL` | `gemini-embedding-001` | Gemini embedding model name |
| `NEOCORTEX_RECALL_WEIGHT_VECTOR` | `0.3` | Hybrid recall weight for vector cosine similarity |
| `NEOCORTEX_RECALL_WEIGHT_TEXT` | `0.2` | Hybrid recall weight for text rank |
| `NEOCORTEX_RECALL_WEIGHT_RECENCY` | `0.1` | Hybrid recall weight for recency decay |
| `NEOCORTEX_RECALL_WEIGHT_ACTIVATION` | `0.25` | Hybrid recall weight for ACT-R base activation |
| `NEOCORTEX_RECALL_WEIGHT_IMPORTANCE` | `0.15` | Hybrid recall weight for node importance |
| `NEOCORTEX_RECALL_RECENCY_HALF_LIFE_HOURS` | `168.0` | Recency half-life in hours (7 days) |
| `NEOCORTEX_RECALL_VECTOR_DISTANCE_THRESHOLD` | `0.5` | Cosine distance threshold for vector match |

### Media Ingestion (`mcp_settings.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `NEOCORTEX_MEDIA_STORE_PATH` | `./media_store` | Root directory for compressed media files |
| `NEOCORTEX_MEDIA_MAX_UPLOAD_BYTES` | `104857600` (100 MB) | Maximum upload size for audio/video files |
| `NEOCORTEX_MEDIA_DESCRIPTION_MODEL` | `gemini-3-flash-preview` | Gemini model for multimodal description |
| `NEOCORTEX_MEDIA_DESCRIPTION_MAX_TOKENS` | `8192` | Max output tokens for media descriptions |
| `GOOGLE_API_KEY` | _(unset)_ | Required for Gemini media descriptions in production mode |

### Domain Routing (`mcp_settings.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `NEOCORTEX_DOMAIN_ROUTING_ENABLED` | `true` | Enable automatic routing to shared domain graphs. Requires `extraction_enabled=true` (uses the job queue) |
| `NEOCORTEX_DOMAIN_CLASSIFIER_MODEL` | `gemini-3-flash-preview` | Gemini model for domain classification |
| `NEOCORTEX_DOMAIN_CLASSIFIER_THINKING_EFFORT` | `low` | Thinking effort for domain classifier |
| `NEOCORTEX_DOMAIN_CLASSIFICATION_THRESHOLD` | `0.3` | Minimum confidence for domain match |

### Admin & Permissions (`mcp_settings.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `NEOCORTEX_BOOTSTRAP_ADMIN_ID` | `admin` | Agent ID seeded as admin on every startup |
| `NEOCORTEX_ADMIN_TOKEN` | `admin-token` | Bearer token for bootstrap admin (dev mode) |

### Dev Tokens

`dev_tokens.json` maps bearer tokens to agent identities:

```json
{
  "admin-token": "admin",
  "claude-code-work": "cc-work",
  "claude-code-private": "cc-private",
  "claude-code-oss": "cc-oss",
  "tui-dev": "dev-user"
}
```

## POC: Pydantic AI Playground

Standalone demo of the 3-agent extraction pipeline using SQLite:

```bash
# Offline mode (TestModel, no API key needed)
uv run python -m pydantic_agents_playground --use-test-model --reset-db --run-demo

# Live with Gemini
export GOOGLE_API_KEY=your_key
uv run python -m pydantic_agents_playground --reset-db --run-demo
```

Inspect the output database:
```bash
sqlite3 data/pydantic_agents_playground.sqlite "SELECT count(*) FROM processing_runs;"
```

## E2E Tests

The unified runner handles everything: starts PostgreSQL, applies migrations, launches both servers with `dev_token` auth, runs the test, and tears down on exit. It sources `.env` automatically for `GOOGLE_API_KEY`.

```bash
# MCP server smoke test (multi-agent isolation, discover cognitive stats)
./scripts/run_e2e.sh scripts/e2e_mcp_test.py

# Ingestion API (text/doc/events, auth, target_graph permission enforcement,
# domain routing job creation verification)
./scripts/run_e2e.sh scripts/e2e_ingestion_test.py

# Embedding / hybrid recall (requires GOOGLE_API_KEY in .env)
./scripts/run_e2e.sh scripts/e2e_embedding_test.py
./scripts/run_e2e.sh scripts/e2e_hybrid_recall_test.py

# Permission system (shared graphs, grant/revoke, admin lifecycle, read via MCP recall)
./scripts/run_e2e.sh scripts/e2e_permission_test.py

# Extraction pipeline + domain routing (ingest → extract → recall with graph context,
# cognitive fields, consolidation, node importance, discover stats,
# domain classification → shared schema population — requires GOOGLE_API_KEY, ~5 min)
./scripts/run_e2e.sh scripts/e2e_extraction_pipeline_test.py

# Cognitive heuristics (ACT-R activation, spreading activation, edge reinforcement,
# importance hints, consolidation — requires GOOGLE_API_KEY, ~2 min)
./scripts/run_e2e.sh scripts/e2e_cognitive_recall_test.py

# Media ingestion (real ffmpeg compression + Gemini description, uploads 2-min
# MP3/MP4 demo clips, verifies episodes in DB and compressed files on disk)
./scripts/run_e2e.sh scripts/e2e_media_ingestion_test.py

# Docker mode (builds images, runs everything in containers)
./scripts/run_e2e.sh --docker scripts/e2e_mcp_test.py

# Keep services up after the test for debugging
KEEP_RUNNING=1 ./scripts/run_e2e.sh scripts/e2e_mcp_test.py
```

The extraction-dependent tests (`e2e_extraction_pipeline_test.py`, `e2e_cognitive_recall_test.py`) clean up stale jobs before running and track only their own extraction jobs, so they work reliably even with leftover state from prior runs. The extraction pipeline test triggers 3 personal + 3 domain extraction jobs (~18 Gemini API calls); the cognitive recall test triggers 3 extraction jobs (~9 Gemini API calls).

The extraction pipeline test also validates domain routing end-to-end: it provisions shared domain schemas via the admin API, grants write permissions, ingests seed texts, and verifies that `route_episode` jobs classify episodes and populate shared domain schemas (e.g., `ncx_shared__domain_knowledge`) with extracted nodes and edges alongside the personal graph.

## Linting

```bash
uv run ruff check src
uv run black --check src
```

## Test Conventions

- **Async by default**: Use `@pytest.mark.asyncio` and `async def test_*()`
- **Fixtures**: Session-scoped for DB connections (`pg_service`, `graph_service`), function-scoped for data
- **Mock path**: Use `InMemoryRepository` for unit tests, real PostgreSQL for integration
- **Test data naming**: Prefix with `test_` (e.g., `agent_id="test_alice"`, `source="test_store"`). Conftest cleanup filters by this pattern.
- **RLS tests gated**: Behind `NEOCORTEX_RUN_RLS_TESTS=1` env var (skipped by default)

## Adding a New MCP Tool

1. Create `src/neocortex/tools/my_tool.py` following `remember.py` pattern
2. Add Pydantic I/O models in `schemas/memory.py`
3. Register in `tools/__init__.py` via `mcp.tool(my_tool)`
4. Add protocol method to `db/protocol.py`
5. Implement in `db/mock.py` (InMemoryRepository) and `db/adapter.py` (GraphServiceAdapter)
6. Write tests in `tests/mcp/test_tools.py` using mock fixtures

## Adding a New Migration

1. Add `migrations/init/NNN_description.sql` for one-time schema changes
2. If the change affects per-graph schemas, also update `migrations/templates/graph_schema.sql`
3. Recreate the database: `docker compose down -v && docker compose up -d`

## SQL Safety

- Schema names are validated against `^ncx_[a-z0-9]+__[a-z0-9_]+$` before use in SQL
- `SET LOCAL search_path` is used (transaction-scoped, not session-level)
- Template SQL uses `{schema_name}` placeholders with validated inputs
- Never interpolate user-provided values into SQL — use `asyncpg` parameterized queries (`$1`, `$2`, ...)

## Project Layout

```
src/
├── neocortex/              # MCP server & core memory system
│   ├── server.py           # FastMCP server factory + lifespan
│   ├── config.py           # PostgreSQL config
│   ├── mcp_settings.py     # MCP server settings
│   ├── models.py           # Domain models (Node, Edge, Episode, etc.)
│   ├── graph_service.py    # Graph CRUD & search
│   ├── graph_router.py     # Multi-graph routing heuristics
│   ├── schema_manager.py   # Graph schema lifecycle
│   ├── postgres_service.py # Connection pool & health checks
│   ├── auth/               # Authentication (dev tokens, Google OAuth)
│   ├── permissions/        # Schema-level access control
│   │   ├── protocol.py     # PermissionChecker protocol
│   │   ├── pg_service.py   # PostgreSQL implementation
│   │   └── memory_service.py # In-memory implementation (tests/mock)
│   ├── admin/              # Admin REST API (mounted on ingestion app)
│   │   ├── auth.py         # require_admin dependency
│   │   └── routes.py       # Permission + graph management endpoints
│   ├── domains/            # Semantic domain routing (upper ontology)
│   │   ├── models.py       # SemanticDomain, ClassificationResult, RoutingResult
│   │   ├── protocol.py     # DomainService protocol
│   │   ├── pg_service.py   # PostgreSQL implementation
│   │   ├── memory_service.py # In-memory implementation (tests/mock)
│   │   ├── classifier.py   # PydanticAI classification agent + mock
│   │   └── router.py       # DomainRouter — classify → route → extract
│   ├── embedding_service.py # Gemini embedding wrapper (768-dim MRL, normalized)
│   ├── scoring.py          # Hybrid recall scoring (vector + text + recency)
│   ├── db/                 # Database adapters, protocols, RLS
│   ├── ingestion/          # FastAPI ingestion API (text, document, events, audio, video)
│   │   ├── media_models.py       # MediaRef, MediaIngestionResult, CompressedMedia
│   │   ├── media_store.py        # Filesystem-based media file store
│   │   ├── media_compressor.py   # ffmpeg compression service
│   │   ├── media_description.py  # Gemini multimodal description service
│   │   └── media_description_mock.py  # Mock description service for tests
│   ├── tools/              # MCP tools (remember, recall, discover)
│   ├── tui/                # Developer TUI (Textual + Click)
│   │   ├── app.py          # Textual App with remember/recall/discover modes
│   │   ├── client.py       # MCP client (streamable-HTTP transport)
│   │   └── __main__.py     # CLI entry point
│   └── schemas/            # Pydantic I/O schemas
│
└── pydantic_agents_playground/  # POC: 3-agent pipeline
    ├── agents.py           # Ontology, Extractor, Librarian agents
    ├── pipeline.py         # Sequential demo runner
    ├── database.py         # SQLite repository
    └── messages.py         # BMW seed corpus (10 messages)

migrations/
├── init/                   # Auto-applied on first Docker start
│   ├── 001_extensions.sql  # pgvector, pg_trgm
│   ├── 002_schema.sql      # Core tables
│   ├── 003_indexes.sql     # Vector + text indexes
│   ├── 004_seed_ontology.sql
│   ├── 005_rls_roles.sql   # Row-Level Security
│   ├── 006_graph_registry.sql
│   ├── 007_graph_permissions.sql  # agent_registry + graph_permissions
│   └── 008_ontology_domains.sql   # Domain routing ontology table + seed domains
└── templates/
    └── graph_schema.sql    # Template for dynamic schema provisioning

tests/
├── test_*.py               # Unit & integration tests
└── mcp/                    # MCP-specific tests
```
