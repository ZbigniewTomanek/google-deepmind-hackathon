# Plan 08: Permission Schemas for Shared Knowledge Structures

## Overview

NeoCortex agents currently have unrestricted read access to all shared schemas and no mechanism to write to them. This plan introduces an application-level permission model that controls per-agent read/write access to shared knowledge structures, a REST admin API for managing permissions, and a bootstrap admin user with superuser privileges.

**Key design decisions:**
- Permissions are stored in a new `graph_permissions` PostgreSQL table (application-level, not PG roles)
- Admin identity is DB-based via `agent_registry` table with `is_admin` flag — allows runtime promotion/demotion
- A bootstrap admin is seeded at startup from config (`NEOCORTEX_BOOTSTRAP_ADMIN_ID`, default `"admin"`) to avoid chicken-and-egg
- Admin routes are mounted on the existing ingestion FastAPI app (one server)
- `InMemoryPermissionService` mirrors the PG service for mock-DB mode and tests
- Existing RLS remains untouched — it handles row-level isolation *within* a schema; permissions handle *schema-level* access control
- `agent_id` in `graph_permissions` has no FK to `agent_registry` — this is intentional to allow lazy agent registration (permissions can be pre-provisioned before an agent first connects)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Permission Flow                          │
│                                                                 │
│  Agent (agent_id from auth)                                     │
│    │                                                            │
│    ├─► MCP Tool (remember/recall/discover)                      │
│    │     └─► GraphRouter                                        │
│    │           ├─ route_recall() ──► filter shared by can_read  │
│    │           └─ route_store_to() ► check can_write on target  │
│    │                                                            │
│    ├─► Ingestion API (/ingest/text?target_graph=...)            │
│    │     └─► check can_write on target_graph                    │
│    │         └─► extraction job carries target_schema            │
│    │                                                            │
│    ├─► MCP remember tool (target_graph=...)                     │
│    │     └─► check can_write on target_graph                    │
│    │         └─► extraction job carries target_schema            │
│    │                                                            │
│    └─► Admin API (/admin/permissions, /admin/graphs)            │
│          └─► requires is_admin(agent_id)                        │
│                                                                 │
│  PermissionService (protocol)                                   │
│    ├─ PostgresPermissionService (real DB)                        │
│    └─ InMemoryPermissionService (mock/tests)                    │
│                                                                 │
│  agent_registry table                                           │
│    (agent_id, is_admin, created_at)                             │
│  graph_permissions table                                        │
│    (agent_id, schema_name, can_read, can_write)                 │
└─────────────────────────────────────────────────────────────────┘
```

## Execution Protocol

Each stage is independently testable, committable, and leaves the codebase in a working state. Execute stages sequentially. Run `uv run pytest tests/ -v` after each stage. One commit per stage.

---

## Stage 1: Permission Data Model, Service Layer & Wiring

**Goal**: Introduce the permission table, Pydantic models, service protocol with two implementations, admin settings, and wire everything into `ServiceContext`.

### Steps

#### 1.1 — SQL migration for `agent_registry` and `graph_permissions`

Create `migrations/init/007_graph_permissions.sql`:

```sql
-- Agent registry: tracks known agents and admin status
CREATE TABLE IF NOT EXISTS agent_registry (
    id          SERIAL PRIMARY KEY,
    agent_id    TEXT UNIQUE NOT NULL,
    is_admin    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_registry_agent ON agent_registry (agent_id);

-- Graph-level permissions: per-agent, per-shared-schema access control
-- NOTE: agent_id intentionally has no FK to agent_registry to support
-- pre-provisioning permissions before an agent first connects.
CREATE TABLE IF NOT EXISTS graph_permissions (
    id          SERIAL PRIMARY KEY,
    agent_id    TEXT NOT NULL,
    schema_name TEXT NOT NULL REFERENCES graph_registry(schema_name) ON DELETE CASCADE,
    can_read    BOOLEAN NOT NULL DEFAULT FALSE,
    can_write   BOOLEAN NOT NULL DEFAULT FALSE,
    granted_by  TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (agent_id, schema_name)
);

CREATE INDEX IF NOT EXISTS idx_graph_permissions_agent ON graph_permissions (agent_id);
CREATE INDEX IF NOT EXISTS idx_graph_permissions_schema ON graph_permissions (schema_name);
```

#### 1.2 — Pydantic models

Create `src/neocortex/schemas/permissions.py`:

```python
from datetime import datetime
from pydantic import BaseModel

class AgentInfo(BaseModel):
    id: int
    agent_id: str
    is_admin: bool
    created_at: datetime
    updated_at: datetime

class PermissionInfo(BaseModel):
    id: int
    agent_id: str
    schema_name: str
    can_read: bool
    can_write: bool
    granted_by: str
    created_at: datetime
    updated_at: datetime

class PermissionGrant(BaseModel):
    """Request body for granting/updating permissions."""
    agent_id: str
    schema_name: str
    can_read: bool = False
    can_write: bool = False
```

#### 1.3 — Admin settings

Add to `MCPSettings` in `src/neocortex/mcp_settings.py`:

```python
bootstrap_admin_id: str = "admin"        # Seeded into agent_registry as admin on startup
admin_token: str = "admin-token-neocortex"  # Bootstrap admin dev token
```

On startup (`create_services`), upsert this agent into `agent_registry` with `is_admin=True`. This solves the chicken-and-egg problem — at least one admin always exists.

#### 1.4 — Permission service protocol

Create `src/neocortex/permissions/__init__.py` (package) and `src/neocortex/permissions/protocol.py`:

```python
from typing import Protocol

from neocortex.schemas.permissions import AgentInfo, PermissionInfo


class PermissionChecker(Protocol):
    async def is_admin(self, agent_id: str) -> bool: ...
    async def ensure_admin(self, agent_id: str) -> None:
        """Register agent as admin in agent_registry."""
    async def can_read_schema(self, agent_id: str, schema_name: str) -> bool: ...
    async def can_write_schema(self, agent_id: str, schema_name: str) -> bool: ...
    async def readable_schemas(self, agent_id: str, candidates: list[str]) -> set[str]:
        """Return the subset of candidate schema names the agent can read.

        Batch method to avoid N+1 queries in route_recall/route_discover.
        Admins return all candidates.
        """
    async def grant(self, agent_id: str, schema_name: str,
                    can_read: bool, can_write: bool, granted_by: str) -> PermissionInfo: ...
    async def revoke(self, agent_id: str, schema_name: str) -> bool: ...
    async def list_for_agent(self, agent_id: str) -> list[PermissionInfo]: ...
    async def list_for_schema(self, schema_name: str) -> list[PermissionInfo]: ...
    async def set_admin(self, agent_id: str, is_admin: bool) -> None:
        """Promote or demote an agent. Upserts into agent_registry.

        Raises ValueError if attempting to demote the bootstrap admin.
        """
    async def list_agents(self) -> list[AgentInfo]: ...
```

#### 1.5 — PostgreSQL implementation

Create `src/neocortex/permissions/pg_service.py`:

- `PostgresPermissionService(pg: PostgresService, bootstrap_admin_id: str)`
- `is_admin()` queries `agent_registry WHERE agent_id = $1 AND is_admin = TRUE`
- Admins bypass `can_read`/`can_write` checks (always return `True`)
- `ensure_admin()` upserts into `agent_registry` with `is_admin=TRUE`:
  ```sql
  INSERT INTO agent_registry (agent_id, is_admin) VALUES ($1, TRUE)
  ON CONFLICT (agent_id) DO UPDATE SET is_admin = TRUE, updated_at = now()
  ```
- `set_admin()` upserts into `agent_registry` with the given `is_admin` flag. Raises `ValueError` if `agent_id == self._bootstrap_admin_id` and `is_admin=False`.
- `readable_schemas()` — single query:
  ```sql
  SELECT schema_name FROM graph_permissions
  WHERE agent_id = $1 AND schema_name = ANY($2) AND can_read = TRUE
  ```
  Admin check first — if admin, return all candidates without hitting `graph_permissions`.
- `grant()` uses `INSERT ... ON CONFLICT (agent_id, schema_name) DO UPDATE`
- `revoke()` deletes the row
- `list_for_agent()` / `list_for_schema()` are straightforward SELECT queries
- `list_agents()` returns all entries from `agent_registry`
- All queries use `$1`/`$2` parameterized style (never string interpolation)

#### 1.6 — In-memory implementation

Create `src/neocortex/permissions/memory_service.py`:

- `InMemoryPermissionService(bootstrap_admin_id: str)`
- Stores permissions in `dict[(agent_id, schema_name), PermissionInfo]`
- Stores admin state in `dict[str, AgentInfo]`
- Same interface, same admin bypass logic, same bootstrap demotion guard
- `readable_schemas()` — set comprehension over stored permissions (admin short-circuit)
- Used when `NEOCORTEX_MOCK_DB=true`

#### 1.7 — Wire into ServiceContext

Update `src/neocortex/services.py`:

- Add `permissions: PermissionChecker` to `ServiceContext` (use protocol type, not concrete union)
- In `create_services()`:
  - Mock mode: create `InMemoryPermissionService(settings.bootstrap_admin_id)`, then `await permissions.ensure_admin(settings.bootstrap_admin_id)`
  - Real mode: create `PostgresPermissionService(pg, settings.bootstrap_admin_id)`, then `await permissions.ensure_admin(settings.bootstrap_admin_id)`
- This guarantees the bootstrap admin exists in `agent_registry` on every startup

#### 1.8 — Unit tests

Create `tests/unit/test_permissions_service.py`:

- Test `InMemoryPermissionService`:
  - `grant` creates permission, `revoke` removes it
  - `can_read_schema` / `can_write_schema` return correct booleans
  - `readable_schemas` returns correct subset; admin returns all candidates
  - `list_for_agent` / `list_for_schema` return correct entries
  - Admin agent always returns `True` for `can_read` / `can_write`
  - Non-existent permission returns `False`
  - `grant` with update (change `can_read` from False to True)
  - `set_admin` promotes/demotes correctly
  - `set_admin` on bootstrap admin with `is_admin=False` raises `ValueError`

### Verification

```bash
uv run pytest tests/unit/test_permissions_service.py -v
uv run pytest tests/ -v  # no regressions
```

### Commit

```
feat(permissions): add permission data model, service layer, and wiring

- SQL migration 007: agent_registry + graph_permissions tables
- PermissionChecker protocol with PG and in-memory implementations
- DB-based admin via agent_registry.is_admin (bootstrap admin seeded on startup)
- Batch readable_schemas method avoids N+1 queries
- Bootstrap admin demotion guard in set_admin
- Wired into ServiceContext for both mock and real DB modes
- Unit tests for InMemoryPermissionService
```

---

## Stage 2: GraphRouter Permission Enforcement & MCP Tool Support

**Goal**: The router filters shared schemas by read permission, adds a method for targeted writes to shared schemas with write permission checks, and the MCP `remember` tool gains `target_graph` support.

### Steps

#### 2.1 — Router gets PermissionChecker dependency

Update `GraphRouter.__init__()` to accept `permissions: PermissionChecker`:

```python
class GraphRouter:
    def __init__(self, schema_mgr: SchemaManager, pool: asyncpg.Pool,
                 permissions: PermissionChecker):
        self._schema_mgr = schema_mgr
        self._pool = pool
        self._permissions = permissions
```

Update `create_services()` to pass `permissions` when constructing `GraphRouter`.

#### 2.2 — Filter `route_recall()` by read permission (batch)

In `route_recall()`, after fetching shared graphs, filter using the batch method:

```python
async def route_recall(self, agent_id: str) -> list[str]:
    agent_graphs = await self._schema_mgr.list_graphs(agent_id=agent_id)
    shared_graphs = await self._schema_mgr.list_graphs(agent_id="shared")

    # Filter shared graphs by read permission (single query, admins short-circuit)
    shared_names = [g.schema_name for g in shared_graphs]
    readable = await self._permissions.readable_schemas(agent_id, shared_names)
    accessible_shared = [g for g in shared_graphs if g.schema_name in readable]

    ordered_agent = sorted(agent_graphs, key=_graph_priority)
    ordered_shared = sorted(accessible_shared, key=_graph_priority)
    return [g.schema_name for g in ordered_agent + ordered_shared]
```

#### 2.3 — Add `route_store_to()` for targeted shared writes

New method on `GraphRouter`:

```python
async def route_store_to(self, agent_id: str, target_schema: str) -> str:
    """Validate write permission and return the target schema for a directed store."""
    # Verify schema exists and is shared
    graphs = await self._schema_mgr.list_graphs(agent_id="shared")
    schema_names = {g.schema_name for g in graphs}
    if target_schema not in schema_names:
        raise PermissionError(f"Schema '{target_schema}' is not a shared graph")

    if not await self._permissions.can_write_schema(agent_id, target_schema):
        raise PermissionError(
            f"Agent '{agent_id}' does not have write access to '{target_schema}'"
        )
    return target_schema
```

#### 2.4 — Adapter support for targeted store

Add `store_episode_to()` method to `GraphServiceAdapter` that takes an explicit `target_schema` instead of routing via `route_store()`. This uses `graph_scoped_connection` (shared schema needs RLS role).

Also add `store_episode_to()` to the `MemoryRepository` protocol:

```python
async def store_episode_to(
    self,
    agent_id: str,
    target_schema: str,
    content: str,
    context: str | None = None,
    source_type: str = "mcp",
) -> int:
    """Store an episode in an explicit target schema (for shared graph writes)."""
```

**InMemoryRepository** implementation: use a `_schema_episodes: dict[str, list[EpisodeRecord]]` to track which schema episodes belong to. Default `store_episode()` stores under `f"ncx_{agent_id}__personal"`. `store_episode_to()` stores under the given `target_schema`. `get_episode()` searches across all schema buckets.

#### 2.5 — Update `route_discover()` to respect read permissions

Same filtering as `route_recall()` — agents only discover schemas they can read. Use `readable_schemas()` batch method.

#### 2.6 — MCP `remember` tool gains `target_graph` support

Update `src/neocortex/tools/remember.py` to accept an optional `target_graph` parameter:

```python
async def remember(
    text: str,
    context: str | None = None,
    target_graph: str | None = None,
    ctx: Context | None = None,
) -> RememberResult:
    """Store a memory. Describe what you want to remember in natural language.

    Args:
        text: The content to remember, in natural language.
        context: Optional context about where/why this memory is being stored.
        target_graph: Optional shared graph to write to (requires write permission).
                      If omitted, stores to the agent's personal graph.
    """
```

When `target_graph` is set:
1. Get `PermissionChecker` from `ctx.lifespan_context["permissions"]`
2. Call `router.route_store_to(agent_id, target_graph)` to validate write permission
3. Use `repo.store_episode_to(agent_id, target_graph, content=text, ...)` instead of `store_episode()`
4. Pass `target_schema=target_graph` to the extraction job (see Stage 3)

When `target_graph` is None: existing behavior unchanged.

#### 2.7 — Tests

Create `tests/unit/test_router_permissions.py`:

- Router with InMemoryPermissionService
- Agent with no shared permissions -> `route_recall` returns only personal schemas
- Agent with read on `ncx_shared__knowledge` -> `route_recall` includes it
- Agent without write -> `route_store_to` raises `PermissionError`
- Agent with write -> `route_store_to` succeeds
- Admin agent -> bypasses all checks
- `route_discover` respects same read filtering

Create `tests/unit/test_remember_target_graph.py`:

- `remember` with `target_graph` and write permission -> stores in target schema
- `remember` with `target_graph` without write permission -> raises PermissionError
- `remember` without `target_graph` -> stores in personal (unchanged)

### Verification

```bash
uv run pytest tests/unit/test_router_permissions.py tests/unit/test_remember_target_graph.py -v
uv run pytest tests/ -v
```

### Commit

```
feat(permissions): enforce read/write permissions in GraphRouter and remember tool

- route_recall filters shared schemas by read permission (batch query)
- route_store_to validates write permission for targeted shared writes
- Admin agents bypass permission checks
- GraphServiceAdapter.store_episode_to for directed shared writes
- InMemoryRepository.store_episode_to with schema-bucketed episodes
- MCP remember tool accepts target_graph for shared writes
```

---

## Stage 3: Ingestion API Permission Enforcement & Extraction Pipeline Awareness

**Goal**: Ingestion endpoints accept an optional `target_graph` parameter. When provided, validate that the agent has write permission to the specified shared schema. The extraction pipeline carries `target_schema` so that extracted nodes/edges land in the correct graph — not the agent's personal schema.

### Steps

#### 3.1 — Update ingestion request models

In `src/neocortex/ingestion/models.py`, add `target_graph` to request models:

```python
class TextIngestionRequest(BaseModel):
    text: str = Field(min_length=1)
    metadata: dict = Field(default_factory=dict)
    target_graph: str | None = Field(
        default=None,
        description="Target shared graph schema. If omitted, stores to agent's personal graph.",
    )
```

Same for `EventsIngestionRequest`. For `ingest_document`, accept `target_graph` as a form field (it's multipart).

#### 3.2 — Permission check in routes

In each route handler, before calling the processor:

```python
if body.target_graph:
    permissions = request.app.state.permissions
    if not await permissions.can_write_schema(agent_id, body.target_graph):
        raise HTTPException(
            status_code=403,
            detail=f"Agent '{agent_id}' does not have write access to '{body.target_graph}'",
        )
```

#### 3.3 — Processor handles target_schema

Update `EpisodeProcessor.process_text()` (and siblings) to accept optional `target_schema: str | None`. When provided, use `repo.store_episode_to(agent_id, target_schema, ...)` instead of `repo.store_episode(agent_id, ...)`.

#### 3.4 — Extraction pipeline carries `target_schema`

This is critical for knowledge propagation. Without it, episodes stored in shared schemas are never extracted into graph nodes/edges.

**Problem**: `_enqueue_extraction()` currently passes only `(agent_id, episode_ids)`. The extraction worker calls `repo.get_episode(agent_id, episode_id)` which routes to the personal schema — but the episode is in the shared schema. All subsequent `upsert_node`/`upsert_edge` calls also target the personal schema.

**Fix — thread `target_schema` through the entire extraction path:**

1. Update `_enqueue_extraction()` to accept and pass `target_schema`:
   ```python
   async def _enqueue_extraction(self, agent_id: str, episode_id: int,
                                  target_schema: str | None = None) -> int | None:
       if not self._job_app or not self._extraction_enabled:
           return None
       job_id = await self._job_app.configure_task("extract_episode").defer_async(
           agent_id=agent_id, episode_ids=[episode_id],
           target_schema=target_schema,
       )
       return job_id
   ```

2. Update `extract_episode` task in `src/neocortex/jobs/tasks.py`:
   ```python
   @app.task(name="extract_episode", ...)
   async def extract_episode(
       agent_id: str,
       episode_ids: list[int],
       target_schema: str | None = None,
   ) -> None:
       ...
       await run_extraction(
           repo=services["repo"],
           embeddings=services["embeddings"],
           agent_id=agent_id,
           episode_ids=episode_ids,
           target_schema=target_schema,
           ...
       )
   ```

3. Update `run_extraction()` in `src/neocortex/extraction/pipeline.py`:
   ```python
   async def run_extraction(
       repo: MemoryRepository,
       embeddings: EmbeddingService | None,
       agent_id: str,
       episode_ids: list[int],
       target_schema: str | None = None,
       ...
   ) -> None:
   ```
   When `target_schema` is set, pass it to `_persist_payload()`.

4. Update `_persist_payload()` to accept `target_schema: str | None`. When set, use `repo.store_episode_to`-style methods for all writes. Specifically, add `target_schema: str | None = None` parameter to the following `MemoryRepository` protocol methods:
   - `get_episode()` — to find the episode in the correct schema
   - `get_or_create_node_type()`
   - `upsert_node()`
   - `find_nodes_by_name()`
   - `upsert_edge()`
   - `get_or_create_edge_type()`
   - `get_node_types()`
   - `get_edge_types()`
   - `list_all_node_names()`

   In `GraphServiceAdapter`, when `target_schema` is not None, use `schema_scoped_connection(pool, target_schema)` directly instead of routing via `agent_id`. In `InMemoryRepository`, when `target_schema` is not None, scope lookups/writes to that schema bucket.

   **Note**: Adding an optional parameter with a default of `None` is backward-compatible — all existing callers continue to work without changes.

#### 3.5 — Wire permissions into ingestion app

In `src/neocortex/ingestion/app.py`, add `app.state.permissions = ctx["permissions"]` during lifespan.

#### 3.6 — Tests

Create `tests/unit/test_ingestion_permissions.py`:

- Agent without write permission -> 403 when `target_graph` is set
- Agent with write permission -> 200, episode stored in target schema
- Admin agent -> bypasses permission check
- No `target_graph` -> stores to personal (existing behavior unchanged)
- Invalid `target_graph` (not a shared schema) -> 403 or 404

Create `tests/unit/test_extraction_target_schema.py`:

- Episode stored in shared schema via `target_graph` -> extraction creates nodes/edges in the **shared** schema (not personal)
- Episode stored without `target_graph` -> extraction targets personal schema (unchanged)
- Verify `_enqueue_extraction` passes `target_schema` through to the task

### Verification

```bash
uv run pytest tests/unit/test_ingestion_permissions.py tests/unit/test_extraction_target_schema.py -v
uv run pytest tests/ -v
```

### Commit

```
feat(permissions): enforce write permissions in ingestion API with extraction awareness

- target_graph parameter on /ingest/text, /ingest/document, /ingest/events
- 403 when agent lacks write access to target shared schema
- EpisodeProcessor.process_text routes to target schema when specified
- Extraction pipeline carries target_schema through task → run_extraction → _persist_payload
- MemoryRepository methods accept optional target_schema for shared graph writes
- Admin bypass for all permission checks
```

---

## Stage 4: Admin REST API

**Goal**: New FastAPI router mounted at `/admin/` with endpoints for managing permissions and shared knowledge structures. All endpoints require admin auth.

### Steps

#### 4.1 — Admin auth dependency

Create `src/neocortex/admin/auth.py`:

```python
async def require_admin(request: Request, agent_id: str = Depends(get_agent_id)) -> str:
    """Dependency that ensures the caller is an admin. Returns agent_id."""
    permissions = request.app.state.permissions
    if not await permissions.is_admin(agent_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    return agent_id
```

#### 4.2 — Permission management endpoints

Create `src/neocortex/admin/routes.py` with router prefix `/admin`:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/admin/permissions` | Grant or update permission (body: `PermissionGrant`) |
| `DELETE` | `/admin/permissions/{agent_id}/{schema_name}` | Revoke permission |
| `GET` | `/admin/permissions` | List all permissions (optional `?agent_id=X` or `?schema_name=X` filter) |
| `GET` | `/admin/permissions/{agent_id}` | List permissions for a specific agent |

Agent management endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/admin/agents` | List all registered agents |
| `PUT` | `/admin/agents/{agent_id}/admin` | Promote agent to admin (`{"is_admin": true}`) |
| `DELETE` | `/admin/agents/{agent_id}/admin` | Demote agent from admin |

All endpoints use `Depends(require_admin)`.

Grant endpoint:
```python
@router.post("/permissions", response_model=PermissionInfo)
async def grant_permission(
    body: PermissionGrant,
    request: Request,
    admin_id: str = Depends(require_admin),
):
    permissions = request.app.state.permissions
    return await permissions.grant(
        agent_id=body.agent_id,
        schema_name=body.schema_name,
        can_read=body.can_read,
        can_write=body.can_write,
        granted_by=admin_id,
    )
```

Demote endpoint must handle the bootstrap admin guard:
```python
@router.delete("/agents/{agent_id}/admin")
async def demote_agent(agent_id: str, request: Request, admin_id: str = Depends(require_admin)):
    permissions = request.app.state.permissions
    try:
        await permissions.set_admin(agent_id, is_admin=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "demoted", "agent_id": agent_id}
```

#### 4.3 — Graph management endpoints

Add to the same router:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/admin/graphs` | Create a new shared graph (body: `{purpose: str}`) |
| `GET` | `/admin/graphs` | List all graphs (personal + shared) |
| `DELETE` | `/admin/graphs/{schema_name}` | Drop a shared graph (cascades permissions via FK) |

These delegate to `SchemaManager` from `app.state.services_ctx`.

#### 4.4 — Mount on ingestion app

In `src/neocortex/ingestion/app.py`:

```python
from neocortex.admin.routes import router as admin_router
app.include_router(admin_router)
```

Also expose `schema_mgr` on `app.state` for the graph management endpoints.

#### 4.5 — Bootstrap admin token in dev_token mode

In `create_app()` lifespan, ensure the admin token is in the token map:

```python
token_map = load_token_map(settings)
# Ensure bootstrap admin token maps to the bootstrap admin agent_id
if settings.admin_token and settings.admin_token not in token_map:
    token_map[settings.admin_token] = settings.bootstrap_admin_id
app.state.token_map = token_map
```

#### 4.6 — Tests

Create `tests/unit/test_admin_api.py`:

- Non-admin agent -> 403 on all `/admin/` endpoints
- Admin grants read permission -> verify via list
- Admin grants write permission -> verify agent can now write
- Admin revokes permission -> verify agent can no longer read/write
- Admin creates shared graph -> appears in list
- Admin drops shared graph -> permissions cascade-deleted
- Update permission (grant with changed flags) -> reflects new state
- Admin promotes agent to admin -> new admin can access `/admin/` endpoints
- Admin demotes agent -> demoted agent gets 403 on `/admin/`
- Bootstrap admin demotion -> 400 with error message

### Verification

```bash
uv run pytest tests/unit/test_admin_api.py -v
uv run pytest tests/ -v
```

### Commit

```
feat(admin): REST API for permission and graph management

- POST/DELETE/GET /admin/permissions for grant/revoke/list
- POST/GET/DELETE /admin/graphs for shared graph lifecycle
- require_admin dependency enforces admin-only access
- Bootstrap admin token wired into dev_token auth mode
- Bootstrap admin demotion returns 400
```

---

## Stage 5: Integration Tests (In-Memory)

**Goal**: Integration tests covering the full permission flow using in-memory implementations, and CLAUDE.md update.

### Steps

#### 5.1 — Integration test: full permission lifecycle

Create `tests/integration/test_permission_flow.py` (uses `InMemoryRepository` + `InMemoryPermissionService`):

1. Admin creates shared graph `ncx_shared__research`
2. Admin grants agent "alice" `can_read=True, can_write=True` on it
3. Admin grants agent "bob" `can_read=True, can_write=False` on it
4. Alice ingests text with `target_graph="ncx_shared__research"` -> success
5. Bob ingests text with `target_graph="ncx_shared__research"` -> 403
6. Alice recalls -> sees `ncx_shared__research` in accessible schemas
7. Bob recalls -> sees `ncx_shared__research` in accessible schemas (read OK)
8. Unauthorized agent "eve" recalls -> does NOT see `ncx_shared__research`
9. Admin revokes alice's write -> alice ingestion now 403
10. Admin drops graph -> all permissions gone

#### 5.2 — Integration test: extraction targets correct schema

Create `tests/integration/test_extraction_target_schema.py`:

1. Admin creates shared graph, grants agent "alice" write access
2. Alice ingests text with `target_graph="ncx_shared__research"`
3. Extraction runs (mocked LLM) with `target_schema="ncx_shared__research"`
4. Verify nodes/edges created in the shared schema (not alice's personal schema)
5. Agent "bob" with read access recalls from shared graph -> sees extracted nodes

#### 5.3 — Verify mock DB mode

Test that `NEOCORTEX_MOCK_DB=true` boots successfully with permission service:

```bash
NEOCORTEX_MOCK_DB=true uv run python -c "
from neocortex.services import create_services
from neocortex.mcp_settings import MCPSettings
import asyncio
ctx = asyncio.run(create_services(MCPSettings()))
assert ctx['permissions'] is not None
print('OK: permissions wired in mock mode')
"
```

#### 5.4 — Update CLAUDE.md

Add permission system to the Architecture Rules section:

```
**6. Shared schema access requires explicit permissions.**
graph_permissions table controls read/write access per agent per shared schema.
GraphRouter filters by can_read; ingestion validates can_write.
Admin agents (is_admin in agent_registry) bypass all permission checks.
Bootstrap admin seeded from NEOCORTEX_BOOTSTRAP_ADMIN_ID on every startup.
PermissionChecker protocol has PG and in-memory implementations.
Extraction pipeline carries target_schema so nodes/edges land in the correct graph.
```

#### 5.5 — Update codebase map in CLAUDE.md

Add new files:
```
  permissions/             # Schema-level access control
    protocol.py            # PermissionChecker protocol
    pg_service.py          # PostgreSQL implementation
    memory_service.py      # In-memory implementation (tests/mock)
  admin/                   # Admin REST API (mounted on ingestion app)
    auth.py                # require_admin dependency
    routes.py              # Permission + graph management endpoints
```

### Verification

```bash
uv run pytest tests/ -v  # ALL tests pass
NEOCORTEX_MOCK_DB=true uv run python -m neocortex  # server boots
```

### Commit

```
feat(permissions): integration tests and CLAUDE.md update

- End-to-end permission lifecycle test (in-memory)
- Extraction target schema integration test
- Mock DB mode validation
- CLAUDE.md updated with permission architecture rules
```

---

## Stage 6: E2E Smoke Tests & Documentation

**Goal**: E2E tests against a running server (PostgreSQL + both services), verifying that the permission system works end-to-end with real database. Update `docs/development.md` with new config, endpoints, and E2E test instructions.

### Steps

#### 6.1 — E2E permission smoke test

Create `scripts/e2e_permission_test.py` following the existing E2E test pattern (`scripts/e2e_mcp_test.py`, `scripts/e2e_ingestion_test.py`):

1. **Setup**: Use admin token to create a shared graph and grant permissions
   ```
   POST /admin/graphs         {"purpose": "e2e_test"}
   POST /admin/permissions    {"agent_id": "e2e_alice", "schema_name": "ncx_shared__e2e_test", "can_read": true, "can_write": true}
   POST /admin/permissions    {"agent_id": "e2e_bob", "schema_name": "ncx_shared__e2e_test", "can_read": true, "can_write": false}
   ```
2. **Write test**: Alice ingests text with `target_graph` -> 200
3. **Write denied**: Bob ingests text with `target_graph` -> 403
4. **Unauthorized**: Eve (no permissions) ingests with `target_graph` -> 403
5. **Read test**: Alice and Bob can recall and see the shared graph. Eve cannot.
6. **Revoke test**: Admin revokes Alice's write -> Alice gets 403
7. **Admin lifecycle**: Admin promotes Bob to admin -> Bob can access `/admin/` endpoints. Admin demotes Bob -> 403 on admin routes.
8. **Cleanup**: Admin drops the shared graph -> permissions cascade-deleted

#### 6.2 — Wire into `run_e2e.sh`

Add `e2e_permission_test.py` to the E2E test suite. Ensure `dev_tokens.json` includes the admin token mapping:

```json
{
  "admin-token-neocortex": "admin",
  "alice-token": "e2e_alice",
  "bob-token": "e2e_bob",
  "eve-token": "e2e_eve",
  "dev-token-neocortex": "dev-user"
}
```

#### 6.3 — Update `docs/development.md`

**Configuration table** — add new settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `NEOCORTEX_BOOTSTRAP_ADMIN_ID` | `admin` | Agent ID seeded as admin on every startup |
| `NEOCORTEX_ADMIN_TOKEN` | `admin-token-neocortex` | Bearer token for bootstrap admin (dev mode) |

**Endpoints section** — add admin API:

```
Admin API (mounted on ingestion server :8001):
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

**Ingestion endpoints** — document `target_graph` parameter:

```
POST /ingest/text      — body: {text, metadata, target_graph?}
POST /ingest/events    — body: {events, metadata, target_graph?}
POST /ingest/document  — multipart form with optional target_graph field
```

**E2E section** — add permission test:

```bash
# Permission system tests
./scripts/run_e2e.sh scripts/e2e_permission_test.py
```

**Project Layout** — add new directories to the tree.

### Verification

```bash
# E2E (requires Docker)
./scripts/run_e2e.sh scripts/e2e_permission_test.py

# Docs render correctly
cat docs/development.md  # visual check
```

### Commit

```
test(permissions): E2E smoke tests and development docs update

- E2E permission lifecycle test against real PostgreSQL
- dev_tokens.json updated with admin + test agent tokens
- docs/development.md: new config vars, admin API endpoints, target_graph docs
```

---

## Progress Tracker

| Stage | Description | Status | Notes |
|-------|-------------|--------|-------|
| 1 | Permission data model, service layer & wiring | DONE | SQL migration 007, Pydantic models, PermissionChecker protocol, PG + in-memory impls, wired into ServiceContext, 18 unit tests |
| 2 | GraphRouter permission enforcement & MCP tool support | DONE | Router filters shared schemas by read permission, route_store_to validates write, store_episode_to on protocol/adapter/mock, remember tool gains target_graph, 11 new tests |
| 3 | Ingestion API permission enforcement & extraction awareness | PENDING | |
| 4 | Admin REST API | PENDING | |
| 5 | Integration tests (in-memory) & CLAUDE.md | PENDING | |
| 6 | E2E smoke tests & development docs | PENDING | |

Last stage completed: Stage 2 — GraphRouter permission enforcement & MCP tool support
Last updated by: plan-runner-agent

---

## Files Modified/Created

### New files
- `migrations/init/007_graph_permissions.sql`
- `src/neocortex/schemas/permissions.py`
- `src/neocortex/permissions/__init__.py`
- `src/neocortex/permissions/protocol.py`
- `src/neocortex/permissions/pg_service.py`
- `src/neocortex/permissions/memory_service.py`
- `src/neocortex/admin/__init__.py`
- `src/neocortex/admin/auth.py`
- `src/neocortex/admin/routes.py`
- `tests/unit/test_permissions_service.py`
- `tests/unit/test_router_permissions.py`
- `tests/unit/test_remember_target_graph.py`
- `tests/unit/test_ingestion_permissions.py`
- `tests/unit/test_extraction_target_schema.py`
- `tests/unit/test_admin_api.py`
- `tests/integration/test_permission_flow.py`
- `tests/integration/test_extraction_target_schema.py`
- `scripts/e2e_permission_test.py`

### Modified files
- `src/neocortex/mcp_settings.py` — add `bootstrap_admin_id`, `admin_token`
- `src/neocortex/services.py` — add `permissions: PermissionChecker` to `ServiceContext`
- `src/neocortex/graph_router.py` — accept `PermissionChecker`, filter by permissions, `route_store_to()`
- `src/neocortex/db/protocol.py` — add `store_episode_to()`, add `target_schema` param to write methods
- `src/neocortex/db/adapter.py` — implement `store_episode_to()`, `target_schema` support in write methods
- `src/neocortex/db/mock.py` — implement `store_episode_to()`, schema-bucketed episodes, `target_schema` support
- `src/neocortex/tools/remember.py` — add `target_graph` parameter with permission check
- `src/neocortex/ingestion/models.py` — add `target_graph` field
- `src/neocortex/ingestion/routes.py` — permission check before processing
- `src/neocortex/ingestion/app.py` — wire permissions + admin router
- `src/neocortex/ingestion/episode_processor.py` — accept `target_schema`, pass to extraction
- `src/neocortex/jobs/tasks.py` — `extract_episode` accepts `target_schema`, passes to `run_extraction`
- `src/neocortex/extraction/pipeline.py` — `run_extraction` and `_persist_payload` accept `target_schema`, all repo calls use it
- `docs/development.md` — new config, admin API docs, target_graph docs, E2E test instructions
- `CLAUDE.md` — architecture rules + codebase map update
