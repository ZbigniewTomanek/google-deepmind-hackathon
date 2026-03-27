# NeoCortex — Agent Memory System

Hackathon project (Google DeepMind x AI Tinkerers, Warsaw 2026). MCP server providing structured long-term memory for AI agents via PostgreSQL knowledge graph with multi-schema isolation.

## Codebase Map

```
src/neocortex/           # MCP server (FastMCP + asyncpg + Pydantic Settings)
  server.py              # Server factory + async lifespan
  db/protocol.py         # MemoryRepository protocol — THE contract for all storage
  db/adapter.py          # GraphServiceAdapter — production impl (multi-schema fan-out)
  db/mock.py             # InMemoryRepository — test impl (no Docker needed)
  db/scoped.py           # Schema/role-scoped connection context managers
  tools/                 # remember, recall, discover — MCP tools
  graph_router.py        # Heuristic routing: which schema(s) per operation
  schema_manager.py      # Graph schema lifecycle (create/drop/list)
  auth/                  # Pluggable auth (none / dev_token / google_oauth)

src/pydantic_agents_playground/  # Standalone POC: 3-agent extraction pipeline (SQLite)
migrations/init/         # Auto-applied on first Docker start (001-006)
migrations/templates/    # SQL template for dynamic per-graph schema provisioning
```

For full layout, configuration reference, and how-to guides, see `docs/development.md`.

## Build & Test

```bash
uv sync                                           # Install deps
uv run pytest tests/ -v                            # Unit tests (no Docker needed)
NEOCORTEX_MOCK_DB=true uv run python -m neocortex  # Run server with mock DB
docker compose up -d postgres                      # Start PostgreSQL
uv run python -m neocortex                         # Run server with real DB
```

## Architecture Rules

These are non-obvious patterns. Violating them breaks the system.

**1. Tools use `MemoryRepository` protocol, never `GraphService` directly.**
Tools get their repo from `ctx.lifespan_context["repo"]`. The protocol (`db/protocol.py`) has two implementations: `InMemoryRepository` (tests) and `GraphServiceAdapter` (production). Read `tools/remember.py` for the canonical pattern.

**2. Dependencies come from lifespan context, not globals.**
```python
repo = ctx.lifespan_context["repo"]        # MemoryRepository
settings = ctx.lifespan_context["settings"] # MCPSettings
agent_id = get_agent_id_from_context(ctx)   # from auth/dependencies.py
```

**3. Multi-graph isolation via PostgreSQL schemas.**
Each agent gets isolated schemas named `ncx_{agent_id}__{purpose}` (double underscore). `GraphRouter` decides routing: store -> personal graph (auto-created), recall -> fan-out across personal + shared, discover -> aggregate all accessible. Shared schemas get RLS; per-agent schemas don't.

**4. All SQL in graph schemas must go through scoped connections.**
`schema_scoped_connection(pool, schema)` for per-agent. `graph_scoped_connection(pool, schema, agent_id)` for shared (adds `SET LOCAL ROLE` for RLS). Schema names validated against `^ncx_[a-z0-9]+__[a-z0-9_]+$`. Use `asyncpg` parameterized queries (`$1`, `$2`) — never string interpolation.

**5. Auth mode determines agent identity.**
`NEOCORTEX_AUTH_MODE`: `none` -> "anonymous", `dev_token` -> from `dev_tokens.json` mapping, `google_oauth` -> OAuth subject. All resolved by `get_agent_id_from_context(ctx)`.

## Key References

- `docs/development.md` — setup, config, test conventions, adding tools/migrations, SQL safety
- `docs/architecture.md` — system design, data model, search capabilities
- `docs/plans/*.md` — completed implementation plans documenting design decisions and rationale
