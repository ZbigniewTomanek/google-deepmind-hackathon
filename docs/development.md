# Development Guide

## Prerequisites

- Docker and Docker Compose
- Python 3.13+ (see `.python-version`)
- `uv` package manager
- Port 5432 free (PostgreSQL)

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

Endpoints: `POST /ingest/text`, `POST /ingest/document` (file upload), `POST /ingest/events`.

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
| `NEOCORTEX_DEV_TOKEN` | `dev-token-neocortex` | Single dev token (legacy fallback) |

### Dev Tokens

`dev_tokens.json` maps bearer tokens to agent identities:

```json
{
  "alice-token": "alice",
  "bob-token": "bob",
  "shared-token": "shared",
  "dev-token-neocortex": "dev-user"
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

## E2E Smoke Test

Validates multi-agent isolation end-to-end against a running server:

```bash
# Start services
docker compose down -v && docker compose up -d

# Run smoke test
uv run python scripts/e2e_mcp_test.py
# or
bash scripts/run_e2e_mcp.sh

# Ingestion API E2E
bash scripts/run_e2e_ingestion.sh
```

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
│   ├── db/                 # Database adapters, protocols, RLS
│   ├── ingestion/          # FastAPI ingestion API (text, document, events)
│   ├── tools/              # MCP tools (remember, recall, discover)
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
│   └── 006_graph_registry.sql
└── templates/
    └── graph_schema.sql    # Template for dynamic schema provisioning

tests/
├── test_*.py               # Unit & integration tests
└── mcp/                    # MCP-specific tests
```
