# Plan 04: Multi-Graph Architecture via PostgreSQL Schemas

## Overview

Replace the single-graph architecture (all data in `public` schema with RLS row filtering) with **isolated PostgreSQL schemas** for each agent/purpose combination. Each schema contains a complete copy of the graph table structure with independent ontology, sequences, and indexes. Tools remain unchanged externally; an internal **GraphRouter** heuristic layer decides which schema(s) to read/write.

### Design Decisions (from clarification)

| Decision | Choice |
|----------|--------|
| Graph scope | **Agent x Purpose** -- each agent can have multiple named graphs |
| Tool API | **Opaque** -- tools unchanged; heuristics route internally |
| Ontology | **Per-graph** -- each schema has its own node_type/edge_type |
| RLS | **Shared graphs only** -- per-agent schemas have no RLS |

### Schema Naming Convention

```
ncx_{agent_id}__{purpose}     -- per-agent graphs (double underscore separates agent from purpose)
ncx_shared__{purpose}          -- shared graphs (agent_id = "shared")

Examples:
  ncx_alice__personal
  ncx_alice__research
  ncx_bob__personal
  ncx_shared__knowledge
```

### Architecture After This Change

```
MCP Tools (remember, recall, discover)
    |  (unchanged API)
    v
GraphRouter (NEW)
    |  heuristics: which graph(s) to target?
    |  remember -> agent's default personal graph
    |  recall   -> fan-out across agent's graphs + shared, merge/rerank
    |  discover -> aggregate across accessible graphs
    v
SchemaManager (NEW)             GraphService (MODIFIED)
    |  create/drop/list            |  now schema-aware
    |  schemas, provision          |  SET search_path per operation
    |  tables + indexes            |
    v                              v
          PostgreSQL
  public/                     ncx_alice__personal/     ncx_shared__knowledge/
    graph_registry              node_type                node_type (+ RLS)
    _migration                  edge_type                edge_type (+ RLS)
                                node                     node      (+ RLS)
                                edge                     edge      (+ RLS)
                                episode                  episode   (+ RLS)
```

### Key Files Affected

| File | Change |
|------|--------|
| `migrations/init/006_graph_registry.sql` | NEW: graph_registry table in public |
| `migrations/init/007_schema_template.sql` | NEW: SQL template for graph schema provisioning |
| `src/neocortex/schema_manager.py` | NEW: Schema lifecycle management |
| `src/neocortex/graph_router.py` | NEW: Heuristic routing layer |
| `src/neocortex/graph_service.py` | MODIFY: schema-aware (search_path) |
| `src/neocortex/postgres_service.py` | MODIFY: add schema-scoped connection helper |
| `src/neocortex/db/adapter.py` | MODIFY: use GraphRouter instead of single GraphService |
| `src/neocortex/db/scoped.py` | MODIFY: schema-scoped connections replace role-scoped |
| `src/neocortex/db/protocol.py` | MINOR: protocol stays, implementations change |
| `src/neocortex/server.py` | MODIFY: wire SchemaManager + GraphRouter in lifespan |
| `src/neocortex/schemas/memory.py` | MINOR: add graph_name to RecallItem for provenance |
| `migrations/init/005_rls_roles.sql` | MODIFY: only apply RLS during shared schema provisioning |

---

## Stage 1: Graph Registry & Schema Template SQL

**Goal**: Create the foundation -- a registry to track all graphs and a SQL template that can provision a new graph schema.

### Steps

1. Create `migrations/init/006_graph_registry.sql`:
   ```sql
   CREATE TABLE IF NOT EXISTS graph_registry (
       id          SERIAL PRIMARY KEY,
       agent_id    TEXT NOT NULL,              -- "alice", "bob", "shared"
       purpose     TEXT NOT NULL,              -- "personal", "research", "knowledge"
       schema_name TEXT UNIQUE NOT NULL,       -- "ncx_alice__personal"
       is_shared   BOOLEAN DEFAULT FALSE,      -- shared graphs get RLS
       created_at  TIMESTAMPTZ DEFAULT now(),
       UNIQUE (agent_id, purpose)
   );
   ```

2. Create `migrations/init/007_schema_template.sql` -- a pure reference file (NOT executed at init). This is the DDL template that `SchemaManager` will execute dynamically for each new graph:
   - `CREATE SCHEMA IF NOT EXISTS {schema_name}`
   - All table definitions from `002_schema.sql` but in the new schema
   - All indexes from `003_indexes.sql` but in the new schema
   - Seed ontology from `004_seed_ontology.sql` but in the new schema
   - Conditionally apply RLS from `005_rls_roles.sql` (only if `is_shared=True`)
   - Use `{schema_name}` placeholders for string substitution

