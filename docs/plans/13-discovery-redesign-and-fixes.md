# Plan 13 — Discovery Redesign, Domain Fixes, Extraction Context, TUI Rebuild

> **Status:** DRAFT
> **Created:** 2026-03-28
> **Issues addressed:** E2E report #1 (seed schemas), #2 (ontology contamination), #3 (discover bloat)
> **Scope:** MCP tool redesign, domain provisioning fix, extraction context fix, TUI rebuild

## Overview

The E2E validation (Report 01) revealed three issues that degrade the system's reliability and usability:

1. **Seed domain schemas not provisioned** — domain routing silently drops all content because seed domains reference PG schemas that don't exist.
2. **Ontology contamination** — extraction agents reuse semantically wrong types (Serotonin → DatabaseSystem) because no domain context is passed to the prompt.
3. **Discover tool dumps ~4000 tokens** — 150+ node types flat, no per-graph breakdown, no incremental exploration.

Additionally, the TUI needs rebuilding to support the new granular discovery tools.

## Design Decisions (from clarification)

- **Ontology contamination fix**: Domain context in extraction prompt (cheapest, no schema changes).
- **Discovery detail level**: Schema metadata + 3-5 sample node names per type.
- **Seed schema permissions**: Shared schemas (`is_shared=true` in `graph_registry`) are readable by all agents. Write requires explicit grant.
- **TUI**: Redesign to support new tool API (not a crash fix — structural redesign).
- **Discovery is a breaking MCP API change**: The single `discover` tool is removed and replaced by 4 granular tools. Existing clients calling `discover` will get "tool not found".

## New MCP Tool Design

Replace single `discover` with 4 incremental tools:

```
Agent exploration flow:
  discover_domains  →  discover_graphs  →  discover_ontology  →  discover_details
  "What domains?"       "What graphs?"       "Types in graph X"    "Details of type Y"
  ~200 tokens            ~300 tokens           ~200-500 tokens       ~300-500 tokens
```

| Tool | Parameters | Returns |
|------|-----------|---------|
| `discover_domains` | _(none)_ | List of semantic domains: slug, name, description, schema_name |
| `discover_graphs` | _(none)_ | List of accessible graphs with per-graph stats (nodes, edges, episodes) |
| `discover_ontology` | `graph_name: str` | Node types + edge types for ONE graph (name, description, count) |
| `discover_details` | `type_name: str, graph_name: str, kind: "node"\|"edge"` | Type metadata + connected types + 3-5 sample names |

---

## Stages

### Stage 1: Fix Seed Domain Schema Provisioning

**Goal**: Seed domains' PG schemas exist on startup, registered in `graph_registry`, readable by all agents via the existing `is_shared` flag.

**Root cause**: `services.py:99` calls `domain_svc.seed_defaults()` which writes rows to `ontology_domains` with `schema_name` values, but `schema_mgr.create_graph()` is never called for those schemas. When `_ensure_schema` (router.py:158) checks `domain.schema_name is not None`, it returns early — assuming the schema exists.

**Files to modify**:
- `src/neocortex/services.py` — After `seed_defaults()`, provision PG schemas for each seed domain.
- `src/neocortex/domains/router.py` — Fix `_ensure_schema` to validate schema actually exists in `graph_registry`.
- `src/neocortex/permissions/pg_service.py` — `can_read_schema` returns True for shared schemas (`is_shared=true` in `graph_registry`).
- `src/neocortex/permissions/memory_service.py` — `can_read_schema` returns True for schemas in a `_shared_schemas` set (populated by callers).

**Design note — why no `grant_read_to_all`**: The `graph_registry` already has an `is_shared` column. Shared schemas are, by definition, world-readable. Using this existing flag avoids adding a new protocol method, a new DB column (`public_read`), and bulk permission grants. Only write access requires explicit `graph_permissions` rows.

**Steps**:

1. **Make `can_read_schema` respect `is_shared`** in `PostgresPermissionService` (`permissions/pg_service.py`):
   ```python
   async def can_read_schema(self, agent_id: str, schema_name: str) -> bool:
       if await self.is_admin(agent_id):
           return True
       # Shared schemas are world-readable
       row = await self._pool.fetchrow(
           "SELECT 1 FROM graph_registry WHERE schema_name = $1 AND is_shared = true",
           schema_name,
       )
       if row is not None:
           return True
       # Fall back to explicit grant
       row = await self._pool.fetchrow(
           "SELECT 1 FROM graph_permissions WHERE agent_id = $1 AND schema_name = $2 AND can_read = true",
           agent_id, schema_name,
       )
       return row is not None
   ```
   Apply the same logic to `readable_schemas` (batch method): union shared schemas with explicitly granted ones.

2. **Make `can_read_schema` respect shared schemas** in `InMemoryPermissionService` (`permissions/memory_service.py`):
   - Add a `_shared_schemas: set[str]` field (default empty).
   - Add a `register_shared_schema(schema_name: str)` method to populate it.
   - In `can_read_schema`, return True if `schema_name in self._shared_schemas`.
   - In `readable_schemas`, include `_shared_schemas & candidates`.

3. **Provision seed schemas in `services.py`** — After `domain_svc.seed_defaults()`, add:
   ```python
   # Provision PG schemas for seed domains
   from neocortex.domains.models import SEED_DOMAINS
   for domain in SEED_DOMAINS:
       if domain.schema_name:
           await schema_mgr.create_graph(
               agent_id="shared", purpose=domain.slug, is_shared=True
           )
   ```
   `create_graph` is idempotent (returns existing schema name on subsequent boots). No permission grants needed — `is_shared=true` in `graph_registry` gives read access to all.

4. **Fix `_ensure_schema`** in `domains/router.py` — When `domain.schema_name` is set, verify the schema exists in `graph_registry` via the schema manager. If not found, fall through to creation:
   ```python
   async def _ensure_schema(self, domain: SemanticDomain, agent_id: str) -> str | None:
       if domain.schema_name is not None:
           # Verify schema actually exists (seed domains may have name but no schema)
           if self._schema_mgr is not None:
               existing = await self._schema_mgr.get_graph(
                   agent_id="shared", purpose=domain.slug
               )
               if existing is not None:
                   return domain.schema_name
               # Schema name set but schema doesn't exist — fall through to create
           else:
               return domain.schema_name
       # ... rest of existing creation logic
   ```

5. **Update tests** — Add test verifying seed schemas are provisioned after `create_services()`.

**Verification**:
- `uv run pytest tests/ -v -k "seed or provision"` passes.
- Start services with real DB → `SELECT * FROM graph_registry WHERE is_shared = true` shows 5 rows (4 seeds + `ncx_shared__knowledge`).
- Verify a non-admin agent can read shared schemas without explicit grant: `can_read_schema("agent_x", "ncx_shared__user_profile")` returns True.

**Commit**: `fix(domains): provision seed domain schemas on bootstrap and use is_shared for read access`

---

### Stage 2: Pass Domain Context to Extraction Pipeline

**Goal**: When extraction runs against a shared domain schema, the ontology and extractor agents receive the domain's name and description so they propose semantically appropriate types.

**Root cause**: `domains/router.py:188` enqueues `extract_episode` with `target_schema` but no domain metadata. The extraction pipeline (`extraction/pipeline.py:83-84`) loads existing types from the target schema, but the ontology agent's system prompt has no concept of "what this schema is for."

**Files to modify**:
- `src/neocortex/jobs/tasks.py` — Add `domain_hint` parameter to `extract_episode` task.
- `src/neocortex/domains/router.py` — Pass domain name+description when enqueuing extraction.
- `src/neocortex/extraction/pipeline.py` — Accept and forward `domain_hint` to agents.
- `src/neocortex/extraction/agents.py` — Add `domain_hint` to deps, inject into prompts.

**Steps**:

1. **Add `domain_hint` to agent deps** (`extraction/agents.py`):
   ```python
   @dataclass
   class OntologyAgentDeps:
       episode_text: str
       existing_node_types: list[str]
       existing_edge_types: list[str]
       domain_hint: str | None = None  # e.g. "Technical Knowledge: Programming languages, ..."

   @dataclass
   class ExtractorAgentDeps:
       episode_text: str
       node_types: list[str]
       edge_types: list[str]
       domain_hint: str | None = None
   ```
   (LibrarianAgentDeps doesn't need it — it works with already-typed entities.)

2. **Inject domain context into ontology agent prompt** (`agents.py`, `inject_context`):
   ```python
   # At the start of inject_context for ontology agent:
   parts = []
   if ctx.deps.domain_hint:
       parts.extend([
           f"Domain context: {ctx.deps.domain_hint}",
           "Propose types that are semantically appropriate for this domain.",
           "Do NOT reuse types from unrelated domains even if they exist.",
           "",
       ])
   parts.extend(["Text to analyze:", ctx.deps.episode_text, ...])
   ```

3. **Inject domain context into extractor agent prompt** (`agents.py`):
   Same pattern — add domain context at the top of `inject_context`.

4. **Accept `domain_hint` in `run_extraction`** (`extraction/pipeline.py`):
   ```python
   async def run_extraction(
       ...,
       domain_hint: str | None = None,
   ) -> None:
   ```
   Pass through to `OntologyAgentDeps(domain_hint=domain_hint)` and `ExtractorAgentDeps(domain_hint=domain_hint)`.

5. **Add `domain_hint` to `extract_episode` task** (`jobs/tasks.py`):
   ```python
   async def extract_episode(
       agent_id: str,
       episode_ids: list[int],
       target_schema: str | None = None,
       source_schema: str | None = None,
       domain_hint: str | None = None,  # NEW
   ) -> None:
   ```
   Pass `domain_hint` to `run_extraction()`.

6. **Pass domain info when enqueuing** (`domains/router.py`, `_enqueue_extraction`):
   Update `_enqueue_extraction` to accept `domain_hint`:
   ```python
   async def _enqueue_extraction(
       self, agent_id: str, episode_id: int,
       target_schema: str, domain_hint: str | None = None,
   ) -> int | None:
       if self._job_app is None:
           return None
       job_id = await self._job_app.configure_task("extract_episode").defer_async(
           agent_id=agent_id,
           episode_ids=[episode_id],
           target_schema=target_schema,
           source_schema=None,
           domain_hint=domain_hint,
       )
       return job_id
   ```
   Update `route_and_extract` call site (line ~103) to pass domain hint:
   ```python
   hint = f"{domain.name}: {domain.description}"
   job_id = await self._enqueue_extraction(agent_id, episode_id, schema_name, domain_hint=hint)
   ```
   The `domain` variable is already in scope (fetched at line ~85 in `route_and_extract`).

**Known limitation — existing contaminated types**: This fix prevents *future* contamination. If a shared schema already has semantically wrong types from prior extractions (e.g. `DatabaseSystem` in a health domain), they remain in `existing_node_types` fed to the ontology agent. Options:
- **Manual cleanup**: Drop contaminated types from shared schemas before re-ingesting.
- **Automated filter** (future): Compare existing type names against the domain description using an LLM call — too expensive for a hackathon.

For now, accept the manual cleanup path.

**Verification**:
- `uv run pytest tests/ -v` passes (existing tests unaffected — `domain_hint=None` is default).
- Add test in `test_extraction_pipeline.py`: when `domain_hint` is set, ontology agent deps include it.
- Manual: ingest health content → check `technical_knowledge` schema → types should be health-appropriate, not reused from tech domain.

**Commit**: `feat(extraction): pass domain context to ontology and extractor agents`

---

### Stage 3: New Discovery Response Models and Protocol Extensions

**Goal**: Define response schemas and repository/service methods needed by the 4 new discovery tools.

**Files to modify**:
- `src/neocortex/schemas/memory.py` — Add new response models.
- `src/neocortex/db/protocol.py` — Add `get_graph_stats` method (per-graph stats).
- `src/neocortex/db/adapter.py` — Implement per-graph stats.
- `src/neocortex/db/mock.py` — Implement per-graph stats for mock.
- `src/neocortex/domains/router.py` — Add `list_domains()` convenience method.

**Steps**:

1. **Add response models** (`schemas/memory.py`):

   **Note**: `GraphInfo` already exists in `schemas/graph.py` (used by `SchemaManager`). The discovery model is named `GraphSummary` to avoid collision.

   ```python
   class DomainInfo(BaseModel):
       slug: str
       name: str
       description: str
       schema_name: str | None = None

   class GraphSummary(BaseModel):
       """Discovery-facing graph info (not to be confused with schemas.graph.GraphInfo)."""
       schema_name: str
       is_shared: bool
       purpose: str
       stats: GraphStats

   class TypeDetail(BaseModel):
       id: int
       name: str
       description: str | None = None
       count: int = 0
       connected_edge_types: list[str] = []  # edge types where this node type participates
       sample_names: list[str] = []           # 3-5 sample node/edge names

   class DiscoverDomainsResult(BaseModel):
       domains: list[DomainInfo]
       message: str | None = None  # e.g. "Domain routing is not enabled"

   class DiscoverGraphsResult(BaseModel):
       graphs: list[GraphSummary]

   class DiscoverOntologyResult(BaseModel):
       graph_name: str
       node_types: list[TypeInfo]
       edge_types: list[TypeInfo]
       stats: GraphStats

   class DiscoverDetailsResult(BaseModel):
       graph_name: str
       type_detail: TypeDetail
   ```

2. **Add `get_stats_for_schema` to protocol** (`db/protocol.py`):
   ```python
   async def get_stats_for_schema(
       self, agent_id: str, schema_name: str
   ) -> GraphStats:
       """Return stats for a single schema."""
   ```

3. **Add `get_type_detail` to protocol** (`db/protocol.py`):
   ```python
   async def get_type_detail(
       self, agent_id: str, type_name: str, graph_name: str, kind: str
   ) -> TypeDetail | None:
       """Return detailed info for a single type: description, connected types, sample names."""
   ```

4. **Implement `get_stats_for_schema` in adapter** (`db/adapter.py`):
   - Extract the existing `_get_stats_in_schema` private method's return value.
   - Wrap it in the public method with schema validation.

5. **Implement `get_type_detail` in adapter** (`db/adapter.py`):
   - For `kind="node"`: query `node_type` by name, then JOIN to find connected edge types, sample 5 node names.
   - For `kind="edge"`: query `edge_type` by name, then JOIN to find source/target node types, sample 5 edge signatures.

6. **Implement both in mock** (`db/mock.py`):
   - `get_stats_for_schema`: return stats from `_nodes`/`_edges`/`_episodes`.
   - `get_type_detail`: build from in-memory data.

7. **Add `list_domains` to `DomainRouter`** (`domains/router.py`):
   ```python
   async def list_domains(self) -> list[SemanticDomain]:
       return await self._domain_service.list_domains()
   ```

**Verification**:
- `uv run pytest tests/ -v` passes.
- Add unit test for `get_type_detail` with mock repo.

**Commit**: `feat(schemas): add discovery response models and protocol extensions`

---

### Stage 4: Replace Discover with 4 Granular MCP Tools

**Goal**: Replace single `discover` tool with `discover_domains`, `discover_graphs`, `discover_ontology`, `discover_details`.

**Breaking change**: This removes the `discover` tool from the MCP surface. Existing clients will get "tool not found". The TUI is updated in Stage 5.

**Files to modify**:
- `src/neocortex/tools/discover.py` — Replace with 4 tool functions.
- `src/neocortex/tools/__init__.py` — Register new tools, remove old.

**Steps**:

1. **Rewrite `discover.py`** with 4 functions:

   ```python
   async def discover_domains(ctx: Context | None = None) -> DiscoverDomainsResult:
       """List semantic knowledge domains (upper ontology).
       Shows what broad categories of knowledge exist and which graphs store them.
       Call this first to understand the knowledge landscape.
       """

   async def discover_graphs(ctx: Context | None = None) -> DiscoverGraphsResult:
       """List all knowledge graphs accessible to you, with per-graph statistics.
       Each graph has node/edge/episode counts (returned as GraphSummary).
       Use graph names with discover_ontology to drill into a specific graph.
       """

   async def discover_ontology(
       graph_name: str, ctx: Context | None = None
   ) -> DiscoverOntologyResult:
       """Show the entity types and relationship types in a specific graph.
       Returns node types and edge types with counts. Use discover_details
       to drill into a specific type.
       """

   async def discover_details(
       type_name: str,
       graph_name: str,
       kind: str = "node",
       ctx: Context | None = None,
   ) -> DiscoverDetailsResult:
       """Get detailed information about a specific type in a graph.
       Returns the type's description, connected types, and sample entity names.
       kind: 'node' for entity types, 'edge' for relationship types.
       """
   ```

2. **Implement `discover_domains`**:
   - Get `domain_router` from lifespan context.
   - If present: call `list_domains()`, map to `DomainInfo`.
   - If None (domains disabled): return `DiscoverDomainsResult(domains=[], message="Domain routing is not enabled")`.

3. **Implement `discover_graphs`**:
   - Use `repo.list_graphs(agent_id)` to get schema names.
   - For each: call `repo.get_stats_for_schema(agent_id, schema_name)`.
   - Get `schema_mgr` from lifespan context (`ctx.lifespan_context["schema_mgr"]` — it's already in `ServiceContext`). Use `schema_mgr.list_graphs()` to look up `purpose` and `is_shared` per schema. If `schema_mgr` is None (mock mode), parse purpose from schema name (strip `ncx_{agent}__` prefix) and assume `is_shared=False`.

4. **Implement `discover_ontology`**:
   - Call `repo.get_node_types(agent_id, target_schema=graph_name)`.
   - Call `repo.get_edge_types(agent_id, target_schema=graph_name)`.
   - Call `repo.get_stats_for_schema(agent_id, graph_name)`.

5. **Implement `discover_details`**:
   - Call `repo.get_type_detail(agent_id, type_name, graph_name, kind)`.

6. **Update `__init__.py`** — Register all 4 new tools, remove old `discover`.

**Verification**:
- `uv run pytest tests/mcp/ -v` passes.
- Update `test_tools.py` to test new tools (discover_domains, discover_graphs, discover_ontology, discover_details).
- Manual: call each tool via MCP client, verify response structure and token count.
- **Note**: `InMemoryRepository.list_graphs()` returns `[]`, so mock-mode testing of `discover_graphs` will return empty results. MCP tool tests should seed the mock repo with synthetic graph data or test with real DB.

**Commit**: `feat(tools): replace discover with 4 granular discovery tools`

---

### Stage 5: TUI Rebuild for Granular Discovery

**Goal**: Rebuild TUI to support the new 4-tool discovery API with drill-down navigation.

**Files to modify**:
- `src/neocortex/tui/client.py` — Add methods for all 4 discovery tools.
- `src/neocortex/tui/app.py` — Redesign discover mode with breadcrumb navigation.

**Steps**:

1. **Update `NeoCortexClient`** (`client.py`):
   - Remove `discover()` method.
   - Add `discover_domains()`, `discover_graphs()`, `discover_ontology(graph_name)`, `discover_details(type_name, graph_name, kind)`.

2. **Redesign discover mode** in `app.py`:
   - Replace single "Fetch Ontology" button with a multi-level explorer.
   - **Level 0** (landing): Two buttons — "Domains" and "Graphs".
   - **Level 1a** (domains): Table listing domains (slug, name, description, schema).
   - **Level 1b** (graphs): Table listing graphs with stats (name, nodes, edges, episodes).
   - **Level 2** (ontology): Click a graph → show node types + edge types tables. Back button.
   - **Level 3** (details): Click a type → show detail panel (description, connected types, samples). Back button.
   - Use a `_discover_stack` list to track navigation breadcrumb.
   - Display breadcrumb as: `Discover > Graphs > ncx_shared__technical_knowledge > Person`
   - Escape key or Back button pops the stack.

3. **Layout changes**:
   - Replace `#discover-area` with a container that includes:
     - Breadcrumb label at top.
     - Action buttons (Domains / Graphs at level 0, Back at deeper levels).
     - Results area (reuse DataTable for tabular data, Static for detail text).

4. **Keyboard shortcuts** for discovery navigation:
   - `b` — back (pop stack).
   - `Enter` on selected table row — drill down.

**Verification**:
- `NEOCORTEX_MOCK_DB=true uv run python -m neocortex` (start server).
- `python -m neocortex.tui` (start TUI) → navigate Domains → Graphs → Ontology → Details.
- Verify each level renders correctly and back navigation works.

**Commit**: `feat(tui): rebuild discovery UI with multi-level drill-down navigation`

---

### Stage 6: Tests and Validation

**Goal**: Ensure all changes are covered by tests and the system works end-to-end.

**Steps**:

1. **Run full test suite**: `uv run pytest tests/ -v` — all pass.
2. **Add test for seed domain provisioning** (`tests/unit/test_seed_provisioning.py`):
   - Mock DB create_services → verify `create_graph` called for each seed domain.
   - Verify `can_read_schema` returns True for shared schemas without explicit grant (via `is_shared` flag).
3. **Add test for domain context in extraction** (`tests/unit/test_extraction_domain_context.py`):
   - Run extraction with `domain_hint` set → verify ontology agent deps include it.
   - Run extraction without `domain_hint` → verify backward compatibility.
4. **Update MCP tool tests** (`tests/mcp/test_tools.py`):
   - Test `discover_domains` returns empty list with mock repo.
   - Test `discover_graphs` returns list with mock repo.
   - Test `discover_ontology` with a graph name returns types.
   - Test `discover_details` with a type name returns detail.
5. **Verify no regressions**: `uv run pytest tests/ -v` — all pass.

**Verification**:
- `uv run pytest tests/ -v` — all tests pass.
- No import errors or missing symbols.

**Commit**: `test: add coverage for discovery redesign and domain provisioning`

---

## Execution Protocol

1. Read plan fully before starting.
2. Execute stages in order (1→6). Each stage is independently committable.
3. Run `uv run pytest tests/ -v` after each stage to verify no regressions.
4. If a stage fails, diagnose and fix before proceeding. Update the plan's Issues section.
5. One commit per stage.

## Progress Tracker

| Stage | Description | Status | Notes |
|-------|------------|--------|-------|
| 1 | Fix seed domain schema provisioning | DONE | is_shared flag for world-readable shared schemas, seed schema provisioning on bootstrap, _ensure_schema validates existence |
| 2 | Domain context in extraction pipeline | DONE | domain_hint added to OntologyAgentDeps, ExtractorAgentDeps, run_extraction, extract_episode task, and DomainRouter._enqueue_extraction |
| 3 | Discovery response models + protocol | DONE | Added DomainInfo, GraphSummary, TypeDetail, DiscoverDomainsResult/GraphsResult/OntologyResult/DetailsResult models; get_stats_for_schema + get_type_detail on protocol/adapter/mock; list_domains on DomainRouter |
| 4 | Replace discover with 4 granular tools | DONE | discover_domains, discover_graphs, discover_ontology, discover_details; updated server instructions, tests, and multi-graph adapter test |
| 5 | TUI rebuild | DONE | Rebuilt client with 4 discovery methods; app with multi-level drill-down (landing→domains/graphs→ontology→details), breadcrumb nav, back button |
| 6 | Tests and validation | IN_PROGRESS | |

**Last stage completed:** Stage 5 — TUI rebuild
**Last updated by:** plan-runner-agent

## Issues

_(None yet)_
