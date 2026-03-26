# Plan: MCP Server Scaffold (FastMCP + Google OAuth + PG Role Mapping)

## Overview

Scaffold the NeoCortex MCP server layer on top of the PostgreSQL storage layer built by [Plan 02](./02-postgres-storage-layer.md). The server uses [FastMCP](https://gofastmcp.com) to expose three high-level tools (`remember`, `recall`, `discover`) via the MCP protocol. Authentication uses Google OAuth via FastMCP's `OAuthProxy`. Each authenticated user maps to a dedicated PostgreSQL role — the server uses `SET LOCAL ROLE` per-transaction and PostgreSQL Row-Level Security (RLS) policies enforce data isolation at the database level.

**Two-phase structure:**
- **Stages 1–6** are independent of Plan 02 and can execute on the `mcp` branch while Plan 02 is being developed on `main`. These stages create files that do NOT overlap with Plan 02's outputs.
- **Stage 7** is a rebase checkpoint — wait for Plan 02 to land on `main`, then rebase.
- **Stages 8–9** integrate with Plan 02's `PostgresService` and `GraphService`, add RLS policies, and wire the real database into MCP tools.

### Relationship to Plan 02

Plan 02 creates the storage foundation (`src/neocortex/` package with `config.py`, `models.py`, `postgres_service.py`, `graph_service.py`, `docker-compose.yml`, `migrations/`). This plan extends that package with MCP-specific modules in non-overlapping paths:

| Plan 02 creates (don't touch) | Plan 03 creates (new files) |
|---|---|
| `src/neocortex/__init__.py` | `src/neocortex/__main__.py` |
| `src/neocortex/config.py` | `src/neocortex/mcp_settings.py` |
| `src/neocortex/models.py` | `src/neocortex/server.py` |
| `src/neocortex/postgres_service.py` | `src/neocortex/tools/` (subpackage) |
| `src/neocortex/graph_service.py` | `src/neocortex/auth/` (subpackage, incl. `dev.py`) |
| `docker-compose.yml` | `src/neocortex/schemas/` (tool I/O models) |
| `migrations/init/001-004.sql` | `src/neocortex/db/` (roles, scoped connections) |
| `tests/conftest.py`, `tests/test_*.py` | `tests/mcp/` (MCP-specific tests) |

After rebase (Stage 7), both sets of files coexist. Integration stages (8–9) wire them together.

### FastMCP Documentation Reference

If you encounter issues during implementation, consult these FastMCP docs (fetch via `WebFetch`):

| Topic | URL | When to consult |
|-------|-----|-----------------|
| Welcome & Install | https://gofastmcp.com/getting-started/welcome | Stage 1 — dependency setup, basic concepts |
| Quickstart | https://gofastmcp.com/getting-started/quickstart | Stage 2 — minimal server example |
| Server (`FastMCP` class) | https://gofastmcp.com/servers/fastmcp | Stage 2 — constructor params, custom routes, `on_duplicate_*` |
| Tools | https://gofastmcp.com/servers/tools | Stage 2, 3 — `@mcp.tool`, type annotations, structured output, `ToolAnnotations` |
| Context | https://gofastmcp.com/servers/context | Stage 5 — `Context`, `CurrentContext()`, `lifespan_context`, session state |
| Dependencies | https://gofastmcp.com/servers/dependencies | Stage 4, 5 — `Depends()`, `CurrentAccessToken()`, `TokenClaim()`, custom deps |
| Auth overview | https://gofastmcp.com/servers/auth | Stage 4 — `OAuthProxy`, `JWTVerifier`, `MultiAuth`, token access |
| Resources | https://gofastmcp.com/servers/resources | Optional — if exposing graph data as MCP resources later |
| Prompts | https://gofastmcp.com/servers/prompts | Optional — if adding MCP prompt templates later |
| Running & Deployment | https://gofastmcp.com/deployment/running | Stage 2, 8 — transports (http/stdio/sse), `mcp.run()`, ASGI, CLI |
| Client (testing) | https://gofastmcp.com/clients/client | Stage 6 — in-memory `Client` for tool testing |
| Composition | https://gofastmcp.com/servers/composition | Optional — if composing multiple servers |

**Troubleshooting priority**: If a FastMCP API doesn't match what this plan describes (e.g., import path changed, class renamed), fetch the relevant doc page above to find the current API. FastMCP evolves quickly — the docs are authoritative.

## Execution Protocol

To execute this plan, follow this loop for each stage:

1. **Read the progress tracker** below and find the first stage that is not DONE
2. **Read the stage details** — understand the goal, dependencies, and steps
3. **Clarify ambiguities** — if anything is unclear or multiple approaches exist,
   ask the user before implementing. Do not guess.
4. **Implement** — execute the steps described in the stage
5. **Validate** — run the verification checks listed in the stage.
   If validation fails, fix the issue before proceeding. Do not skip verification.
6. **Update this plan** — mark the stage as DONE in the progress tracker,
   add brief notes about what was done and any deviations from the original steps
7. **Commit** — create an atomic commit with the message specified in the stage.
   Include all changed files (code, config, docs, and this plan file).

Repeat until all stages are DONE or a stage is BLOCKED.

**If a stage cannot be completed**: mark it BLOCKED in the tracker with a note
explaining why, and stop. Do not proceed to subsequent stages.

**If assumptions are wrong**: stop, document the issue in the Issues section below,
revise affected stages, and get user confirmation before continuing.

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | MCP package extensions & dependencies | PENDING | | |
| 2 | FastMCP server with 3 tool stubs | PENDING | | |
| 3 | Tool I/O schemas | PENDING | | |
| 4 | Auth layer (dev-token + Google OAuth) | PENDING | | |
| 5 | In-memory mock repository & role mapping | PENDING | | |
| 6 | MCP-layer tests | PENDING | | |
| 7 | Rebase onto Plan 02 | PENDING | | |
| 8 | PostgreSQL integration — wire tools to GraphService | PENDING | | |
| 9 | RLS policies & role-based access | PENDING | | |
| 10 | Push to remote, create PR, and merge to main | PENDING | | |

Statuses: `PENDING` → `IN_PROGRESS` → `DONE` | `BLOCKED`

---

## Stage 1: MCP package extensions & dependencies

**Goal**: Add FastMCP-specific modules to the `src/neocortex/` package (which Plan 02 may or may not have created yet on this branch). Update `pyproject.toml` with MCP-specific dependencies.
**Dependencies**: None
**Docs**: [Welcome & Install](https://gofastmcp.com/getting-started/welcome) — verify install instructions and minimum version

**Steps**:

1. Create directory structure for MCP-specific modules. If `src/neocortex/__init__.py` doesn't exist yet on this branch, create a minimal one (it will be replaced by Plan 02's version on rebase):
   ```
   src/neocortex/
   ├── __init__.py          # Minimal: """NeoCortex — Agent Memory System.""" (if not present)
   ├── __main__.py          # NEW — entry point for MCP server
   ├── mcp_settings.py      # NEW — MCP-specific configuration
   ├── server.py            # NEW — FastMCP server factory
   ├── tools/
   │   ├── __init__.py      # NEW
   │   ├── remember.py      # NEW
   │   ├── recall.py        # NEW
   │   └── discover.py      # NEW
   ├── auth/
   │   ├── __init__.py      # NEW
   │   ├── dev.py           # NEW — dev-token auth for testing
   │   ├── google.py        # NEW
   │   └── dependencies.py  # NEW
   ├── schemas/
   │   ├── __init__.py      # NEW
   │   └── memory.py        # NEW — tool I/O models only
   └── db/
       ├── __init__.py      # NEW
       ├── protocol.py      # NEW — repository protocol (ABC)
       ├── roles.py         # NEW — OAuth→PG role mapping
       ├── scoped.py        # NEW — scoped connections
       └── mock.py          # NEW — in-memory mock implementation
   ```

2. Update `pyproject.toml` — add FastMCP dependency and test deps. Be additive only (Plan 02 adds asyncpg, pydantic, pydantic-settings separately):
   ```toml
   dependencies = [
       "pydantic-ai-slim[google]>=1.72.0",
       "loguru>=0.7.3",
       "asyncpg>=0.30.0",           # Also added by Plan 02
       "pydantic>=2.0",             # Also added by Plan 02
       "pydantic-settings>=2.0",    # Also added by Plan 02
       "fastmcp>=2.0",              # NEW — MCP server framework
   ]
   ```
   Also add `pytest-asyncio` to the dev dependency group (needed for `@pytest.mark.asyncio` in Stage 6+):
   ```toml
   [dependency-groups]
   dev = [
       ...,
       "pytest-asyncio",
   ]
   ```
   Note: Duplicate deps with Plan 02 are fine — after rebase, dedup in the merge.

3. Create `src/neocortex/mcp_settings.py`:
   ```python
   from pydantic_settings import BaseSettings


   class MCPSettings(BaseSettings):
       """MCP server configuration. Loaded from env vars with NEOCORTEX_ prefix."""

       model_config = {"env_prefix": "NEOCORTEX_", "env_file": ".env", "env_file_encoding": "utf-8"}

       # Server
       server_name: str = "NeoCortex"
       server_host: str = "127.0.0.1"
       server_port: int = 8000
       transport: str = "http"  # "http" | "stdio"

       # Authentication — "none" | "dev_token" | "google_oauth"
       #  - none: no auth, all requests are anonymous
       #  - dev_token: static bearer token for testing (no browser flow needed)
       #  - google_oauth: full Google OAuth via FastMCP OAuthProxy
       auth_mode: str = "none"

       # Dev-token auth (used when auth_mode = "dev_token")
       dev_token: str = "dev-token-neocortex"  # Bearer token to accept
       dev_user_id: str = "dev-user"            # Identity returned for the dev token

       # Google OAuth (used when auth_mode = "google_oauth")
       google_client_id: str = ""
       google_client_secret: str = ""
       oauth_base_url: str = "http://localhost:8000"

       # Feature flags
       mock_db: bool = True  # Use in-memory mock until PG is wired
   ```
   This is separate from Plan 02's `PostgresConfig` (which uses `POSTGRES_` prefix). After rebase both coexist.

4. Create `src/neocortex/__main__.py`:
   ```python
   """Run the NeoCortex MCP server: python -m neocortex"""
   from neocortex.server import create_server
   from neocortex.mcp_settings import MCPSettings

   settings = MCPSettings()
   mcp = create_server(settings)

   if __name__ == "__main__":
       mcp.run(transport=settings.transport, host=settings.server_host, port=settings.server_port)
   ```

5. **Validate FastMCP imports** — after `uv sync`, verify that the import paths used in later stages actually exist. Run each of these; if any fails, fetch the relevant FastMCP doc URL from the reference table above using `WebFetch`, find the correct import, and update the affected stage in this plan before proceeding:
   ```bash
   uv run python -c "from fastmcp import FastMCP, Context; print('FastMCP core OK')"
   uv run python -c "from fastmcp import Client; print('Client OK')"
   ```
   The following imports are used in Stages 4–5 and may have changed in newer FastMCP versions. Test them now so failures surface early:
   ```bash
   uv run python -c "from fastmcp.server.auth import OAuthProxy; print('OAuthProxy OK')"
   ```
   If `OAuthProxy` import fails, search for the correct path: `uv run python -c "import fastmcp; import pkgutil; [print(m.name) for m in pkgutil.walk_packages(fastmcp.__path__, 'fastmcp.')]"` and grep for `OAuthProxy` or `OAuth`. Update Stage 4 with the correct path.

**Verification**:
- [ ] `uv sync` succeeds (fastmcp resolves)
- [ ] All directories and `__init__.py` files exist
- [ ] `uv run python -c "from neocortex.mcp_settings import MCPSettings; print(MCPSettings().auth_mode)"` prints `none`
- [ ] FastMCP import validation (step 5) passes — or plan is updated with correct paths
- [ ] `uv run ruff check src/neocortex` passes

**Commit**: `feat(mcp): add MCP package extensions, settings, and directory structure`

---

## Stage 2: FastMCP server with 3 tool stubs

**Goal**: Create the FastMCP server factory and register three MCP tool stubs returning mock data.
**Dependencies**: Stage 1
**Docs**: [Server (`FastMCP` class)](https://gofastmcp.com/servers/fastmcp) — constructor params, `custom_route`; [Tools](https://gofastmcp.com/servers/tools) — `@mcp.tool`, annotations; [Running](https://gofastmcp.com/deployment/running) — `mcp.run()`, transports

**Steps**:

1. Create `src/neocortex/server.py`:
   ```python
   from fastmcp import FastMCP
   from starlette.responses import JSONResponse
   from neocortex.mcp_settings import MCPSettings


   def create_server(settings: MCPSettings | None = None) -> FastMCP:
       settings = settings or MCPSettings()

       mcp = FastMCP(
           name=settings.server_name,
           instructions=(
               "NeoCortex is an agent memory system. Use 'remember' to store knowledge, "
               "'recall' to retrieve it, and 'discover' to explore what types of knowledge exist."
           ),
       )

       # Register tools
       from neocortex.tools import register_tools
       register_tools(mcp)

       # Health check
       @mcp.custom_route("/health", methods=["GET"])
       async def health_check(request):
           return JSONResponse({"status": "ok", "version": "0.1.0"})

       return mcp
   ```

2. Create `src/neocortex/tools/__init__.py`:
   ```python
   from neocortex.tools.remember import remember
   from neocortex.tools.recall import recall
   from neocortex.tools.discover import discover


   def register_tools(mcp):
       mcp.tool(remember)
       mcp.tool(recall)
       mcp.tool(discover)
   ```

3. Create `src/neocortex/tools/remember.py`:
   ```python
   async def remember(text: str, context: str | None = None) -> dict:
       """Store a memory. Describe what you want to remember in natural language.
       The system persists it as an episode and asynchronously extracts
       structured facts into the knowledge graph.

       Args:
           text: The content to remember, in natural language.
           context: Optional context about where/why this memory is being stored.
       """
       return {
           "status": "stored",
           "episode_id": -1,
           "message": "Memory stored (mock mode — no database connected).",
       }
   ```

4. Create `src/neocortex/tools/recall.py`:
   ```python
   async def recall(query: str, limit: int = 10) -> dict:
       """Recall memories related to a query. Uses hybrid search combining
       semantic similarity, full-text search, and graph traversal.

       Args:
           query: What you want to know, in natural language.
           limit: Maximum number of results to return (1-100).
       """
       return {
           "results": [],
           "total": 0,
           "query": query,
           "message": "No memories found (mock mode — no database connected).",
       }
   ```

5. Create `src/neocortex/tools/discover.py`:
   ```python
   async def discover(query: str | None = None) -> dict:
       """Discover what types of knowledge are stored. Returns the ontology —
       entity types, relationship types, and statistics. Optionally filtered.

       Args:
           query: Optional filter to narrow the ontology exploration.
       """
       return {
           "node_types": [],
           "edge_types": [],
           "stats": {"total_nodes": 0, "total_edges": 0, "total_episodes": 0},
           "message": "Empty knowledge graph (mock mode — no database connected).",
       }
   ```

**Verification**:
- [ ] `uv run python -c "from neocortex.server import create_server; s = create_server(); print(s.name)"` prints `NeoCortex`
- [ ] Server smoke test (non-interactive — do NOT start the server interactively):
  ```bash
  NEOCORTEX_MOCK_DB=true uv run python -m neocortex &
  SERVER_PID=$!
  sleep 2
  curl -sf http://localhost:8000/health && echo "Health OK" || echo "Health FAILED"
  kill $SERVER_PID 2>/dev/null
  wait $SERVER_PID 2>/dev/null
  ```
- [ ] `uv run ruff check src/neocortex` passes

**Commit**: `feat(mcp): add FastMCP server with remember/recall/discover tool stubs`

---

## Stage 3: Tool I/O schemas

**Goal**: Define Pydantic models for MCP tool inputs and outputs. These are MCP-layer models — distinct from Plan 02's `models.py` which defines graph entities for the storage layer.
**Dependencies**: Stage 2
**Docs**: [Tools — Structured Output](https://gofastmcp.com/servers/tools) — Pydantic models as return types become `structuredContent` automatically

**Steps**:

1. Create `src/neocortex/schemas/memory.py`:
   ```python
   from pydantic import BaseModel, Field


   # --- Tool Outputs ---

   class RememberResult(BaseModel):
       status: str
       episode_id: int
       message: str

   class RecallItem(BaseModel):
       node_id: int
       name: str
       content: str
       node_type: str
       score: float = Field(..., description="Hybrid relevance score")
       source: str | None = None

   class RecallResult(BaseModel):
       results: list[RecallItem]
       total: int
       query: str

   class TypeInfo(BaseModel):
       id: int
       name: str
       description: str | None = None
       count: int = 0

   class GraphStats(BaseModel):
       total_nodes: int
       total_edges: int
       total_episodes: int

   class DiscoverResult(BaseModel):
       node_types: list[TypeInfo]
       edge_types: list[TypeInfo]
       stats: GraphStats
   ```

2. Update `src/neocortex/schemas/__init__.py`:
   ```python
   from neocortex.schemas.memory import (
       RememberResult, RecallItem, RecallResult,
       TypeInfo, GraphStats, DiscoverResult,
   )
   ```

3. Update tool functions to return typed Pydantic models (FastMCP auto-serializes structured output):
   - `remember.py` → return `RememberResult(...)`
   - `recall.py` → return `RecallResult(...)`
   - `discover.py` → return `DiscoverResult(...)`

**Verification**:
- [ ] `uv run python -c "from neocortex.schemas import RememberResult, RecallResult, DiscoverResult; print('OK')"`
- [ ] `uv run python -c "from neocortex.server import create_server; print('OK')"` (tools still wire up)
- [ ] `uv run ruff check src/neocortex` passes

**Commit**: `feat(mcp): add Pydantic schemas for MCP tool inputs and outputs`

---

## Stage 4: Auth layer (dev-token + Google OAuth)

**Goal**: Create a pluggable auth layer with three modes: `none` (anonymous), `dev_token` (static bearer token for testing/agent validation), and `google_oauth` (full Google OAuth via FastMCP OAuthProxy). The `dev_token` mode is critical for hackathon work — it lets agents and curl test the full auth→identity→RLS pipeline without any browser flow.
**Dependencies**: Stage 1
**Docs**: [Auth](https://gofastmcp.com/servers/auth) — `OAuthProxy`, `GoogleProvider`, `CurrentAccessToken`, token claims; [Dependencies](https://gofastmcp.com/servers/dependencies) — `Depends()`, `CurrentAccessToken()`, `TokenClaim()`

**API stability note**: FastMCP's auth API evolves quickly. If any import path below fails at implementation time:
1. Fetch the relevant doc URL from the FastMCP Documentation Reference table (top of this plan) using `WebFetch`
2. Search the installed package: `uv run python -c "import fastmcp; import pkgutil; [print(m.name) for m in pkgutil.walk_packages(fastmcp.__path__, 'fastmcp.')]"` and grep for the class name
3. Update this plan with the correct import path before proceeding

**Steps**:

1. Create `src/neocortex/auth/dev.py` — lightweight dev-token auth that bypasses OAuth entirely:
   ```python
   from starlette.authentication import AuthCredentials, SimpleUser, AuthenticationBackend
   from starlette.requests import HTTPConnection
   from neocortex.mcp_settings import MCPSettings


   class DevTokenAuth(AuthenticationBackend):
       """Static bearer-token auth for development and agent testing.

       Accepts a single hardcoded token from settings and maps it to a
       configurable user identity. No browser redirect, no external IdP.

       Usage:
           curl -H "Authorization: Bearer dev-token-neocortex" http://localhost:8000/mcp
       """

       def __init__(self, settings: MCPSettings):
           self._token = settings.dev_token
           self._user_id = settings.dev_user_id

       async def authenticate(self, conn: HTTPConnection):
           auth = conn.headers.get("Authorization", "")
           if auth == f"Bearer {self._token}":
               return AuthCredentials(["authenticated"]), SimpleUser(self._user_id)
           return None
   ```
   NOTE: The exact integration point with FastMCP's auth system may differ from raw Starlette middleware. At implementation time, check how FastMCP's `auth` parameter accepts custom backends. If FastMCP expects its own auth type rather than a Starlette `AuthenticationBackend`, adapt this class accordingly — the key behavior (accept a static token, return a user identity) stays the same.

2. Create `src/neocortex/auth/google.py`:
   ```python
   from fastmcp.server.auth import OAuthProxy
   from neocortex.mcp_settings import MCPSettings


   def create_google_auth(settings: MCPSettings) -> OAuthProxy:
       """Create a Google OAuthProxy for FastMCP.

       OAuthProxy wraps Google's non-DCR OAuth flow into a DCR-compliant
       interface that MCP clients expect. Requires a pre-registered Google
       OAuth client ID and secret (from Google Cloud Console).
       """
       return OAuthProxy(
           issuer_url="https://accounts.google.com",
           client_id=settings.google_client_id,
           client_secret=settings.google_client_secret,
           base_url=settings.oauth_base_url,
       )
   ```
   NOTE: If `OAuthProxy` import fails, check for `GoogleProvider` under `fastmcp.server.auth.providers.google`. See the API stability note above.

3. Create `src/neocortex/auth/__init__.py`:
   ```python
   from neocortex.mcp_settings import MCPSettings


   def create_auth(settings: MCPSettings):
       """Create auth provider based on settings.auth_mode.

       Returns:
           None             — auth_mode == "none"
           DevTokenAuth     — auth_mode == "dev_token"
           OAuthProxy       — auth_mode == "google_oauth"
       """
       if settings.auth_mode == "none":
           return None
       elif settings.auth_mode == "dev_token":
           from neocortex.auth.dev import DevTokenAuth
           return DevTokenAuth(settings)
       elif settings.auth_mode == "google_oauth":
           from neocortex.auth.google import create_google_auth
           return create_google_auth(settings)
       else:
           raise ValueError(f"Unknown auth_mode: {settings.auth_mode!r}. Use 'none', 'dev_token', or 'google_oauth'.")
   ```

4. Create `src/neocortex/auth/dependencies.py`:
   ```python
   from neocortex.mcp_settings import MCPSettings


   def get_agent_id_from_context(ctx) -> str:
       """Extract agent identity from request context.

       Behavior depends on auth_mode:
         - none: returns "anonymous"
         - dev_token: returns the configured dev_user_id
         - google_oauth: extracts 'sub' claim from the OAuth token

       The exact mechanism for accessing the authenticated user depends on
       FastMCP's dependency injection. At implementation time, check whether
       FastMCP provides CurrentAccessToken(), ctx.user, or another pattern.
       Adapt this function accordingly.
       """
       settings = ctx.lifespan_context.get("settings")
       if settings and settings.auth_mode == "none":
           return "anonymous"
       # Try to get user from context — adapt based on actual FastMCP API
       user = getattr(ctx, "user", None)
       if user is not None:
           return str(user)
       return "anonymous"
   ```

5. Update `src/neocortex/server.py` to wire auth into the FastMCP constructor:
   ```python
   from neocortex.auth import create_auth

   def create_server(settings: MCPSettings | None = None) -> FastMCP:
       settings = settings or MCPSettings()
       auth = create_auth(settings)
       mcp = FastMCP(
           name=settings.server_name,
           auth=auth,
           instructions=...,
       )
       ...
   ```

**Verification** (all non-interactive — do NOT start the server with Ctrl+C):
- [ ] `uv run python -c "from neocortex.auth import create_auth; from neocortex.mcp_settings import MCPSettings; print(create_auth(MCPSettings()))"` prints `None` (auth_mode=none by default)
- [ ] `uv run python -c "from neocortex.auth import create_auth; from neocortex.mcp_settings import MCPSettings; a = create_auth(MCPSettings(auth_mode='dev_token')); print(type(a).__name__)"` prints `DevTokenAuth`
- [ ] `uv run python -c "from neocortex.auth.dependencies import get_agent_id_from_context; print('OK')"`
- [ ] Server smoke test with dev-token auth:
  ```bash
  NEOCORTEX_AUTH_MODE=dev_token NEOCORTEX_MOCK_DB=true uv run python -m neocortex &
  SERVER_PID=$!
  sleep 2
  curl -sf http://localhost:8000/health && echo "Health OK" || echo "Health FAILED"
  kill $SERVER_PID 2>/dev/null
  wait $SERVER_PID 2>/dev/null
  ```
- [ ] `uv run ruff check src/neocortex` passes

**Commit**: `feat(mcp): add pluggable auth layer with dev-token and Google OAuth modes`

---

## Stage 5: In-memory mock repository & role mapping

**Goal**: Create a `MemoryRepository` protocol, an `InMemoryRepository` implementation, and the OAuth→PG role mapping function (pure string logic, no PG dependency). This lets the MCP tools be exercised end-to-end without PostgreSQL. After rebase, the real `GraphService` from Plan 02 will implement the protocol.
**Dependencies**: Stage 3
**Docs**: [Context — Lifespan](https://gofastmcp.com/servers/context) — `@lifespan`, `lifespan_context`, composing lifespans; [Dependencies](https://gofastmcp.com/servers/dependencies) — `CurrentContext()`, injecting into tools

**Steps**:

1. Create `src/neocortex/db/protocol.py` — the repository interface:
   ```python
   from typing import Protocol
   from neocortex.schemas.memory import RecallItem, TypeInfo, GraphStats


   class MemoryRepository(Protocol):
       """Abstract interface for the NeoCortex storage layer.

       Implementations:
         - InMemoryRepository: for testing and mock mode
         - GraphServiceAdapter: wraps Plan 02's GraphService (built in Stage 8)
       """

       async def store_episode(
           self, agent_id: str, content: str, context: str | None = None, source_type: str = "mcp"
       ) -> int:
           """Store a raw episode. Returns the episode ID."""
           ...

       async def recall(self, query: str, agent_id: str, limit: int = 10) -> list[RecallItem]:
           """Hybrid search: semantic + lexical + graph. Returns ranked results."""
           ...

       async def get_node_types(self) -> list[TypeInfo]:
           ...

       async def get_edge_types(self) -> list[TypeInfo]:
           ...

       async def get_stats(self) -> GraphStats:
           ...
   ```

2. Create `src/neocortex/db/mock.py` — in-memory implementation:
   ```python
   from neocortex.schemas.memory import RecallItem, TypeInfo, GraphStats


   class InMemoryRepository:
       """Mock repository for testing. Stores episodes in a list,
       supports basic substring matching for recall."""

       def __init__(self):
           self._episodes: list[dict] = []
           self._next_id = 1

       async def store_episode(
           self, agent_id: str, content: str, context: str | None = None, source_type: str = "mcp"
       ) -> int:
           eid = self._next_id
           self._next_id += 1
           self._episodes.append({
               "id": eid, "agent_id": agent_id, "content": content,
               "context": context, "source_type": source_type,
           })
           return eid

       async def recall(self, query: str, agent_id: str, limit: int = 10) -> list[RecallItem]:
           query_lower = query.lower()
           matches = []
           for ep in self._episodes:
               if ep["agent_id"] == agent_id and query_lower in ep["content"].lower():
                   matches.append(RecallItem(
                       node_id=ep["id"], name=f"Episode #{ep['id']}",
                       content=ep["content"], node_type="Episode",
                       score=1.0, source=ep["source_type"],
                   ))
           return matches[:limit]

       async def get_node_types(self) -> list[TypeInfo]:
           return []

       async def get_edge_types(self) -> list[TypeInfo]:
           return []

       async def get_stats(self) -> GraphStats:
           return GraphStats(total_nodes=0, total_edges=0, total_episodes=len(self._episodes))
   ```

3. Create `src/neocortex/db/roles.py` — OAuth-to-PG role name mapping (pure string logic, no PG dependency):
   ```python
   import re

   # PG identifiers max 63 chars; prefix is 17 chars → 46 chars for sanitized sub
   _MAX_SUB_LENGTH = 46
   _SAFE_CHARS = re.compile(r"[^a-z0-9_]")


   def oauth_sub_to_pg_role(oauth_sub: str) -> str:
       """Map an OAuth 'sub' claim to a PostgreSQL role name.

       Convention: neocortex_agent_{sanitized_sub}
       Sanitization: lowercase, replace non-alphanumeric with _, truncate.
       """
       sanitized = _SAFE_CHARS.sub("_", oauth_sub.lower())[:_MAX_SUB_LENGTH]
       return f"neocortex_agent_{sanitized}"
   ```
   NOTE: This is moved here from Stage 9 because it's a pure function with no PG dependency, enabling tests in Stage 6.

4. Add a lifespan to `src/neocortex/server.py` that initializes the repository. **Important**: define the lifespan inside `create_server` so it captures `settings` from the enclosing scope (do NOT re-instantiate `MCPSettings()` inside the lifespan):
   ```python
   from contextlib import asynccontextmanager

   def create_server(settings: MCPSettings | None = None) -> FastMCP:
       settings = settings or MCPSettings()
       auth = create_auth(settings)

       @asynccontextmanager
       async def app_lifespan(server):
           # settings is captured from the enclosing create_server() scope
           from neocortex.db.mock import InMemoryRepository
           repo = InMemoryRepository()
           yield {"repo": repo, "settings": settings}

       mcp = FastMCP(
           name=settings.server_name,
           auth=auth,
           instructions=...,
           lifespan=app_lifespan,
       )
       ...
   ```
   NOTE: The exact lifespan API may differ. If FastMCP expects `@lifespan` decorator from `fastmcp.server.lifespan`, use that instead. If the import fails, check FastMCP docs (see reference table) and search for `lifespan` in the installed package. The key requirement is that `settings` flows from `create_server` into the lifespan — do not create a new `MCPSettings()` inside it.

5. Update all three tool functions to use `Context` to access the repository:
   ```python
   from fastmcp import Context

   async def remember(
       text: str, context: str | None = None,
       ctx: Context = ...,  # Use CurrentContext() or whatever FastMCP provides
   ) -> RememberResult:
       repo = ctx.lifespan_context["repo"]
       settings = ctx.lifespan_context["settings"]
       # Derive agent_id from auth context
       from neocortex.auth.dependencies import get_agent_id_from_context
       agent_id = get_agent_id_from_context(ctx)
       episode_id = await repo.store_episode(agent_id=agent_id, content=text, context=context)
       return RememberResult(status="stored", episode_id=episode_id, message="Memory stored.")
   ```
   Apply the same pattern to `recall` and `discover`.

   NOTE: The exact way to inject `Context` into tool functions depends on FastMCP's dependency injection. Check if `CurrentContext()` is a valid default parameter, or if the `Context` type hint alone is sufficient. Consult [Dependencies](https://gofastmcp.com/servers/dependencies) if the approach above fails.

**Verification**:
- [ ] `uv run python -c "from neocortex.db.protocol import MemoryRepository; print('OK')"`
- [ ] `uv run python -c "from neocortex.db.mock import InMemoryRepository; print('OK')"`
- [ ] `uv run python -c "from neocortex.db.roles import oauth_sub_to_pg_role; print(oauth_sub_to_pg_role('user@example.com'))"` prints `neocortex_agent_user_example_com`
- [ ] Server smoke test (non-interactive):
  ```bash
  NEOCORTEX_MOCK_DB=true NEOCORTEX_AUTH_MODE=none uv run python -m neocortex &
  SERVER_PID=$!
  sleep 2
  curl -sf http://localhost:8000/health && echo "Health OK" || echo "Health FAILED"
  kill $SERVER_PID 2>/dev/null
  wait $SERVER_PID 2>/dev/null
  ```
- [ ] `uv run ruff check src/neocortex` passes

**Commit**: `feat(mcp): add MemoryRepository protocol, InMemoryRepository, role mapping, and wire tools via lifespan`

---

## Stage 6: MCP-layer tests

**Goal**: Add unit tests for the MCP server, tools, schemas, auth helpers, and mock repository. Tests go in `tests/mcp/` to avoid conflicts with Plan 02's tests in `tests/`.
**Dependencies**: Stage 5
**Docs**: [Client](https://gofastmcp.com/clients/client) — in-memory `Client` for testing tools without HTTP; pass a `FastMCP` instance directly

**Steps**:

1. Create test directory:
   ```
   tests/mcp/
   ├── __init__.py
   ├── conftest.py          # Shared fixtures (mock repo, test server)
   ├── test_tools.py        # Tool function tests via FastMCP Client
   ├── test_schemas.py      # Schema instantiation tests
   ├── test_mock_repo.py    # InMemoryRepository tests
   ├── test_roles.py        # OAuth→PG role mapping tests
   └── test_server.py       # Server creation tests
   ```

2. Create `tests/mcp/conftest.py`:
   ```python
   import pytest
   from neocortex.db.mock import InMemoryRepository
   from neocortex.server import create_server
   from neocortex.mcp_settings import MCPSettings

   @pytest.fixture
   def mock_repo():
       return InMemoryRepository()

   @pytest.fixture
   def test_settings():
       return MCPSettings(auth_mode="none", mock_db=True)

   @pytest.fixture
   def test_server(test_settings):
       return create_server(test_settings)
   ```

3. Create `tests/mcp/test_tools.py` — use FastMCP's in-memory `Client`:
   - Test `remember` stores an episode and returns `RememberResult` with status "stored"
   - Test `recall` with empty repo returns empty results
   - Test `discover` returns empty ontology and zero stats

4. Create `tests/mcp/test_mock_repo.py`:
   - Test `store_episode` returns incrementing IDs
   - Test `recall` finds episodes by substring, filtered by agent_id
   - Test `get_stats` reflects stored episodes count

5. Create `tests/mcp/test_roles.py` (tests `roles.py` created in Stage 5):
   - Test `oauth_sub_to_pg_role` with various inputs (email, UUID, special chars)
   - Test role name length truncation (max 63 chars for PG identifiers)
   - Test sanitization of unsafe characters

6. Create `tests/mcp/test_schemas.py`:
   - Smoke test instantiation of all schema models
   - Test serialization round-trip

7. Create `tests/mcp/test_server.py`:
   - Test `create_server` returns a FastMCP instance with correct name
   - Test server has 3 tools registered (remember, recall, discover)

**Verification**:
- [ ] `uv run pytest tests/mcp/ -v` — all tests pass
- [ ] `uv run ruff check tests/mcp` passes

**Commit**: `test(mcp): add unit tests for MCP tools, schemas, mock repo, and auth helpers`

---

## Stage 7: Rebase onto Plan 02

**Goal**: Wait for Plan 02 to be merged to `main`, then rebase the `mcp` branch to incorporate the PostgreSQL storage layer. Resolve any conflicts and re-verify.
**Dependencies**: Stages 1–6 DONE, Plan 02 merged to `main`

**Steps**:

1. **Check if Plan 02 has landed on main**:
   ```bash
   git fetch origin
   git log origin/main --oneline -10
   ```
   Look for Plan 02's commits (e.g., `feat(storage): add Docker Compose with PostgreSQL 16...`, `feat(neocortex): add package skeleton and PostgresService...`). If they are not present, mark this stage BLOCKED with note "Waiting for Plan 02 to merge to main" and stop.

2. **Rebase onto main**:
   ```bash
   git rebase origin/main
   ```

3. **Resolve conflicts** (expected in):
   - `pyproject.toml` — merge both dependency lists (keep Plan 02's deps + add `fastmcp>=2.0`)
   - `src/neocortex/__init__.py` — keep Plan 02's version (or merge trivially)
   - `.env.example` — merge both sets of env vars (POSTGRES_ + NEOCORTEX_)
   The MCP-specific files (`server.py`, `tools/`, `auth/`, `schemas/`, `db/`, `__main__.py`, `mcp_settings.py`) should have NO conflicts since Plan 02 doesn't create them.

4. **Fix imports post-rebase**: Verify that `src/neocortex/__init__.py` from Plan 02 doesn't break MCP module imports. If Plan 02's `__init__.py` has different content, ensure it's compatible.

5. **Re-run all tests**:
   ```bash
   uv sync
   uv run pytest tests/mcp/ -v
   ```
   Plan 02's integration tests (`tests/test_graph_*.py`) require Docker — only run them if Docker is up.

6. **Verify both module trees coexist**:
   ```bash
   uv run python -c "from neocortex.postgres_service import PostgresService; print('Plan 02 OK')"
   uv run python -c "from neocortex.server import create_server; print('Plan 03 OK')"
   uv run python -c "from neocortex.graph_service import GraphService; print('Plan 02 OK')"
   uv run python -c "from neocortex.mcp_settings import MCPSettings; print('Plan 03 OK')"
   ```

**Verification**:
- [ ] `git rebase origin/main` succeeds (with conflict resolution if needed)
- [ ] `uv sync` succeeds
- [ ] `uv run pytest tests/mcp/ -v` passes
- [ ] Both Plan 02 and Plan 03 imports work (see step 6)
- [ ] `uv run ruff check src/neocortex` passes

**Commit**: No new commit if rebase was clean. If conflicts were resolved, the rebase itself rewrites commits. If post-rebase fixups are needed, commit: `fix(mcp): resolve rebase conflicts with Plan 02 storage layer`

---

## Stage 8: PostgreSQL integration — wire tools to GraphService

**Goal**: Replace mock repository in MCP tools with a `GraphServiceAdapter` that wraps Plan 02's `GraphService` and `PostgresService`. Update lifespan to manage the real connection pool.
**Dependencies**: Stage 7
**Docs**: [Context — Lifespan](https://gofastmcp.com/servers/context) — composing lifespans with `|` pipe operator; [Running](https://gofastmcp.com/deployment/running) — ASGI app via `mcp.http_app()` for Docker

**Steps**:

1. Create `src/neocortex/db/adapter.py` — adapter implementing `MemoryRepository` using Plan 02's `GraphService`:
   ```python
   from neocortex.graph_service import GraphService
   from neocortex.schemas.memory import RecallItem, TypeInfo, GraphStats


   class GraphServiceAdapter:
       """Adapts Plan 02's GraphService to the MemoryRepository protocol."""

       def __init__(self, graph: GraphService):
           self._graph = graph

       async def store_episode(
           self, agent_id: str, content: str, context: str | None = None, source_type: str = "mcp"
       ) -> int:
           metadata = {"context": context} if context else {}
           episode = await self._graph.create_episode(
               agent_id=agent_id, content=content, source_type=source_type, metadata=metadata,
           )
           return episode.id

       async def recall(self, query: str, agent_id: str, limit: int = 10) -> list[RecallItem]:
           # Use text search as primary recall method
           hits = await self._graph.search_by_text(query, limit=limit)
           results = []
           for hit in hits:
               # Resolve node type name
               nt = await self._graph.get_node_type(hit["type_id"])
               results.append(RecallItem(
                   node_id=hit["id"],
                   name=hit["name"],
                   content=hit.get("content", ""),
                   node_type=nt.name if nt else "Unknown",
                   score=hit.get("rank", 0.0),
                   source=hit.get("source"),
               ))
           return results

       async def get_node_types(self) -> list[TypeInfo]:
           stats = await self._graph.get_ontology_stats()
           return [TypeInfo(id=0, name=t["type_name"], count=t["count"]) for t in stats["node_types"]]

       async def get_edge_types(self) -> list[TypeInfo]:
           stats = await self._graph.get_ontology_stats()
           return [TypeInfo(id=0, name=t["type_name"], count=t["count"]) for t in stats["edge_types"]]

       async def get_stats(self) -> GraphStats:
           stats = await self._graph.get_ontology_stats()
           return GraphStats(
               total_nodes=stats["total_nodes"],
               total_edges=stats["total_edges"],
               total_episodes=stats["total_episodes"],
           )
   ```

2. Update the lifespan in `src/neocortex/server.py` (inside `create_server`) to conditionally use real PG. **Important**: Keep the lifespan defined inside `create_server` as a closure capturing `settings` (established in Stage 5):
   ```python
   # Inside create_server():
   @asynccontextmanager
   async def app_lifespan(server):
       # settings captured from enclosing create_server() scope — NOT re-instantiated
       if settings.mock_db:
           from neocortex.db.mock import InMemoryRepository
           repo = InMemoryRepository()
           yield {"repo": repo, "settings": settings}
       else:
           from neocortex.config import PostgresConfig
           from neocortex.postgres_service import PostgresService
           from neocortex.graph_service import GraphService
           from neocortex.db.adapter import GraphServiceAdapter

           pg = PostgresService(PostgresConfig())
           await pg.connect()
           try:
               graph = GraphService(pg)
               repo = GraphServiceAdapter(graph)
               yield {"repo": repo, "pg": pg, "graph": graph, "settings": settings}
           finally:
               await pg.disconnect()
   ```

3. Add the MCP server as a service in `docker-compose.yml` (extending Plan 02's file):
   ```yaml
   # Add to existing services section:
     neocortex-mcp:
       build:
         context: .
         dockerfile: docker/mcp/Dockerfile
       ports:
         - "8000:8000"
       environment:
         NEOCORTEX_TRANSPORT: http
         NEOCORTEX_SERVER_HOST: "0.0.0.0"
         NEOCORTEX_MOCK_DB: "false"
         NEOCORTEX_AUTH_MODE: "none"
         POSTGRES_HOST: neocortex-postgres
         POSTGRES_PORT: "5432"
         POSTGRES_USER: neocortex
         POSTGRES_PASSWORD: neocortex
         POSTGRES_DATABASE: neocortex
       depends_on:
         postgres:
           condition: service_healthy
   ```

4. Create `docker/mcp/Dockerfile`:
   ```dockerfile
   FROM python:3.13-slim
   WORKDIR /app
   COPY pyproject.toml uv.lock ./
   RUN pip install uv && uv sync --frozen
   COPY src/ src/
   EXPOSE 8000
   CMD ["uv", "run", "python", "-m", "neocortex"]
   ```

**Verification** (local — always run):
- [ ] `uv run python -c "from neocortex.db.adapter import GraphServiceAdapter; print('OK')"`
- [ ] `uv run pytest tests/mcp/ -v` still passes (mock mode tests)
- [ ] `uv run ruff check src/neocortex` passes

**Verification** (requires Docker — skip if Docker is not running):
- [ ] Check Docker is available: `docker compose ps --filter status=running | grep postgres || echo "SKIP: Docker not running — skip Docker verification"`
- [ ] `docker compose up -d` starts both postgres and neocortex-mcp
- [ ] `curl -sf http://localhost:8000/health` returns OK
- [ ] Server connects to PG (non-interactive):
  ```bash
  NEOCORTEX_MOCK_DB=false NEOCORTEX_AUTH_MODE=none uv run python -m neocortex &
  SERVER_PID=$!
  sleep 3
  curl -sf http://localhost:8000/health && echo "PG mode OK" || echo "PG mode FAILED"
  kill $SERVER_PID 2>/dev/null
  wait $SERVER_PID 2>/dev/null
  ```

**Commit**: `feat(mcp): wire tools to GraphService via adapter, add Docker service`

---

## Stage 9: RLS policies & role-based access

**Goal**: Add PostgreSQL Row-Level Security policies so that each OAuth-authenticated agent only sees its own data. Create the PG role provisioning flow and scoped connection helpers. Ontology tables (`node_type`, `edge_type`) remain shared — all agents can read and extend the ontology.
**Dependencies**: Stage 8

**Steps**:

1. Create `migrations/init/005_rls_roles.sql` — RLS setup applied on first Docker init:
   ```sql
   -- =============================================================
   -- Row-Level Security & Role-Based Access
   -- =============================================================

   -- Base group role for all MCP agents (no login — used via SET ROLE)
   DO $$
   BEGIN
       IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'neocortex_agent') THEN
           CREATE ROLE neocortex_agent NOLOGIN;
       END IF;
   END
   $$;

   -- Table-level grants for agent group role
   GRANT USAGE ON SCHEMA public TO neocortex_agent;
   GRANT SELECT, INSERT, UPDATE, DELETE ON node, edge, episode TO neocortex_agent;
   GRANT SELECT, INSERT ON node_type, edge_type TO neocortex_agent;
   GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO neocortex_agent;

   -- Add owner_role column to data tables (tracks which PG role owns the row)
   -- DEFAULT current_user ensures rows created via SET ROLE get the agent's role
   ALTER TABLE node ADD COLUMN IF NOT EXISTS owner_role TEXT DEFAULT current_user;
   ALTER TABLE edge ADD COLUMN IF NOT EXISTS owner_role TEXT DEFAULT current_user;
   ALTER TABLE episode ADD COLUMN IF NOT EXISTS owner_role TEXT DEFAULT current_user;

   -- Index for RLS filtering
   CREATE INDEX IF NOT EXISTS idx_node_owner ON node (owner_role);
   CREATE INDEX IF NOT EXISTS idx_edge_owner ON edge (owner_role);
   CREATE INDEX IF NOT EXISTS idx_episode_owner ON episode (owner_role);

   -- Enable RLS on data tables (superuser and table owner bypass RLS)
   ALTER TABLE node ENABLE ROW LEVEL SECURITY;
   ALTER TABLE edge ENABLE ROW LEVEL SECURITY;
   ALTER TABLE episode ENABLE ROW LEVEL SECURITY;

   -- Force RLS even for table owner (the neocortex admin user)
   -- This ensures the admin connection pool also respects RLS when SET ROLE is active
   ALTER TABLE node FORCE ROW LEVEL SECURITY;
   ALTER TABLE edge FORCE ROW LEVEL SECURITY;
   ALTER TABLE episode FORCE ROW LEVEL SECURITY;

   -- ── Node policies ───────────────────────────────────────────
   -- Agents see: own rows + shared rows (owner_role IS NULL)
   CREATE POLICY node_select_policy ON node FOR SELECT
       USING (owner_role = current_user OR owner_role IS NULL);
   CREATE POLICY node_insert_policy ON node FOR INSERT
       WITH CHECK (owner_role = current_user);
   CREATE POLICY node_update_policy ON node FOR UPDATE
       USING (owner_role = current_user)
       WITH CHECK (owner_role = current_user);
   CREATE POLICY node_delete_policy ON node FOR DELETE
       USING (owner_role = current_user);

   -- ── Edge policies ───────────────────────────────────────────
   -- Agents see: own edges + shared edges (owner_role IS NULL)
   CREATE POLICY edge_select_policy ON edge FOR SELECT
       USING (owner_role = current_user OR owner_role IS NULL);
   CREATE POLICY edge_insert_policy ON edge FOR INSERT
       WITH CHECK (owner_role = current_user);
   CREATE POLICY edge_update_policy ON edge FOR UPDATE
       USING (owner_role = current_user)
       WITH CHECK (owner_role = current_user);
   CREATE POLICY edge_delete_policy ON edge FOR DELETE
       USING (owner_role = current_user);

   -- ── Episode policies ────────────────────────────────────────
   -- Episodes are strictly private — agents only see their own
   CREATE POLICY episode_select_policy ON episode FOR SELECT
       USING (owner_role = current_user);
   CREATE POLICY episode_insert_policy ON episode FOR INSERT
       WITH CHECK (owner_role = current_user);
   CREATE POLICY episode_delete_policy ON episode FOR DELETE
       USING (owner_role = current_user);

   -- ── No RLS on ontology tables ───────────────────────────────
   -- node_type and edge_type are shared: all agents read/write freely
   -- (covered by table-level GRANT above, no row-level restriction)
   ```

2. Update `src/neocortex/db/roles.py` — add PG role provisioning function (the `oauth_sub_to_pg_role` pure function was already created in Stage 5):
   ```python
   # Add to existing roles.py (which already has oauth_sub_to_pg_role):
   import asyncpg
   from loguru import logger


   async def ensure_pg_role(pool: asyncpg.Pool, role_name: str) -> None:
       """Create the PG role if it doesn't exist. Grants neocortex_agent membership."""
       async with pool.acquire() as conn:
           exists = await conn.fetchval(
               "SELECT 1 FROM pg_roles WHERE rolname = $1", role_name
           )
           if not exists:
               # Use quoted identifier to handle any special chars
               await conn.execute(f'CREATE ROLE "{role_name}" NOLOGIN INHERIT IN ROLE neocortex_agent')
               logger.info("Created PG role: {}", role_name)
   ```

3. Create `src/neocortex/db/scoped.py` — scoped connection with role switching:
   ```python
   from contextlib import asynccontextmanager
   import asyncpg
   from neocortex.db.roles import oauth_sub_to_pg_role, ensure_pg_role


   @asynccontextmanager
   async def scoped_connection(pool: asyncpg.Pool, oauth_sub: str):
       """Acquire a connection, ensure the PG role exists, and SET LOCAL ROLE.

       All queries within this context run as the agent's PG role,
       meaning RLS policies filter data to that agent's rows only.
       After the transaction, the role resets automatically (SET LOCAL is
       transaction-scoped).
       """
       role_name = oauth_sub_to_pg_role(oauth_sub)
       await ensure_pg_role(pool, role_name)
       async with pool.acquire() as conn:
           async with conn.transaction():
               await conn.execute(f'SET LOCAL ROLE "{role_name}"')
               yield conn
   ```

4. Update `src/neocortex/db/adapter.py` to support role-scoped queries. Add an optional `pool` and `agent_id` so that when auth is active, queries go through a scoped connection:
   ```python
   # In GraphServiceAdapter.__init__:
   def __init__(self, graph: GraphService, pool: asyncpg.Pool | None = None):
       self._graph = graph
       self._pool = pool

   # In store_episode — when pool is available, use scoped_connection:
   async def store_episode(self, agent_id: str, content: str, ...):
       if self._pool:
           from neocortex.db.scoped import scoped_connection
           async with scoped_connection(self._pool, agent_id) as conn:
               # Execute INSERT via the scoped connection (RLS applies)
               ...
       else:
           # Fallback: use GraphService directly (no RLS)
           episode = await self._graph.create_episode(agent_id=agent_id, ...)
           return episode.id
   ```
   NOTE: The exact implementation depends on how `GraphService` and `PostgresService` handle connection sharing. At implementation time, decide whether to:
   - (A) Pass the scoped connection into `GraphService` methods
   - (B) Create a `ScopedGraphService` that wraps `GraphService` with a pinned connection
   - (C) Have the adapter execute raw SQL on the scoped connection
   Option (C) is simplest for the hackathon; option (B) is cleanest long-term.

5. Update the server lifespan to pass `pool` to the adapter:
   ```python
   repo = GraphServiceAdapter(graph, pool=pg.pool)
   ```

6. Create `tests/mcp/test_rls.py` — integration tests (require Docker):
   ```python
   """RLS integration tests. Require Docker PostgreSQL to be running.
   Run with: uv run pytest tests/mcp/test_rls.py -v
   """
   import pytest

   @pytest.mark.asyncio
   async def test_agent_sees_only_own_episodes(pg_pool):
       """Two agents store episodes; each only sees their own."""
       ...

   @pytest.mark.asyncio
   async def test_agent_sees_shared_nodes(pg_pool):
       """Nodes with owner_role=NULL are visible to all agents."""
       ...

   @pytest.mark.asyncio
   async def test_agent_cannot_modify_other_agent_nodes(pg_pool):
       """Agent A cannot UPDATE or DELETE agent B's nodes."""
       ...

   @pytest.mark.asyncio
   async def test_ontology_tables_are_shared(pg_pool):
       """All agents can read and insert into node_type / edge_type."""
       ...
   ```

7. Update `.env.example` with the full set of variables (merge Plan 02's POSTGRES_ vars + Plan 03's NEOCORTEX_ vars):
   ```env
   # PostgreSQL (Plan 02)
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   POSTGRES_USER=neocortex
   POSTGRES_PASSWORD=neocortex
   POSTGRES_DATABASE=neocortex

   # MCP Server (Plan 03)
   NEOCORTEX_TRANSPORT=http
   NEOCORTEX_SERVER_HOST=127.0.0.1
   NEOCORTEX_SERVER_PORT=8000
   NEOCORTEX_AUTH_MODE=none              # "none" | "dev_token" | "google_oauth"
   NEOCORTEX_MOCK_DB=false

   # Dev-token auth (used when NEOCORTEX_AUTH_MODE=dev_token)
   NEOCORTEX_DEV_TOKEN=dev-token-neocortex
   NEOCORTEX_DEV_USER_ID=dev-user

   # Google OAuth (used when NEOCORTEX_AUTH_MODE=google_oauth)
   NEOCORTEX_GOOGLE_CLIENT_ID=
   NEOCORTEX_GOOGLE_CLIENT_SECRET=
   NEOCORTEX_OAUTH_BASE_URL=http://localhost:8000
   ```

**Verification** (local — always run):
- [ ] `uv run python -c "from neocortex.db.roles import oauth_sub_to_pg_role; print(oauth_sub_to_pg_role('user@example.com'))"` prints `neocortex_agent_user_example_com`
- [ ] `uv run pytest tests/mcp/ -v` — all MCP tests pass
- [ ] `uv run ruff check src/neocortex tests/mcp` passes

**Verification** (requires Docker — skip if Docker is not running):
- [ ] Check Docker: `docker compose ps --filter status=running | grep postgres || echo "SKIP: Docker not running"`
- [ ] `docker compose down -v && docker compose up -d` — fresh start with RLS migration applied
- [ ] `docker compose exec postgres psql -U neocortex -d neocortex -c "SELECT polname FROM pg_policy;"` shows all RLS policies
- [ ] `docker compose exec postgres psql -U neocortex -d neocortex -c "SELECT rolname FROM pg_roles WHERE rolname = 'neocortex_agent';"` returns the group role
- [ ] `uv run pytest tests/mcp/test_rls.py -v` — all RLS tests pass

**Commit**: `feat(mcp): add RLS policies, PG role provisioning, and scoped connections`

---

## Stage 10: Push to remote, create PR, and merge to main

**Goal**: Push the `mcp` branch to the remote, create a pull request against `main`, and merge it so that all Plan 03 changes land on the main branch.
**Dependencies**: All previous stages DONE (Stages 1–6 minimum; Stages 7–9 if Plan 02 has landed)

**Steps**:

1. **Ensure all work is committed** — there should be no uncommitted changes:
   ```bash
   git status
   ```
   If there are uncommitted changes, commit them first with an appropriate message.

2. **Push the `mcp` branch to remote**:
   ```bash
   git push -u origin mcp
   ```

3. **Create a pull request** using `gh` CLI:
   ```bash
   gh pr create --base main --head mcp \
     --title "feat(mcp): MCP server scaffold with FastMCP, auth, and PG integration" \
     --body "$(cat <<'EOF'
   ## Summary

   Scaffolds the NeoCortex MCP server layer (Plan 03) on top of the PostgreSQL storage layer (Plan 02):

   - **FastMCP server** with 3 MCP tools: `remember`, `recall`, `discover`
   - **Pluggable auth**: `none` (anonymous), `dev_token` (static bearer for testing), `google_oauth` (full OAuth flow)
   - **Pydantic schemas** for tool I/O with structured MCP output
   - **MemoryRepository protocol** with `InMemoryRepository` (mock) and `GraphServiceAdapter` (real PG)
   - **PostgreSQL RLS policies** — per-agent data isolation via `SET LOCAL ROLE`, shared ontology tables
   - **Role provisioning** — OAuth sub → PG role mapping with auto-creation
   - **Docker service** for the MCP server alongside PostgreSQL
   - **Test suite** in `tests/mcp/` covering tools, schemas, mock repo, roles, and RLS

   ## Test plan

   - [ ] `uv run pytest tests/mcp/ -v` — all MCP unit tests pass
   - [ ] `uv run ruff check src/neocortex tests/mcp` — lint clean
   - [ ] Server starts in mock mode: `NEOCORTEX_MOCK_DB=true NEOCORTEX_AUTH_MODE=none uv run python -m neocortex`
   - [ ] Server starts with dev-token auth: `NEOCORTEX_AUTH_MODE=dev_token uv run python -m neocortex`
   - [ ] Health check: `curl http://localhost:8000/health`
   - [ ] (If Docker available) `docker compose up -d` starts PG + MCP, RLS tests pass

   🤖 Generated with [Claude Code](https://claude.com/claude-code)
   EOF
   )"
   ```

4. **Wait for any CI checks** (if configured). Check PR status:
   ```bash
   gh pr checks --watch
   ```
   If there are no CI checks configured, proceed directly to merge.

5. **Merge the PR** into `main`:
   ```bash
   gh pr merge --squash --delete-branch
   ```
   Use `--squash` to keep `main` history clean. Use `--delete-branch` to clean up the `mcp` branch after merge.

   NOTE: If the repository requires reviews or has branch protection rules that prevent direct merge, mark this stage BLOCKED with a note explaining the blocker. Do not bypass branch protection.

6. **Verify the merge landed on main**:
   ```bash
   git checkout main
   git pull origin main
   git log --oneline -5
   ```
   Confirm the squashed commit appears in `main`.

**Verification**:
- [ ] `gh pr view --json state --jq .state` returns `MERGED`
- [ ] `git log origin/main --oneline -3` shows the merged PR commit
- [ ] `mcp` branch is deleted on remote: `git ls-remote --heads origin mcp` returns empty

**Commit**: No new commit — this stage creates and merges a PR from existing commits.

---

## Overall Verification

After all stages are complete:

1. **Clean Docker start**: `docker compose down -v && docker compose up -d`
2. **Full test suite**: `uv run pytest tests/ -v` (both Plan 02 and Plan 03 tests)
3. **MCP server with real PG**: `NEOCORTEX_MOCK_DB=false NEOCORTEX_AUTH_MODE=none uv run python -m neocortex`
4. **Health check**: `curl http://localhost:8000/health`
5. **MCP tools discoverable**: Connect an MCP client to `http://localhost:8000/mcp`
6. **RLS enforcement**: Via test_rls.py — two different agent roles can't see each other's data
7. **Shared ontology**: Both agents can read/write `node_type` and `edge_type`
8. **Lint**: `uv run ruff check src/neocortex tests/mcp`

## Final File Tree (after all stages)

```
project-root/
├── docker-compose.yml                     (Plan 02 + neocortex-mcp service)
├── docker/
│   └── mcp/
│       └── Dockerfile                     (Stage 8)
├── .env.example                           (merged Plan 02 + Plan 03 vars)
├── migrations/
│   └── init/
│       ├── 001_extensions.sql             (Plan 02)
│       ├── 002_schema.sql                 (Plan 02)
│       ├── 003_indexes.sql                (Plan 02)
│       ├── 004_seed_ontology.sql          (Plan 02)
│       └── 005_rls_roles.sql              (Stage 9)
├── src/
│   └── neocortex/
│       ├── __init__.py                    (Plan 02)
│       ├── __main__.py                    (Stage 1)
│       ├── config.py                      (Plan 02 — PostgresConfig)
│       ├── mcp_settings.py                (Stage 1 — MCPSettings)
│       ├── models.py                      (Plan 02 — graph entity models)
│       ├── postgres_service.py            (Plan 02)
│       ├── graph_service.py               (Plan 02)
│       ├── server.py                      (Stage 2 — FastMCP factory)
│       ├── tools/
│       │   ├── __init__.py                (Stage 2)
│       │   ├── remember.py                (Stage 2)
│       │   ├── recall.py                  (Stage 2)
│       │   └── discover.py                (Stage 2)
│       ├── auth/
│       │   ├── __init__.py                (Stage 4)
│       │   ├── dev.py                     (Stage 4 — dev-token auth)
│       │   ├── google.py                  (Stage 4)
│       │   └── dependencies.py            (Stage 4)
│       ├── schemas/
│       │   ├── __init__.py                (Stage 3)
│       │   └── memory.py                  (Stage 3 — tool I/O models)
│       └── db/
│           ├── __init__.py                (Stage 1)
│           ├── protocol.py                (Stage 5)
│           ├── mock.py                    (Stage 5)
│           ├── adapter.py                 (Stage 8)
│           ├── roles.py                   (Stage 5 — pure mapping; Stage 9 — adds ensure_pg_role)
│           └── scoped.py                  (Stage 9)
├── tests/
│   ├── conftest.py                        (Plan 02 — PG fixtures)
│   ├── test_postgres_service.py           (Plan 02)
│   ├── test_graph_ontology.py             (Plan 02)
│   ├── test_graph_data.py                 (Plan 02)
│   ├── test_graph_search.py              (Plan 02)
│   └── mcp/
│       ├── __init__.py                    (Stage 6)
│       ├── conftest.py                    (Stage 6)
│       ├── test_tools.py                  (Stage 6)
│       ├── test_schemas.py                (Stage 6)
│       ├── test_mock_repo.py              (Stage 6)
│       ├── test_roles.py                  (Stage 6)
│       ├── test_server.py                 (Stage 6)
│       └── test_rls.py                    (Stage 9)
└── pyproject.toml                         (merged deps)
```

## Issues

[Document any problems discovered during execution]

## Decisions

### Decision: Auth mode — pluggable with dev-token bypass
- **Options**: A) Google OAuth only B) Boolean auth_enabled flag (on/off) C) Pluggable auth_mode with dev-token, Google OAuth, and none
- **Chosen**: C — `auth_mode` setting with three values: `none`, `dev_token`, `google_oauth`
- **Rationale**: `dev_token` mode is critical for hackathon: agents and curl can test the full auth→identity→RLS pipeline without browser redirects or Google Cloud setup. `none` mode for quick local dev. `google_oauth` for production. A boolean flag was too coarse — it collapsed "no auth" and "simple auth for testing" into one mode.

### Decision: OAuth provider (google_oauth mode)
- **Options**: A) Google OAuth B) JWT Verifier only C) MultiAuth (Google + JWT)
- **Chosen**: A — Google OAuth via FastMCP's OAuthProxy
- **Rationale**: Aligns with DeepMind/Gemini stack. OAuthProxy handles Google's non-DCR OAuth and presents a DCR-compliant interface to MCP clients.

### Decision: PostgreSQL access control
- **Options**: A) App-level filtering (WHERE agent_id = ?) B) PostgreSQL Row-Level Security C) Separate PG roles per user
- **Chosen**: C — Separate PG roles per user, with RLS policies
- **Rationale**: Strongest isolation. Each OAuth user maps to a PG role via `SET LOCAL ROLE`. RLS policies on `node`, `edge`, `episode` enforce that agents only see their own data. Ontology tables (`node_type`, `edge_type`) remain shared. Roles inherit from `neocortex_agent` group role for table-level permissions.

### Decision: RLS policy design — shared vs private data
- **Context**: Some data should be visible to all agents (ontology, shared knowledge), while other data is per-agent.
- **Chosen**: `owner_role` column on `node`, `edge`, `episode` with DEFAULT `current_user`. RLS policies allow SELECT on `owner_role = current_user OR owner_role IS NULL`. NULL owner means shared/public data. Ontology tables have no RLS — fully shared.
- **Rationale**: Simple, flexible. Shared nodes (e.g., from admin ingestion) have NULL owner_role and are visible to everyone. Agent-created data is automatically tagged with the agent's PG role.

### Decision: Package structure — avoiding Plan 02 conflicts
- **Context**: Plan 02 creates `src/neocortex/` with `config.py`, `models.py`, etc. Plan 03 needs to add MCP-specific code without merge conflicts.
- **Chosen**: Plan 03 creates only NEW files (`server.py`, `mcp_settings.py`, `tools/`, `auth/`, `schemas/`, `db/`). After rebase, both sets coexist. MCP settings use `NEOCORTEX_` prefix; Plan 02's PG config uses `POSTGRES_` prefix.
- **Rationale**: Minimizes rebase conflicts. The only expected conflicts are in `pyproject.toml` (dep lists) and `.env.example` (env vars) — both trivially resolvable.

### Decision: Repository adapter pattern
- **Context**: MCP tools need a database interface. Plan 02's `GraphService` has the actual implementation. We need a bridge.
- **Chosen**: `MemoryRepository` Protocol with two implementations: `InMemoryRepository` (mock) and `GraphServiceAdapter` (wraps Plan 02's `GraphService`). Tools depend only on the Protocol.
- **Rationale**: Clean dependency inversion. Mock mode works without PG. Real mode delegates to `GraphService`. The adapter translates between MCP-layer schemas and Plan 02's models.
