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
SchemaManager (NEW)             GraphService (UNCHANGED)
    |  create/drop/list            |  admin-level CRUD (public schema)
    |  schemas, provision          |  NOT used in multi-graph hot path
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

**Key insight**: The adapter already executes raw SQL on scoped connections for `store_episode`, `recall`, and `get_stats`. GraphService is only used as a fallback when no pool is available (mock mode). The multi-graph adapter continues this pattern -- all hot-path queries are raw SQL on schema-scoped connections. GraphService stays unchanged as the admin API.

### Key Files Affected

| File | Change |
|------|--------|
| `migrations/init/006_graph_registry.sql` | NEW: graph_registry table in public |
| `migrations/templates/graph_schema.sql` | NEW: SQL template for graph schema provisioning |
| `src/neocortex/schema_manager.py` | NEW: Schema lifecycle management |
| `src/neocortex/graph_router.py` | NEW: Heuristic routing layer |
| `src/neocortex/db/adapter.py` | MODIFY: use GraphRouter for multi-schema fan-out |
| `src/neocortex/db/scoped.py` | MODIFY: add schema-scoped connections alongside role-scoped |
| `src/neocortex/db/protocol.py` | MINOR: protocol stays, implementations change |
| `src/neocortex/server.py` | MODIFY: wire SchemaManager + GraphRouter in lifespan |
| `src/neocortex/schemas/memory.py` | MODIFY: add source_kind + graph_name to RecallItem |
| `src/neocortex/auth/dev.py` | MODIFY: multi-token auth from JSON file |
| `src/neocortex/mcp_settings.py` | MODIFY: add dev_tokens_file setting |
| `src/neocortex/auth/dependencies.py` | MODIFY: resolve agent_id from multi-token map |
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

2. Create `migrations/templates/graph_schema.sql` -- a pure reference file (NOT in `init/`, NOT auto-executed). This is the DDL template that `SchemaManager` will execute dynamically for each new graph:
   - `CREATE SCHEMA IF NOT EXISTS {schema_name}`
   - All table definitions from `002_schema.sql` but in the new schema
   - All indexes from `003_indexes.sql` but in the new schema
   - Seed ontology from `004_seed_ontology.sql` but in the new schema
   - Conditionally apply RLS from `005_rls_roles.sql` (only if `is_shared=True`)
   - Use `{schema_name}` placeholders for string substitution

3. Create `migrations/templates/` directory. Note: only files in `migrations/init/` are auto-applied by docker-entrypoint. The template is loaded programmatically by `SchemaManager`.

### Verification
- `docker compose down -v && docker compose up -d` -- registry table exists
- `\dt public.*` shows `graph_registry`
- Template SQL file exists at `migrations/templates/graph_schema.sql` with `{schema_name}` placeholders

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

**Goal**: Add schema-scoped connections (`SET search_path`) alongside the existing role-scoped connections. Keep role-scoping only for shared graphs.

### Steps

1. Modify `src/neocortex/db/scoped.py`:
   - Keep existing `scoped_connection` (renamed to `role_scoped_connection`)
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

2. Add `_validate_schema_name(name)` -- must match `^ncx_[a-z0-9]+__[a-z0-9_]+$` pattern (enforces the `ncx_{agent}__{purpose}` structure with required double-underscore separator).

3. Modify `src/neocortex/postgres_service.py`:
   - Add helper: `async def execute_in_schema(self, schema_name: str, query: str, *args)`
   - This is convenience for one-off queries in a specific schema

### Verification
- Unit test: `_validate_schema_name` accepts `ncx_alice__personal`, rejects `ncx___`, `ncx_`, `public`, `ncx_a`
- Integration test: create schema, use `schema_scoped_connection`, verify queries hit correct schema
- Integration test: shared schema uses both search_path AND role

### Commit
`feat(multi-graph): add schema-scoped connection helpers`

---

## Stage 4: GraphRouter (Heuristic Routing Layer)

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

