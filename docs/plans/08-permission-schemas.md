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

class PermissionChecker(Protocol):
    async def is_admin(self, agent_id: str) -> bool: ...
    async def ensure_admin(self, agent_id: str) -> None:
        """Register agent as admin in agent_registry."""
    async def can_read_schema(self, agent_id: str, schema_name: str) -> bool: ...
    async def can_write_schema(self, agent_id: str, schema_name: str) -> bool: ...
    async def grant(self, agent_id: str, schema_name: str,
                    can_read: bool, can_write: bool, granted_by: str) -> PermissionInfo: ...
    async def revoke(self, agent_id: str, schema_name: str) -> bool: ...
    async def list_for_agent(self, agent_id: str) -> list[PermissionInfo]: ...
    async def list_for_schema(self, schema_name: str) -> list[PermissionInfo]: ...
    async def set_admin(self, agent_id: str, is_admin: bool) -> None:
        """Promote or demote an agent. Upserts into agent_registry."""
    async def list_agents(self) -> list[AgentInfo]: ...
```

#### 1.5 — AgentInfo model

Add to `src/neocortex/schemas/permissions.py`:

```python
class AgentInfo(BaseModel):
    id: int
    agent_id: str
    is_admin: bool
    created_at: datetime
    updated_at: datetime
```

#### 1.6 — PostgreSQL implementation

Create `src/neocortex/permissions/pg_service.py`:

- `PostgresPermissionService(pg: PostgresService)`
- `is_admin()` queries `agent_registry WHERE agent_id = $1 AND is_admin = TRUE`
- Admins bypass `can_read`/`can_write` checks (always return `True`)
- `ensure_admin()` upserts into `agent_registry` with `is_admin=TRUE` (used at startup for bootstrap)
- `set_admin()` upserts into `agent_registry` with the given `is_admin` flag
- `grant()` uses `INSERT ... ON CONFLICT (agent_id, schema_name) DO UPDATE`
- `revoke()` deletes the row
- `list_for_agent()` / `list_for_schema()` are straightforward SELECT queries
- `list_agents()` returns all entries from `agent_registry`
- All queries use `$1`/`$2` parameterized style (never string interpolation)

#### 1.7 — In-memory implementation

Create `src/neocortex/permissions/memory_service.py`:

- `InMemoryPermissionService()`
- Stores permissions in `dict[(agent_id, schema_name), PermissionInfo]`
- Stores admin state in `dict[str, AgentInfo]`
- Same interface, same admin bypass logic
- Used when `NEOCORTEX_MOCK_DB=true`

#### 1.8 — Wire into ServiceContext

Update `src/neocortex/services.py`:

- Add `permissions: PostgresPermissionService | InMemoryPermissionService` to `ServiceContext`
- In `create_services()`:
  - Mock mode: create `InMemoryPermissionService()`, then `await permissions.ensure_admin(settings.bootstrap_admin_id)`
  - Real mode: create `PostgresPermissionService(pg)`, then `await permissions.ensure_admin(settings.bootstrap_admin_id)`
- This guarantees the bootstrap admin exists in `agent_registry` on every startup

#### 1.8 — Unit tests

Create `tests/unit/test_permissions_service.py`:

- Test `InMemoryPermissionService`:
  - `grant` creates permission, `revoke` removes it
  - `can_read_schema` / `can_write_schema` return correct booleans
  - `list_for_agent` / `list_for_schema` return correct entries
  - Admin agent always returns `True` for `can_read` / `can_write`
  - Non-existent permission returns `False`
  - `grant` with update (change `can_read` from False to True)

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
- Wired into ServiceContext for both mock and real DB modes
- Unit tests for InMemoryPermissionService
```

---

## Stage 2: GraphRouter Permission Enforcement

**Goal**: The router filters shared schemas by read permission and adds a method for targeted writes to shared schemas with write permission checks.

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

#### 2.2 — Filter `route_recall()` by read permission

In `route_recall()`, after fetching shared graphs, filter:

```python
async def route_recall(self, agent_id: str) -> list[str]:
    agent_graphs = await self._schema_mgr.list_graphs(agent_id=agent_id)
    shared_graphs = await self._schema_mgr.list_graphs(agent_id="shared")

    # Filter shared graphs by read permission (admins pass all)
    accessible_shared = []
    for g in shared_graphs:
        if await self._permissions.can_read_schema(agent_id, g.schema_name):
            accessible_shared.append(g)

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

Also update `MemoryRepository` protocol with the new method signature.

#### 2.5 — Update `route_discover()` to respect read permissions

Same filtering as `route_recall()` — agents only discover schemas they can read.

#### 2.6 — Tests

Create `tests/unit/test_router_permissions.py`:

- Router with InMemoryPermissionService
- Agent with no shared permissions → `route_recall` returns only personal schemas
- Agent with read on `ncx_shared__knowledge` → `route_recall` includes it
- Agent without write → `route_store_to` raises `PermissionError`
- Agent with write → `route_store_to` succeeds
- Admin agent → bypasses all checks

### Verification

```bash
uv run pytest tests/unit/test_router_permissions.py -v
uv run pytest tests/ -v
```

### Commit

```
feat(permissions): enforce read/write permissions in GraphRouter