3. Update `docker-compose.yml`: ensure `006_graph_registry.sql` is applied at init (it already will be since it's in `migrations/init/`). The `007_schema_template.sql` should NOT be auto-applied -- rename or move it to indicate it's a template (e.g., `migrations/templates/graph_schema.sql`).

### Verification
- `docker compose down -v && docker compose up -d` -- registry table exists
- `\dt public.*` shows `graph_registry`
- Template SQL file exists and contains valid DDL with `{schema_name}` placeholders

### Commit
`feat(multi-graph): add graph registry table and schema provisioning template`

---

## Stage 2: SchemaManager

**Goal**: Python class that creates, drops, lists, and provisions graph schemas using the SQL template.

### Steps

1. Create `src/neocortex/schema_manager.py`:
   ```python
   class SchemaManager:
       def __init__(self, pg: PostgresService)

       async def create_graph(self, agent_id: str, purpose: str, is_shared: bool = False) -> str:
           """Create a new graph schema. Returns schema_name."""
           # 1. Generate schema_name: ncx_{sanitize(agent_id)}__{sanitize(purpose)}
           # 2. Check graph_registry for duplicates
           # 3. Read template SQL, substitute {schema_name}
           # 4. Execute DDL in transaction
           # 5. If is_shared: apply RLS policies
           # 6. Register in graph_registry
           # 7. Return schema_name

       async def drop_graph(self, schema_name: str) -> bool:
           """Drop a graph schema and remove from registry."""
           # DROP SCHEMA {schema_name} CASCADE
           # DELETE FROM graph_registry WHERE schema_name = ...

       async def list_graphs(self, agent_id: str | None = None) -> list[GraphInfo]:
           """List registered graphs, optionally filtered by agent."""
           # SELECT * FROM graph_registry WHERE ...

       async def get_graph(self, agent_id: str, purpose: str) -> GraphInfo | None:
           """Look up a specific graph."""

       async def ensure_default_graphs(self, agent_id: str) -> str:
           """Ensure agent has at least a 'personal' graph. Create if missing. Return schema_name."""

       @staticmethod
       def make_schema_name(agent_id: str, purpose: str) -> str:
           """Generate schema name: ncx_{agent_id}__{purpose}"""
   ```

2. Create `src/neocortex/schemas/graph.py` (or add to existing schemas):
   ```python
   class GraphInfo(BaseModel):
       id: int
       agent_id: str
       purpose: str
       schema_name: str
       is_shared: bool
       created_at: datetime
   ```

3. The template SQL should be loaded from `migrations/templates/graph_schema.sql` using `importlib.resources` or a simple file read relative to project root. For Docker, bundle the template in the image.

### Verification
- Unit test: `SchemaManager.make_schema_name("alice", "personal")` == `"ncx_alice__personal"`
- Integration test (requires Docker PG): create graph, verify schema exists, verify tables exist within schema, drop graph, verify gone
- Test duplicate detection (creating same agent+purpose twice raises or returns existing)

### Commit
`feat(multi-graph): add SchemaManager for graph schema lifecycle`

---

## Stage 3: Schema-Scoped Connections

**Goal**: Replace role-scoped connections (`SET LOCAL ROLE`) with schema-scoped connections (`SET search_path`). Keep role-scoping only for shared graphs.

### Steps

1. Modify `src/neocortex/db/scoped.py`:
   - Rename `scoped_connection` to `role_scoped_connection` (keep for shared graphs)
   - Add new `schema_scoped_connection(pool, schema_name)` context manager:
     ```python
     @asynccontextmanager
     async def schema_scoped_connection(pool: asyncpg.Pool, schema_name: str):
         """Run queries with search_path set to a specific graph schema."""
         _validate_schema_name(schema_name)
         async with pool.acquire() as conn, conn.transaction():
             await conn.execute(f"SET LOCAL search_path TO {schema_name}, public")
             yield conn
     ```
   - Add `graph_scoped_connection(pool, schema_name, agent_id=None)` that combines both:
     - Sets `search_path` to schema
     - If the schema is shared: also sets role via `SET LOCAL ROLE`
     - If per-agent schema: only sets search_path

2. Add `_validate_schema_name(name)` -- must match `^ncx_[a-z0-9_]+$` pattern.

3. Modify `src/neocortex/postgres_service.py`:
   - Add helper: `async def execute_in_schema(self, schema_name: str, query: str, *args)`
   - This is convenience for one-off queries in a specific schema

### Verification
- Unit test: `_validate_schema_name` accepts valid names, rejects bad ones
- Integration test: create schema, use `schema_scoped_connection`, verify queries hit correct schema
- Integration test: shared schema uses both search_path AND role

### Commit
`feat(multi-graph): add schema-scoped connection helpers`

---

## Stage 4: Schema-Aware GraphService

**Goal**: Make `GraphService` operate within a specific schema by accepting a connection/schema parameter.

### Steps

1. Modify `src/neocortex/graph_service.py`:
   - Add `schema_name: str | None = None` to `__init__`. When set, all queries use schema-qualified table names OR the service operates within a pre-scoped connection.
   - **Approach**: Rather than schema-qualifying every table name in SQL (fragile), the `GraphService` should receive a pre-scoped `asyncpg.Connection` (where `search_path` is already set). This means `GraphService` methods should accept an optional `conn` parameter:
     ```python
     async def create_node(self, ..., conn: asyncpg.Connection | None = None) -> Node:
         # If conn provided, use it (already scoped to correct schema)
         # If not, use self._pg (legacy behavior, public schema)
     ```
   - Alternatively (simpler): Create a **factory** that produces a `GraphService` bound to a specific schema connection:
     ```python
     class ScopedGraphService:
         """GraphService operating within a specific schema."""
         def __init__(self, conn: asyncpg.Connection):
             self._conn = conn
         # Same methods as GraphService but use self._conn directly
     ```
   - **Recommended**: Use the connection-passing approach. Each method in `GraphService` gets an optional `conn` parameter. When `None`, it falls back to `self._pg` (current behavior). When provided, it uses the pre-scoped connection.

2. This is a refactor of `GraphService` internals. External API stays the same but gains `conn` parameter on each method.

3. Ensure all SQL queries use unqualified table names (which they already do). The `search_path` handles schema routing.

### Verification
- Existing tests still pass (conn=None falls back to current behavior)
- New test: create schema, scope connection, create node via GraphService with conn -- verify node is in correct schema
- Test: nodes in schema A are not visible when querying schema B

### Commit
`refactor(graph-service): add optional conn parameter for schema-scoped operations`

---

## Stage 5: GraphRouter (Heuristic Routing Layer)

**Goal**: New component that decides which graph schema(s) to use for each operation type. This is the brain that keeps tool API opaque.

### Steps

1. Create `src/neocortex/graph_router.py`:
   ```python
   class GraphRouter:
       """Routes memory operations to appropriate graph schema(s)."""

       def __init__(self, schema_mgr: SchemaManager, pool: asyncpg.Pool):
           self._schema_mgr = schema_mgr
           self._pool = pool

       async def route_store(self, agent_id: str) -> str:
           """Determine which schema to store a new episode/memory in.
           Returns schema_name.

           Heuristic (MVP):
             - Always store to agent's 'personal' graph
             - Auto-create if doesn't exist
           """
           graph = await self._schema_mgr.get_graph(agent_id, "personal")
           if graph is None:
               return await self._schema_mgr.create_graph(agent_id, "personal")
           return graph.schema_name

       async def route_recall(self, agent_id: str) -> list[str]:
           """Determine which schemas to search during recall.
           Returns list of schema_names to fan-out across.

           Heuristic (MVP):
             - Search all agent's own graphs
             - Search all shared graphs
             - Return list ordered by priority (personal first, then shared)
           """
           agent_graphs = await self._schema_mgr.list_graphs(agent_id=agent_id)
           shared_graphs = await self._schema_mgr.list_graphs(agent_id="shared")
           schemas = [g.schema_name for g in agent_graphs]
           schemas += [g.schema_name for g in shared_graphs]
           return schemas

       async def route_discover(self, agent_id: str) -> list[str]:
           """Determine which schemas to include in ontology discovery.
           Same as recall routing -- show everything accessible.
           """
           return await self.route_recall(agent_id)
   ```

2. The router is intentionally simple for MVP. Heuristics can be made more sophisticated later:
   - Store routing could analyze content to decide personal vs. research graph
   - Recall routing could weight schemas differently
   - LLM-based routing (post-hackathon)

### Verification
- Unit test: mock SchemaManager, verify route_store creates personal graph on first call
- Unit test: route_recall returns agent graphs + shared graphs
- Unit test: route_discover returns same as route_recall

### Commit
`feat(multi-graph): add GraphRouter heuristic routing layer`

---

## Stage 6: Multi-Graph Adapter

**Goal**: Rewrite `GraphServiceAdapter` to use `GraphRouter` for multi-graph operations. This is the integration point where everything comes together.

### Steps

1. Rewrite `src/neocortex/db/adapter.py`:
   ```python
   class GraphServiceAdapter:
       def __init__(self, graph: GraphService, router: GraphRouter,
                    pool: asyncpg.Pool, pg: PostgresService):
           self._graph = graph
           self._router = router
           self._pool = pool
           self._pg = pg

       async def store_episode(self, agent_id, content, context, source_type) -> int:
           schema = await self._router.route_store(agent_id)
           async with schema_scoped_connection(self._pool, schema) as conn:
               # INSERT INTO episode using conn (search_path set to schema)
               ...

       async def recall(self, query, agent_id, limit) -> list[RecallItem]:
           schemas = await self._router.route_recall(agent_id)
           all_results = []
           for schema in schemas:
               async with schema_scoped_connection(self._pool, schema) as conn:
                   # Full-text + episode search in this schema
                   results = await self._recall_in_schema(conn, query, schema, limit)
                   all_results.extend(results)
           # Deduplicate, re-rank, truncate to limit
           all_results.sort(key=lambda r: r.score, reverse=True)
           return all_results[:limit]

       async def get_node_types(self) -> list[TypeInfo]:
           # Aggregate across all accessible schemas
           ...

       async def get_edge_types(self) -> list[TypeInfo]:
           ...

       async def get_stats(self, agent_id) -> GraphStats:
           # Sum across all accessible schemas
           ...
   ```

2. Add `graph_name` field to `RecallItem` schema for provenance (which graph did this result come from):
   - Modify `src/neocortex/schemas/memory.py`: add `graph_name: str | None = None` to `RecallItem`

3. Update `DiscoverResult` to include per-graph breakdown:
   - Add `graphs: list[str]` field showing which graphs the agent has access to

### Verification
- Integration test: create 2 schemas, store data in each, recall merges results from both
- Test: results include `graph_name` provenance
- Test: discover aggregates stats across schemas

### Commit
`feat(multi-graph): rewrite adapter for multi-graph routing and fan-out recall`

---

## Stage 7: Server Wiring & Auto-Provisioning

**Goal**: Wire `SchemaManager` and `GraphRouter` into the server lifespan. Create shared graph on startup. Auto-provision agent graphs on first use.

### Steps

1. Modify `src/neocortex/server.py` lifespan:
   ```python
   @asynccontextmanager
   async def app_lifespan(server):
       if settings.mock_db:
           repo = InMemoryRepository()
           yield {"repo": repo, "settings": settings}
           return

       pg = PostgresService(PostgresConfig())
       await pg.connect()
       try:
           graph = GraphService(pg)
           schema_mgr = SchemaManager(pg)
           # Ensure shared knowledge graph exists
           await schema_mgr.create_graph("shared", "knowledge", is_shared=True)
           router = GraphRouter(schema_mgr, pg.pool)
           repo = GraphServiceAdapter(graph, router=router, pool=pg.pool, pg=pg)
           yield {"repo": repo, "pg": pg, "graph": graph,
                  "schema_mgr": schema_mgr, "router": router, "settings": settings}
       finally:
           await pg.disconnect()
   ```

2. The `GraphRouter.route_store()` already auto-creates the agent's personal graph on first use (via `SchemaManager.ensure_default_graphs`). No additional wiring needed for auto-provisioning.

3. Update `InMemoryRepository` to also support multi-graph semantics (or keep it simple with single-graph mock -- acceptable for testing).

### Verification
- Server starts, shared knowledge graph schema is created automatically
- First `remember` call from a new agent creates their personal graph schema
- Health check still works
- Mock mode still works

### Commit
`feat(multi-graph): wire SchemaManager and GraphRouter into server lifespan`

---

## Stage 8: RLS Cleanup

**Goal**: Remove RLS from per-agent schemas. Keep it only on shared graph schemas. Clean up dead code.

### Steps

1. Modify `migrations/templates/graph_schema.sql`:
   - Split RLS section into a conditional block that's only applied when `{is_shared}` is true
   - Per-agent schemas: no `owner_role` column, no RLS policies, no `neocortex_agent` role grants
   - Shared schemas: full RLS setup (owner_role, policies, role grants)

2. The `SchemaManager.create_graph()` already passes `is_shared` flag -- use it to control which DDL sections run.

3. Update `src/neocortex/db/scoped.py`:
   - `graph_scoped_connection` checks registry `is_shared` flag
   - Shared: sets both `search_path` AND `SET LOCAL ROLE`
   - Per-agent: sets only `search_path`

4. Keep `roles.py` (still needed for shared graph role management). Remove `owner_role` references from per-agent code paths.

5. The old `005_rls_roles.sql` init migration is now dead code for the `public` schema. Since we're moving all graph data to named schemas, we can leave it in place (harmless) or gate it.

### Verification
- Per-agent schema: no `owner_role` column on node/edge/episode tables
- Shared schema: `owner_role` column exists, RLS policies active
- Agent A cannot see Agent B's data in shared schema (RLS works)
- Agent can freely read/write own schema (no RLS overhead)

### Commit
`refactor(multi-graph): apply RLS only to shared graph schemas`

---

## Stage 9: Tests

**Goal**: Comprehensive test coverage for multi-graph architecture.

### Steps

1. Create `tests/test_schema_manager.py`:
   - `test_make_schema_name` -- naming convention
   - `test_create_graph` -- schema + tables created (requires Docker PG)
   - `test_create_duplicate_graph` -- idempotent or raises
   - `test_drop_graph` -- schema removed, registry cleaned
   - `test_list_graphs` -- filter by agent_id
   - `test_ensure_default_graphs` -- creates personal on first call, noop on second

2. Create `tests/test_graph_router.py`:
   - `test_route_store_creates_personal_graph`
   - `test_route_store_returns_existing_graph`
   - `test_route_recall_includes_agent_and_shared`
   - `test_route_recall_no_shared_graphs` -- only agent graphs returned

3. Create `tests/test_multi_graph_adapter.py`:
   - `test_store_in_agent_schema` -- episode lands in correct schema
   - `test_recall_merges_across_schemas` -- results from personal + shared
   - `test_recall_provenance` -- RecallItem.graph_name set correctly
   - `test_discover_aggregates_stats` -- stats sum across schemas
   - `test_schema_isolation` -- data in schema A not in schema B

4. Update `tests/mcp/test_rls.py`:
   - Adapt to shared schema context
   - Test RLS only applies to shared schemas

5. Update `tests/mcp/conftest.py`:
   - Add fixtures for multi-graph setup (SchemaManager, GraphRouter)

### Verification
- `poetry run pytest tests/ -v` -- all tests pass
- Coverage for new modules > 80%

### Commit
`test(multi-graph): add comprehensive tests for schema manager, router, and adapter`

---

## Stage 10: Validation & Integration Smoke Test

**Goal**: End-to-end validation that the full MCP server works with multi-graph routing.

### Steps

1. `docker compose down -v && docker compose up -d` -- clean start
2. Start MCP server: `python -m neocortex`
3. Call `remember(text="Alice likes pizza")` as agent "alice"
   - Verify: `ncx_alice__personal` schema created
   - Verify: episode stored in `ncx_alice__personal.episode`
4. Call `remember(text="Shared fact: PostgreSQL supports pgvector")` as agent "alice"
   - Verify: stored in `ncx_alice__personal` (router default)
5. Call `recall(query="pizza")` as agent "alice"
   - Verify: result found from personal schema
6. Call `discover()` as agent "alice"
   - Verify: stats reflect agent's graph + shared graph
7. Repeat with agent "bob" -- verify complete isolation
8. Verify shared graph is visible to both agents in recall

### Verification
- All 8 steps pass
- No errors in server logs
- Existing test suite still passes

### Commit
`docs(plan): mark stage 10 as DONE in multi-graph schemas plan`

---

## Execution Protocol

This plan is designed for sequential, stage-by-stage execution. Each stage is independently committable and testable.

### Pre-flight
- Ensure Docker PostgreSQL is running: `docker compose up -d postgres`
- Ensure dependencies installed: `uv sync`
- Verify clean git state: `git status`

### Per-Stage Loop
1. Read stage steps
2. Implement changes
3. Run verification (tests, manual checks)
4. Update progress tracker
5. Commit with specified message + `Co-Authored-By`
6. Proceed to next stage

### If Blocked
- Document the issue in the tracker
- If assumption is wrong, revise affected stages
- Do not proceed past a blocked stage

---

## Progress Tracker

| Stage | Description | Status | Notes |
|-------|-------------|--------|-------|
| 1 | Graph Registry & Schema Template SQL | TODO | |
| 2 | SchemaManager | TODO | |
| 3 | Schema-Scoped Connections | TODO | |
| 4 | Schema-Aware GraphService | TODO | |
| 5 | GraphRouter (Heuristic Routing) | TODO | |
| 6 | Multi-Graph Adapter | TODO | |
| 7 | Server Wiring & Auto-Provisioning | TODO | |
| 8 | RLS Cleanup | TODO | |
| 9 | Tests | TODO | |
| 10 | Validation & Integration Smoke Test | TODO | |

**Last stage completed**: N/A
**Last updated by**: Plan creation (2026-03-27)