## Stage 5: Multi-Graph Adapter

**Goal**: Rewrite `GraphServiceAdapter` to use `GraphRouter` for multi-graph operations. Fix `RecallItem` schema for mixed node/episode provenance. Use parallel fan-out for recall.

### Steps

1. Fix `src/neocortex/schemas/memory.py` -- `RecallItem` must handle both nodes and episodes cleanly:
   ```python
   class RecallItem(BaseModel):
       item_id: int                          # was node_id -- generic ID (node or episode)
       name: str
       content: str
       item_type: str                        # was node_type -- "Episode" or a node type name
       score: float = Field(..., description="Hybrid relevance score")
       source: str | None = None
       source_kind: Literal["node", "episode"]  # NEW: disambiguates what item_id refers to
       graph_name: str | None = None            # NEW: which graph schema this came from
   ```
   Note: `node_id` → `item_id` and `node_type` → `item_type` are renames. Update all references in adapter, tools, tests, and mock.

2. Update `DiscoverResult`:
   ```python
   class DiscoverResult(BaseModel):
       node_types: list[TypeInfo]
       edge_types: list[TypeInfo]
       stats: GraphStats
       graphs: list[str] = []    # NEW: schemas accessible to this agent
   ```

3. Rewrite `src/neocortex/db/adapter.py`:
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
               row = await conn.fetchrow(
                   """INSERT INTO episode (agent_id, content, source_type, metadata)
                      VALUES ($1, $2, $3, $4::jsonb) RETURNING id""",
                   agent_id, content, source_type, json.dumps(metadata),
               )
           return int(row["id"])

       async def recall(self, query, agent_id, limit) -> list[RecallItem]:
           schemas = await self._router.route_recall(agent_id)
           # Parallel fan-out across schemas
           tasks = [
               self._recall_in_schema(schema, query, limit)
               for schema in schemas
           ]
           results_per_schema = await asyncio.gather(*tasks)
           all_results = [item for batch in results_per_schema for item in batch]
           # Deduplicate, re-rank, truncate to limit
           all_results.sort(key=lambda r: r.score, reverse=True)
           return all_results[:limit]

       async def _recall_in_schema(self, schema, query, limit) -> list[RecallItem]:
           async with schema_scoped_connection(self._pool, schema) as conn:
               # Full-text search on nodes
               node_rows = await conn.fetch(...)
               # ILIKE search on episodes
               episode_rows = await conn.fetch(...)
               # Type name lookup
               type_rows = await conn.fetch("SELECT id, name FROM node_type")
           type_names = {int(r["id"]): str(r["name"]) for r in type_rows}
           # Build RecallItems with source_kind="node"|"episode" and graph_name=schema
           ...

       async def get_node_types(self, agent_id: str | None = None) -> list[TypeInfo]:
           # Aggregate across all accessible schemas
           ...

       async def get_edge_types(self, agent_id: str | None = None) -> list[TypeInfo]:
           ...

       async def get_stats(self, agent_id) -> GraphStats:
           # Sum across all accessible schemas
           ...
   ```

4. Update `src/neocortex/db/protocol.py` -- `MemoryRepository` protocol signatures stay the same. The `RecallItem` field renames are transparent to callers since they access by name.

5. Update `src/neocortex/db/mock.py` (`InMemoryRepository`) -- adapt to the new `RecallItem` field names (`item_id`, `item_type`, `source_kind`).

6. Update `src/neocortex/tools/discover.py` -- pass `graphs` list from router into `DiscoverResult`.

### Verification
- Integration test: create 2 schemas, store data in each, recall merges results from both
- Test: results include `graph_name` provenance and correct `source_kind`
- Test: discover aggregates stats across schemas and lists accessible graphs

### Commit
`feat(multi-graph): rewrite adapter for multi-graph routing and fan-out recall`

---

## Stage 6: Multi-Token Dev Auth

**Goal**: Replace the single dev-token with a JSON file mapping multiple tokens to agent IDs, so different agents can be tested without switching auth modes.

### Steps

1. Create `dev_tokens.json` at project root:
   ```json
   {
     "alice-token": "alice",
     "bob-token": "bob",
     "shared-token": "shared",
     "dev-token-neocortex": "dev-user"
   }
   ```

2. Modify `src/neocortex/mcp_settings.py`:
   ```python
   class MCPSettings(BaseSettings):
       # ... existing fields ...

       # Dev-token auth (used when auth_mode = "dev_token")
       dev_token: str = "dev-token-neocortex"       # DEPRECATED: kept for single-token compat
       dev_user_id: str = "dev-user"                 # DEPRECATED: kept for single-token compat
       dev_tokens_file: str = ""                      # Path to JSON mapping {token: agent_id}
   ```

3. Modify `src/neocortex/auth/dev.py`:
   ```python
   import json
   from pathlib import Path

   class DevTokenAuth(AuthProvider):
       """Multi-token auth for development and agent testing."""

       def __init__(self, settings: MCPSettings):
           super().__init__(base_url=settings.oauth_base_url)
           self._token_map: dict[str, str] = {}

           # Load from JSON file if configured
           if settings.dev_tokens_file:
               tokens_path = Path(settings.dev_tokens_file)
               if tokens_path.exists():
                   self._token_map = json.loads(tokens_path.read_text())

           # Fallback: single legacy token
           if not self._token_map:
               self._token_map = {settings.dev_token: settings.dev_user_id}

       async def verify_token(self, token: str) -> AccessToken | None:
           agent_id = self._token_map.get(token)
           if agent_id is None:
               return None

           return AccessToken(
               token=token,
               client_id="neocortex-dev-client",
               scopes=["openid"],
               claims={"sub": agent_id},
           )
   ```

4. Update `docker-compose.yml` for the `neocortex-mcp` service:
   ```yaml
   environment:
     NEOCORTEX_AUTH_MODE: "dev_token"
     NEOCORTEX_DEV_TOKENS_FILE: "/app/dev_tokens.json"
   volumes:
     - ./dev_tokens.json:/app/dev_tokens.json:ro
   ```

5. The `get_agent_id_from_context` in `dependencies.py` already extracts `claims["sub"]` from the token -- no changes needed there. The multi-token map makes `verify_token` return different `sub` claims per token.

### Verification
- Unit test: `DevTokenAuth` with multi-token file resolves alice-token → "alice", bob-token → "bob"
- Unit test: unknown token returns `None`
- Unit test: fallback to single legacy token when no file configured
- Manual test: `curl -H "Authorization: Bearer alice-token" http://localhost:8000/...` resolves as agent "alice"