- route_recall filters shared schemas by read permission
- route_store_to validates write permission for targeted shared writes
- Admin agents bypass permission checks
- GraphServiceAdapter.store_episode_to for directed shared writes
```

---

## Stage 3: Ingestion API Permission Enforcement

**Goal**: Ingestion endpoints accept an optional `target_graph` parameter. When provided, validate that the agent has write permission to the specified shared schema. When absent, default to personal schema (current behavior).

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

#### 3.3 — Processor handles target_graph

Update `EpisodeProcessor.process_text()` (and siblings) to accept optional `target_schema: str | None`. When provided, use `repo.store_episode_to(agent_id, target_schema, ...)` instead of `repo.store_episode(agent_id, ...)`.

#### 3.4 — Wire permissions into ingestion app

In `src/neocortex/ingestion/app.py`, add `app.state.permissions = ctx["permissions"]` during lifespan.

#### 3.5 — Tests

Create `tests/unit/test_ingestion_permissions.py`:

- Agent without write permission → 403 when `target_graph` is set
- Agent with write permission → 200, episode stored in target schema
- Admin agent → bypasses permission check
- No `target_graph` → stores to personal (existing behavior unchanged)
- Invalid `target_graph` (not a shared schema) → 403 or 404

### Verification

```bash
uv run pytest tests/unit/test_ingestion_permissions.py -v
uv run pytest tests/ -v
```

### Commit

```
feat(permissions): enforce write permissions in ingestion API

- target_graph parameter on /ingest/text, /ingest/document, /ingest/events
- 403 when agent lacks write access to target shared schema
- EpisodeProcessor.process_text routes to target schema when specified
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
    if not permissions.is_admin(agent_id):
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

- Non-admin agent → 403 on all `/admin/` endpoints
- Admin grants read permission → verify via list
- Admin grants write permission → verify agent can now write
- Admin revokes permission → verify agent can no longer read/write
- Admin creates shared graph → appears in list
- Admin drops shared graph → permissions cascade-deleted
- Update permission (grant with changed flags) → reflects new state
- Admin promotes agent to admin → new admin can access `/admin/` endpoints
- Admin demotes agent → demoted agent gets 403 on `/admin/`
- Bootstrap admin cannot be demoted (safety check)

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
```

---

## Stage 5: End-to-End Validation & Documentation

**Goal**: Integration tests covering the full permission flow, CLAUDE.md update, and cleanup.

### Steps

#### 5.1 — Integration test: full permission lifecycle

Create `tests/integration/test_permission_flow.py` (uses `InMemoryRepository` + `InMemoryPermissionService`):

1. Admin creates shared graph `ncx_shared__research`
2. Admin grants agent "alice" `can_read=True, can_write=True` on it
3. Admin grants agent "bob" `can_read=True, can_write=False` on it
4. Alice ingests text with `target_graph="ncx_shared__research"` → success
5. Bob ingests text with `target_graph="ncx_shared__research"` → 403
6. Alice recalls → sees `ncx_shared__research` in accessible schemas
7. Bob recalls → sees `ncx_shared__research` in accessible schemas (read OK)
8. Unauthorized agent "eve" recalls → does NOT see `ncx_shared__research`
9. Admin revokes alice's write → alice ingestion now 403
10. Admin drops graph → all permissions gone

#### 5.2 — Verify mock DB mode

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

#### 5.3 — Update CLAUDE.md

Add permission system to the Architecture Rules section:

```
**6. Shared schema access requires explicit permissions.**
graph_permissions table controls read/write access per agent per shared schema.
GraphRouter filters by can_read; ingestion validates can_write.
Admin agents (is_admin in agent_registry) bypass all permission checks.
Bootstrap admin seeded from NEOCORTEX_BOOTSTRAP_ADMIN_ID on every startup.
PermissionChecker protocol has PG and in-memory implementations.
```

#### 5.4 — Update codebase map in CLAUDE.md

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
feat(permissions): integration tests and documentation

- End-to-end permission lifecycle test
- Mock DB mode validation
- CLAUDE.md updated with permission architecture rules
```

---

## Progress Tracker

| Stage | Description | Status | Notes |
|-------|-------------|--------|-------|
| 1 | Permission data model, service layer & wiring | PENDING | |
| 2 | GraphRouter permission enforcement | PENDING | |
| 3 | Ingestion API permission enforcement | PENDING | |
| 4 | Admin REST API | PENDING | |
| 5 | End-to-end validation & documentation | PENDING | |

Last stage completed: —
Last updated by: —

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
- `tests/unit/test_ingestion_permissions.py`
- `tests/unit/test_admin_api.py`
- `tests/integration/test_permission_flow.py`

### Modified files
- `src/neocortex/mcp_settings.py` — add `bootstrap_admin_id`, `admin_token`
- `src/neocortex/services.py` — add `permissions` to `ServiceContext`
- `src/neocortex/graph_router.py` — accept `PermissionChecker`, filter by permissions
- `src/neocortex/db/protocol.py` — add `store_episode_to()` method
- `src/neocortex/db/adapter.py` — implement `store_episode_to()`
- `src/neocortex/db/mock.py` — implement `store_episode_to()` + permission awareness
- `src/neocortex/ingestion/models.py` — add `target_graph` field
- `src/neocortex/ingestion/routes.py` — permission check before processing
- `src/neocortex/ingestion/app.py` — wire permissions + admin router
- `src/neocortex/ingestion/episode_processor.py` — accept `target_schema` param
- `CLAUDE.md` — architecture rules + codebase map update