### Commit
`feat(auth): support multiple dev tokens mapped to agent IDs via JSON file`

---

## Stage 7: Server Wiring & Auto-Provisioning

**Goal**: Wire `SchemaManager` and `GraphRouter` into the server lifespan. Create shared graph on startup. Auto-provision agent graphs on first use.

### Steps

1. Modify `src/neocortex/server.py` lifespan:
   ```python
   @asynccontextmanager
   async def app_lifespan(server):
       if settings.mock_db:
           # Mock mode: unchanged -- InMemoryRepository, no SchemaManager/Router
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

2. The `GraphRouter.route_store()` already auto-creates the agent's personal graph on first use. No additional wiring needed for auto-provisioning.

3. Mock mode (`InMemoryRepository`) is intentionally left as-is -- single-graph, no routing. It continues to work for unit tests via the `MemoryRepository` protocol. Multi-graph behavior is only tested via integration tests with real PostgreSQL.

### Verification
- Server starts, `ncx_shared__knowledge` schema is created automatically
- First `remember` call from a new agent creates their `ncx_{agent}__personal` schema
- Health check still works
- Mock mode still works (`NEOCORTEX_MOCK_DB=true`)
- All existing unit tests pass (they use mock mode)

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
   - `test_recall_provenance` -- RecallItem.graph_name and source_kind set correctly
   - `test_discover_aggregates_stats` -- stats sum across schemas
   - `test_discover_lists_graphs` -- DiscoverResult.graphs populated
   - `test_schema_isolation` -- data in schema A not in schema B

4. Create `tests/test_dev_token_auth.py`:
   - `test_multi_token_from_file` -- loads JSON, resolves tokens to agent IDs
   - `test_unknown_token_rejected` -- returns None
   - `test_fallback_single_token` -- works when no file configured

5. Update `tests/mcp/test_rls.py`:
   - Adapt to shared schema context
   - Test RLS only applies to shared schemas

6. Update `tests/mcp/conftest.py`:
   - Add fixtures for multi-graph setup (SchemaManager, GraphRouter)

### Verification
- `uv run pytest tests/ -v` -- all tests pass
- Coverage for new modules > 80%

### Commit
`test(multi-graph): add comprehensive tests for schema manager, router, adapter, and auth`

---

## Stage 10: E2E Validation & Smoke Test

**Goal**: End-to-end validation that the full MCP server works with multi-graph routing and multi-agent identity.

### Steps

1. Create `scripts/e2e_smoke_test.py` -- automated validation script:
   ```python
   """E2E smoke test for multi-graph architecture.

   Prerequisites:
     docker compose up -d postgres
     NEOCORTEX_AUTH_MODE=dev_token NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
       uv run python -m neocortex

   Usage:
     uv run python scripts/e2e_smoke_test.py
   """
   import asyncio
   import httpx

   BASE_URL = "http://localhost:8000"
   ALICE_TOKEN = "alice-token"
   BOB_TOKEN = "bob-token"

   async def main():
       async with httpx.AsyncClient() as client:
           # 1. Health check
           r = await client.get(f"{BASE_URL}/health")
           assert r.status_code == 200

           # 2. Alice stores a memory
           r = await mcp_call(client, ALICE_TOKEN, "remember",
                              {"text": "Alice likes pizza"})
           assert r["episode_id"] > 0

           # 3. Bob stores a memory
           r = await mcp_call(client, BOB_TOKEN, "remember",
                              {"text": "Bob likes sushi"})
           assert r["episode_id"] > 0

           # 4. Alice recalls -- sees her own data, not Bob's
           r = await mcp_call(client, ALICE_TOKEN, "recall",
                              {"query": "pizza"})
           assert any("pizza" in item["content"].lower() for item in r["results"])
           assert not any("sushi" in item["content"].lower() for item in r["results"])

           # 5. Bob recalls -- sees his own data, not Alice's
           r = await mcp_call(client, BOB_TOKEN, "recall",
                              {"query": "sushi"})
           assert any("sushi" in item["content"].lower() for item in r["results"])
           assert not any("pizza" in item["content"].lower() for item in r["results"])

           # 6. Alice discovers -- shows her graph + shared
           r = await mcp_call(client, ALICE_TOKEN, "discover", {})
           assert "ncx_alice__personal" in r["graphs"]

           # 7. Verify schema isolation in DB directly
           # (optional: query PG to confirm schemas exist)

       print("ALL CHECKS PASSED")

   asyncio.run(main())
   ```
   Note: The `mcp_call` helper should use the appropriate MCP client protocol (HTTP SSE or streamable-http) to call tools with the bearer token.

2. Manual verification (if MCP client protocol is complex):
   - `docker compose down -v && docker compose up -d` -- clean start
   - Start MCP server: `NEOCORTEX_AUTH_MODE=dev_token NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json uv run python -m neocortex`
   - Use `curl` or an MCP inspector to call tools with different bearer tokens
   - Verify schema isolation by querying PostgreSQL directly:
     ```sql
     \dn ncx_*
     SELECT * FROM ncx_alice__personal.episode;
     SELECT * FROM ncx_bob__personal.episode;
     ```

3. Verify all existing tests still pass: `uv run pytest tests/ -v`

### Verification
- Automated script passes OR manual steps 1-7 verified
- No errors in server logs
- Schemas `ncx_alice__personal`, `ncx_bob__personal`, `ncx_shared__knowledge` exist
- Data isolation confirmed: Alice's data not in Bob's schema and vice versa

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
| 4 | GraphRouter (Heuristic Routing) | TODO | |
| 5 | Multi-Graph Adapter | DONE | Multi-schema adapter rewrite, recall provenance fields, discover graph aggregation, and Stage 5 tests added. |
| 6 | Multi-Token Dev Auth | TODO | |
| 7 | Server Wiring & Auto-Provisioning | DONE | Wired `SchemaManager` and `GraphRouter` into server lifespan, auto-provisioned the shared graph at startup, and verified first-write agent graph creation. |
| 8 | RLS Cleanup | DONE | Shared-schema RLS now provisions grants/policies only for shared graphs, shared reads use graph-scoped roles, and RLS tests target shared schemas while private schemas stay owner-role free. |
| 9 | Tests | TODO | |
| 10 | E2E Validation & Smoke Test | TODO | |

**Last stage completed**: N/A
**Last updated by**: Plan revision (2026-03-27) -- review fixes applied

## Automation Progress Tracker

| # | Stage | Status | Notes | Updated |
|---|-------|--------|-------|---------|
| 1 | Graph Registry & Schema Template SQL | DONE | Added `graph_registry`, created `migrations/templates/graph_schema.sql`, verified registry in Postgres, and ran `poetry run pytest`. | 2026-03-27 |
| 2 | SchemaManager | DONE | Added `SchemaManager`, `GraphInfo`, schema template loading/provisioning, registry-backed create/list/drop/default helpers, and Stage 2 tests; `poetry run pytest` passed. | 2026-03-27 |
| 3 | Schema-Scoped Connections | DONE | Added role/schema/graph scoped connection helpers, schema validation, `execute_in_schema`, and Stage 3 integration tests; `poetry run pytest` passed. | 2026-03-27 |
| 4 | GraphRouter (Heuristic Routing) | DONE | Added `GraphRouter` MVP routing heuristics with personal-first recall/discover fan-out and Stage 4 unit tests; `poetry run pytest` passed. | 2026-03-27 |
| 5 | Multi-Graph Adapter | DONE | Rewrote the adapter for router-driven schema fan-out, added `RecallItem` provenance fields and discover graph aggregation, and verified with `poetry run pytest`. | 2026-03-27 |
| 6 | Multi-Token Dev Auth | DONE | Added JSON-backed multi-token dev auth, mounted `dev_tokens.json` in Docker Compose, and added Stage 6 auth tests; `poetry run pytest` passed. | 2026-03-27 |
| 7 | Server Wiring & Auto-Provisioning | DONE | Wired `SchemaManager` and `GraphRouter` into server lifespan, auto-created `ncx_shared__knowledge` on startup, added a server lifespan integration test, and `poetry run pytest` passed. | 2026-03-27 |
| 8 | RLS Cleanup | DONE | Shared-schema RLS now provisions grants/policies only for shared graphs, shared reads use graph-scoped roles, and shared-schema/private-schema coverage was updated; `poetry run pytest` passed. | 2026-03-27 |
| 9 | Tests | DONE | Added missing GraphRouter and multi-graph adapter coverage, added MCP multi-graph fixtures, and verified with `poetry run pytest` plus `uv run pytest tests/ -v`; `pytest-cov` was not available in the Poetry environment for the >80% coverage check. | 2026-03-27 |
| 10 | E2E Validation & Smoke Test | DONE | Added `scripts/e2e_smoke_test.py`, validated live multi-agent isolation against the running server, updated the stale discover expectation, and verified with `poetry run pytest` plus `uv run pytest tests/ -v`. | 2026-03-27 |

**Last stage completed**: E2E Validation & Smoke Test
**Last updated by**: plan-runner-agent
