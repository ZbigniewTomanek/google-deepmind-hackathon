# Plan 07 — Extraction Pipeline Integration & PoC Finalization

> **Goal**: Wire the 3-agent extraction pipeline (ontology → extraction → librarian) into the
> NeoCortex MCP server so that ingested text is automatically enriched into a knowledge graph.
> Deliver a functional PoC where a user can ingest medical-domain data, recall memories with
> graph-traversal context, and explore the resulting ontology via the TUI.

## Overview

Plans 00–06 built all the infrastructure: PostgreSQL storage, MCP server, multi-schema isolation,
ingestion API, embeddings, hybrid recall, and a developer TUI. The 3-agent extraction pipeline
exists only as a standalone SQLite playground demo (Plan 00). This plan bridges the gap:

1. Expose graph mutation operations through `MemoryRepository` protocol
2. Integrate Procrastinate (PostgreSQL-native async job queue) for background processing
3. Port and generalize the extraction pipeline to work with NeoCortex's async/PostgreSQL stack
4. Create a medical-domain seed corpus (neurology, pharmacy, sexual function)
5. Wire extraction into `remember` and ingestion flows via async jobs
6. Enhance `recall` with node matching + configurable-depth edge traversal
7. Update TUI and run end-to-end validation

## Architecture After This Plan

```
User (TUI / API / MCP Client)
  │
  ├─ remember(text) ──► store_episode() ──► enqueue extraction job
  │                                              │
  ├─ POST /ingest/text ──► store_episode() ──────┘
  │                                              │
  │                              ┌───────────────┘
  │                              ▼
  │                     ┌─────────────────┐
  │                     │  Procrastinate    │
  │                     │  (async worker)  │
  │                     └────────┬────────┘
  │                              │
  │                 ┌────────────▼────────────┐
  │                 │  Extraction Pipeline     │
  │                 │  ┌──────────────────┐   │
  │                 │  │ 1. Ontology Agent│   │  ─► upsert node/edge types
  │                 │  │ 2. Extractor     │   │  ─► create nodes + edges
  │                 │  │ 3. Librarian     │   │  ─► deduplicate & persist
  │                 │  └──────────────────┘   │
  │                 └─────────────────────────┘
  │
  ├─ recall(query) ──► hybrid episode search
  │                  + node vector/text search
  │                  + N-hop edge traversal on matched nodes
  │                  ──► merged, scored results
  │
  └─ discover() ───► ontology types + counts + sample entities
```

## Data Model Mapping: Playground → NeoCortex

| Playground Model | NeoCortex Model | Table | Key Difference |
|---|---|---|---|
| `OntologyClass` | `NodeType` | `node_type` | String ID → integer PK, lookup by name |
| `OntologyProperty` | `EdgeType` | `edge_type` | String ID → integer PK, lookup by name |
| `ExtractedEntity` | `Node` | `node` | `class_id` → `type_id` (int FK), properties in JSONB |
| `ExtractedFact` (entity-valued) | `Edge` | `edge` | subject/target → `source_id`/`target_id` (int FK) |
| `ExtractedFact` (scalar-valued) | `Node.properties` | `node` | Stored as JSONB property on subject node |
| `SeedMessage` | `Episode` | `episode` | `message_id` → `id`, adds `agent_id` |
| `FactMention` | `Edge.properties.mentions[]` | `edge` | Provenance stored in edge JSONB |

**Key design decision**: Scalar-valued facts (string, number, boolean, date) become properties
on the subject node rather than edges to synthetic value-nodes. Only entity-valued facts become
edges. This keeps the graph clean and queryable.

---

## Stage 1: Extend MemoryRepository Protocol for Graph Mutations

### Purpose
Expose `GraphService`'s node/edge/type CRUD through the `MemoryRepository` protocol so the
extraction pipeline (and future tools) can manipulate the knowledge graph without breaking the
protocol abstraction.

### Steps

1. **Add methods to `MemoryRepository` protocol** (`src/neocortex/db/protocol.py`)

   New methods (all async, all require `agent_id` for schema routing):

   ```python
   # ── Type Management ──
   async def get_or_create_node_type(
       self, agent_id: str, name: str, description: str | None = None
   ) -> NodeType: ...

   async def get_or_create_edge_type(
       self, agent_id: str, name: str, description: str | None = None
   ) -> EdgeType: ...

   # ── Episode Read (needed by extraction pipeline in Stage 4) ──
   async def get_episode(
       self, agent_id: str, episode_id: int
   ) -> Episode | None: ...
   """Fetch a single episode. Adapter queries the agent's personal schema."""

   # ── Node CRUD ──
   async def upsert_node(
       self, agent_id: str, name: str, type_id: int,
       content: str | None = None, properties: dict | None = None,
       embedding: list[float] | None = None, source: str | None = None,
   ) -> Node: ...
   """Upsert by (name, type_id) within the agent's schema.
   If a node with the same name AND type_id exists, merge properties and update.
   Name alone is NOT the uniqueness key — the same name under different types
   creates separate nodes (e.g. 'Serotonin' as Neurotransmitter vs Drug)."""

   async def find_nodes_by_name(
       self, agent_id: str, name: str
   ) -> list[Node]: ...
   """Return all nodes matching `name` (case-insensitive) across all types.
   May return multiple results if the same name exists under different types."""

   # ── Edge CRUD ──
   async def upsert_edge(
       self, agent_id: str, source_id: int, target_id: int,
       type_id: int, weight: float = 1.0, properties: dict | None = None,
   ) -> Edge: ...
   """Upsert by (source_id, target_id, type_id) within the agent's schema.
   If an edge with the same triple exists, merge properties and update weight.
   This makes extraction retries safe — no duplicate edges on re-processing."""

   # ── Graph Traversal ──
   async def get_node_neighborhood(
       self, agent_id: str, node_id: int, depth: int = 2,
   ) -> list[dict]: ...
   """BFS traversal up to `depth` hops. Returns list of
   {node: Node, edges: list[Edge], distance: int}."""

   # ── Bulk Queries (for extraction pipeline) ──
   async def list_all_node_names(self, agent_id: str) -> list[str]: ...
   async def list_all_edge_signatures(self, agent_id: str) -> list[str]: ...
   ```

2. **Implement in `GraphServiceAdapter`** (`src/neocortex/db/adapter.py`)

   Each method delegates to `GraphService` within a schema-scoped connection.
   - `get_episode`: query by id in the agent's personal schema via `route_store(agent_id)`
   - `get_or_create_node_type`: use `graph.get_node_type_by_name()`, fallback to `graph.create_node_type()`
   - `upsert_node`: query `SELECT id FROM node WHERE name = $1 AND type_id = $2`, then create or update
   - `find_nodes_by_name`: `SELECT * FROM node WHERE lower(name) = lower($1)` — returns list, caller decides
   - `upsert_edge`: `INSERT ... ON CONFLICT (source_id, target_id, type_id) DO UPDATE SET weight = $5, properties = node.properties || $6::jsonb`
   - `get_node_neighborhood`: iterative BFS using `graph.get_neighbors()` up to depth
   - Schema routing: use `self._router.route_store(agent_id)` for writes, fan-out for reads
   - All SQL via `schema_scoped_connection(self._pool, schema_name)`

3. **Implement in `InMemoryRepository`** (`src/neocortex/db/mock.py`)

   First, add `created_at` to `EpisodeRecord` TypedDict so `get_episode` can return
   a proper `Episode` model:
   ```python
   class EpisodeRecord(TypedDict, total=False):
       id: int
       agent_id: str
       content: str
       context: str | None
       source_type: str
       embedding: list[float] | None
       created_at: datetime  # NEW — set to datetime.now(UTC) in store_episode
   ```

   Add in-memory dicts:
   ```python
   self._node_types: dict[str, NodeType] = {}   # keyed by name
   self._edge_types: dict[str, EdgeType] = {}   # keyed by name
   self._nodes: dict[int, Node] = {}             # keyed by id
   self._edges: dict[int, Edge] = {}             # keyed by id
   self._next_node_id = 1
   self._next_edge_id = 1
   self._next_type_id = 1
   ```
   - `get_episode`: lookup in `self._episodes` by id, filter by agent_id, convert to `Episode` model
   - `get_node_neighborhood`: simple BFS over `self._edges`
   - `upsert_node`: lookup by `(name, type_id)` tuple
   - `upsert_edge`: lookup by `(source_id, target_id, type_id)` tuple, update if exists
   - `find_nodes_by_name`: filter `self._nodes` by case-insensitive name match, return list

4. **Unit tests** (`tests/test_protocol_graph_mutations.py`)
   - Test get_episode returns stored episode, None for missing
   - Test upsert_node idempotency (same name+type → same node, merged properties)
   - Test upsert_node with same name but different type_id → two distinct nodes
   - Test get_or_create_node_type idempotency
   - Test find_nodes_by_name returns list (empty, single, multiple types)
   - Test get_node_neighborhood at depth 1, 2, 3
   - Test upsert_edge creates new edge, and upsert with same (source, target, type) updates instead of duplicating
   - Run against `InMemoryRepository`

### Verification
```bash
uv run pytest tests/test_protocol_graph_mutations.py -v
```

### Commit
`feat(db): extend MemoryRepository protocol with graph mutation methods`

---

## Stage 2: Background Jobs via Procrastinate

### Purpose
Provide asynchronous job processing for extraction and other long-running tasks.
Uses [Procrastinate](https://github.com/procrastinate-org/procrastinate) — a PostgreSQL-native,
async-first job queue that handles table management, `FOR UPDATE SKIP LOCKED` claiming,
retry with backoff, and worker lifecycle out of the box. This avoids reimplementing
queue primitives and gives us a clean path to job chaining / dependencies later.

### Why Procrastinate over hand-rolled queue
- **Less code**: no custom migration, no `claim_next_job` SQL, no polling loop, no stale-job reclamation — Procrastinate handles all of it.
- **Retry with backoff**: built-in `RetryStrategy` with exponential backoff, max attempts.
- **In-process worker**: `app.run_worker_async()` embeds directly in our FastMCP/FastAPI lifespan — no extra process to manage.
- **Job chaining**: while not a built-in DAG scheduler, a task handler can `await other_task.defer_async(...)` to chain follow-up jobs. This is sufficient for PoC and cleanly extensible.
- **LISTEN/NOTIFY**: instant job pickup (no polling interval to tune).

### Steps

1. **Add dependency** (`pyproject.toml`)
   ```bash
   uv add "procrastinate[psycopg]"
   ```
   Note: Procrastinate uses psycopg (v3) for async via `PsycopgConnector`. Since we already
   use asyncpg for the main pool, Procrastinate manages its own connection pool internally —
   no conflict.

2. **Create Procrastinate app** (`src/neocortex/jobs/__init__.py`, `tasks.py`)

   `__init__.py` — app factory:
   ```python
   import procrastinate

   def create_job_app(conninfo: str) -> procrastinate.App:
       """Create a Procrastinate app connected to the NeoCortex database."""
       return procrastinate.App(
           connector=procrastinate.PsycopgConnector(conninfo=conninfo),
           import_paths=["neocortex.jobs.tasks"],
       )
   ```

   `tasks.py` — extraction task:
   ```python
   from neocortex.jobs import create_job_app

   # Placeholder app for task registration — replaced at runtime with real conninfo.
   app = procrastinate.App(connector=procrastinate.InMemoryConnector())

   @app.task(
       name="extract_episode",
       retry=procrastinate.RetryStrategy(max_attempts=3, wait=5),
       queue="extraction",
   )
   async def extract_episode(
       agent_id: str,
       episode_ids: list[int],
   ) -> None:
       """Run extraction pipeline for a batch of episodes."""
       from neocortex.jobs.context import get_services
       services = get_services()
       from neocortex.extraction.pipeline import run_extraction
       await run_extraction(
           repo=services["repo"],
           embeddings=services["embeddings"],
           agent_id=agent_id,
           episode_ids=episode_ids,
           model_name=services["settings"].extraction_model,
       )
   ```

   `context.py` — runtime service access for tasks:
   ```python
   """Module-level holder for ServiceContext, set during lifespan."""
   from __future__ import annotations
   from typing import TYPE_CHECKING

   if TYPE_CHECKING:
       from neocortex.services import ServiceContext

   _services: ServiceContext | None = None

   def set_services(ctx: ServiceContext) -> None:
       global _services
       _services = ctx

   def get_services() -> ServiceContext:
       if _services is None:
           raise RuntimeError("Job services not initialized. Was set_services() called in lifespan?")
       return _services
   ```

3. **Add settings** (`src/neocortex/mcp_settings.py`)
   ```python
   extraction_enabled: bool = True        # feature flag
   extraction_model: str = "gemini-2.5-flash"  # LLM model for extraction agents
   ```
   No `job_poll_interval` needed — Procrastinate uses LISTEN/NOTIFY for instant pickup.

4. **Wire into service lifecycle** (`src/neocortex/services.py`)
   ```python
   from neocortex.jobs import create_job_app
   from neocortex.jobs.context import set_services

   # In ServiceContext TypedDict:
   job_app: procrastinate.App | None

   # In create_services():
   if not settings.mock_db and settings.extraction_enabled:
       conninfo = PostgresConfig().dsn  # "postgresql://user:pass@host:port/db"
       job_app = create_job_app(conninfo)
       await job_app.open_async()
       # Apply Procrastinate schema (idempotent)
       await job_app.admin.apply_schema_async()
       set_services(ctx)  # make services available to task handlers
   else:
       job_app = None

   # In shutdown_services():
   job_app = ctx.get("job_app")
   if job_app is not None:
       await job_app.close_async()
   ```

5. **Start worker in MCP server lifespan only** (`src/neocortex/server.py`)

   The extraction worker runs exclusively in the MCP server process. The ingestion API
   only enqueues jobs — it does NOT start a worker. This avoids two workers competing
   for the same jobs when both services run simultaneously.

   ```python
   # In server.py async lifespan, after create_services():
   job_app = ctx["job_app"]
   if job_app is not None:
       worker_task = asyncio.create_task(
           job_app.run_worker_async(queues=["extraction"], install_signal_handlers=False)
       )
       yield
       worker_task.cancel()
       with suppress(asyncio.CancelledError):
           await worker_task
   else:
       yield
   ```

   The ingestion API (`ingestion/app.py`) only needs `job_app` for `defer_async()` calls —
   no `run_worker_async` needed there.

6. **Unit tests** (`tests/test_jobs.py`)
   - Use `procrastinate.InMemoryConnector()` for testing (no Docker needed)
   - Test task registration and deferral
   - Test retry strategy configuration
   - Test `extract_episode` task calls `run_extraction` with correct args (mock pipeline)
   - Test worker start/stop lifecycle via `run_worker_async`

### Verification
```bash
uv run pytest tests/test_jobs.py -v
```

### Commit
`feat(jobs): integrate Procrastinate for async extraction job processing`

---

## Stage 3: Medical Domain Seed Corpus

### Purpose
Create ~10 realistic medical text passages covering neurology, pharmacy, and sexual function.
These replace the BMW corpus and serve as demo data for the PoC.

### Steps

1. **Create corpus module** (`src/neocortex/extraction/corpus.py`)

   ```python
   MEDICAL_SEED_MESSAGES: list[dict] = [
       {
           "id": "med-001",
           "title": "Serotonin and Mood Regulation",
           "topic": "neurology",
           "content": "Serotonin (5-hydroxytryptamine, 5-HT) is a monoamine neurotransmitter..."
       },
       # ... 9 more messages
   ]
   ```

   Topics to cover (ensuring cross-domain connections):

   | ID | Title | Domain | Key Concepts |
   |---|---|---|---|
   | med-001 | Serotonin and Mood Regulation | neurology | serotonin, 5-HT receptors, mood pathways |
   | med-002 | SSRIs: Mechanism and Clinical Use | pharmacy | fluoxetine, sertraline, reuptake inhibition |
   | med-003 | SSRI-Induced Sexual Dysfunction | sexual function | delayed ejaculation, anorgasmia, libido decrease |
   | med-004 | Dopamine Pathways and Reward | neurology | dopamine, mesolimbic pathway, reward circuitry |
   | med-005 | PDE5 Inhibitors in Erectile Dysfunction | pharmacy / sexual function | sildenafil, tadalafil, NO/cGMP pathway |
   | med-006 | Neuroanatomy of Sexual Response | neurology / sexual function | hypothalamus, spinal reflex arcs, autonomic NS |
   | med-007 | Antiepileptic Drugs and Hormonal Effects | pharmacy / sexual function | valproate, carbamazepine, hormone disruption |
   | med-008 | Multiple Sclerosis and Sexual Dysfunction | neurology / sexual function | demyelination, bladder/sexual symptoms |
   | med-009 | Bupropion: Atypical Antidepressant Profile | pharmacy | norepinephrine-dopamine reuptake, lower sexual SE |
   | med-010 | Neuroplasticity and Pharmacological Intervention | neurology / pharmacy | BDNF, synaptic plasticity, ketamine |

   Each message: 150–250 words of factual medical content with specific drug names,
   mechanisms, anatomical structures, and clinical relationships.

2. **Create CLI ingest command** (`src/neocortex/extraction/cli.py`)

   ```python
   async def ingest_seed_corpus(
       base_url: str = "http://localhost:8001",
       token: str | None = None,
   ) -> None:
       """POST each seed message to /ingest/text endpoint."""
   ```

   Runnable as: `uv run python -m neocortex.extraction.cli --ingest-corpus`

### Verification
```bash
uv run python -c "from neocortex.extraction.corpus import MEDICAL_SEED_MESSAGES; print(len(MEDICAL_SEED_MESSAGES))"
# Should print 10
```

### Commit
`feat(extraction): add medical domain seed corpus (neurology, pharmacy, sexual function)`

---

## Stage 4: Extraction Pipeline Module

### Purpose
Port the 3-agent extraction pipeline from the playground to NeoCortex. Make it async,
PostgreSQL-backed, and domain-agnostic.

### Steps

1. **Create extraction package** (`src/neocortex/extraction/__init__.py`)

2. **Adapted schemas** (`src/neocortex/extraction/schemas.py`)

   Bridge models that map between LLM output and NeoCortex's data model:

   ```python
   # ── LLM Output Schemas (what agents produce) ──

   class ProposedNodeType(BaseModel):
       """Ontology agent proposes new node types."""
       name: str = Field(description="PascalCase type name, e.g. 'Neurotransmitter'")
       description: str

   class ProposedEdgeType(BaseModel):
       """Ontology agent proposes new edge types."""
       name: str = Field(description="SCREAMING_SNAKE relationship name, e.g. 'INHIBITS'")
       description: str

   class OntologyProposal(BaseModel):
       new_node_types: list[ProposedNodeType] = Field(default_factory=list)
       new_edge_types: list[ProposedEdgeType] = Field(default_factory=list)
       rationale: str

   class ExtractedEntity(BaseModel):
       name: str = Field(description="Canonical entity name")
       type_name: str = Field(description="Must match an existing node type name")
       description: str | None = None
       properties: dict = Field(default_factory=dict,
           description="Scalar facts as key-value pairs")

   class ExtractedRelation(BaseModel):
       source_name: str
       target_name: str
       relation_type: str = Field(description="Must match an existing edge type name")
       weight: float = Field(default=1.0, ge=0.0, le=1.0)
       properties: dict = Field(default_factory=dict,
           description="Evidence text, confidence, etc.")

   class ExtractionResult(BaseModel):
       entities: list[ExtractedEntity] = Field(default_factory=list)
       relations: list[ExtractedRelation] = Field(default_factory=list)
       rationale: str

   class NormalizedEntity(BaseModel):
       """Librarian output — deduplicated, ready to persist."""
       name: str
       type_name: str
       description: str | None = None
       properties: dict = Field(default_factory=dict)
       is_new: bool = True  # False if merging with existing

   class NormalizedRelation(BaseModel):
       source_name: str
       target_name: str
       relation_type: str
       weight: float = 1.0
       properties: dict = Field(default_factory=dict)

   class LibrarianPayload(BaseModel):
       accepted_node_types: list[ProposedNodeType] = Field(default_factory=list)
       accepted_edge_types: list[ProposedEdgeType] = Field(default_factory=list)
       entities: list[NormalizedEntity] = Field(default_factory=list)
       relations: list[NormalizedRelation] = Field(default_factory=list)
       summary: str
   ```

3. **Agent definitions** (`src/neocortex/extraction/agents.py`)

   Three agents, generalized (no domain-specific prompts):

   ```python
   from pydantic_ai import Agent
   from pydantic_ai.models.google import GoogleModel
   from pydantic_ai.models.test import TestModel

   DEFAULT_MODEL_NAME = "gemini-2.5-flash"

   def _build_model(model_name: str | None = None, use_test_model: bool = False):
       """Build the LLM model. Reads from settings if model_name not provided."""
       if use_test_model:
           return TestModel()
       name = model_name or DEFAULT_MODEL_NAME
       return GoogleModel(name)

   # ── Ontology Agent ──
   @dataclass
   class OntologyAgentDeps:
       episode_text: str
       existing_node_types: list[str]  # names only
       existing_edge_types: list[str]

   def build_ontology_agent(model=None) -> Agent[OntologyAgentDeps, OntologyProposal]:
       agent = Agent(
           model or GoogleModel(MODEL_NAME),
           output_type=OntologyProposal,
           deps_type=OntologyAgentDeps,
           system_prompt=(
               "You are an ontology engineer. Given a text passage, propose new node types "
               "and edge types that would be needed to represent the knowledge in the text.",
               "Propose only reusable, general concepts — not instance-level names.",
               "Extend conservatively: prefer existing types when possible.",
               "Node type names: PascalCase (e.g. Drug, Neurotransmitter, Disease).",
               "Edge type names: SCREAMING_SNAKE (e.g. TREATS, INHIBITS, CAUSES).",
           ),
       )
       # Dynamic instructions inject current ontology state
       @agent.instructions
       async def inject_context(ctx: RunContext[OntologyAgentDeps]) -> str: ...

       return agent

   # ── Extractor Agent ──
   @dataclass
   class ExtractorAgentDeps:
       episode_text: str
       node_types: list[str]
       edge_types: list[str]

   def build_extractor_agent(model=None) -> Agent[ExtractorAgentDeps, ExtractionResult]:
       # System prompts enforce ontology alignment, evidence grounding
       ...

   # ── Librarian Agent ──
   @dataclass
   class LibrarianAgentDeps:
       episode_text: str
       node_types: list[str]
       edge_types: list[str]
       extracted_entities: list[ExtractedEntity]
       extracted_relations: list[ExtractedRelation]
       known_node_names: list[str]  # for dedup

   def build_librarian_agent(model=None) -> Agent[LibrarianAgentDeps, LibrarianPayload]:
       # System prompts enforce deduplication, normalization
       ...
   ```

4. **Pipeline orchestration** (`src/neocortex/extraction/pipeline.py`)

   ```python
   async def run_extraction(
       repo: MemoryRepository,
       embeddings: EmbeddingService | None,
       agent_id: str,
       episode_ids: list[int],
       model_name: str | None = None,
       use_test_model: bool = False,
   ) -> None:
       """Process episodes through the 3-agent pipeline and persist results.

       Args:
           model_name: LLM model name (from settings.extraction_model). Falls back
                       to DEFAULT_MODEL_NAME if None.
           use_test_model: If True, use pydantic_ai TestModel (for unit tests).
       """

       for episode_id in episode_ids:
           episode = await repo.get_episode(agent_id, episode_id)
           if not episode:
               logger.warning("episode_not_found", episode_id=episode_id)
               continue

           text = episode.content

           # 1. Load current ontology from agent's graph
           node_types = await repo.get_node_types(agent_id)
           edge_types = await repo.get_edge_types(agent_id)

           # 2. Ontology stage
           ontology_result = await ontology_agent.run(
               f"Analyze this text and propose ontology extensions:\n\n{text}",
               deps=OntologyAgentDeps(
                   episode_text=text,
                   existing_node_types=[t.name for t in node_types],
                   existing_edge_types=[t.name for t in edge_types],
               ),
           )

           # 3. Persist new types
           for nt in ontology_result.output.new_node_types:
               await repo.get_or_create_node_type(agent_id, nt.name, nt.description)
           for et in ontology_result.output.new_edge_types:
               await repo.get_or_create_edge_type(agent_id, et.name, et.description)

           # Reload types (now includes newly created)
           node_types = await repo.get_node_types(agent_id)
           edge_types = await repo.get_edge_types(agent_id)

           # 4. Extraction stage
           extraction_result = await extractor_agent.run(
               f"Extract entities and relations from:\n\n{text}",
               deps=ExtractorAgentDeps(
                   episode_text=text,
                   node_types=[t.name for t in node_types],
                   edge_types=[t.name for t in edge_types],
               ),
           )

           # 5. Librarian stage
           known_names = await repo.list_all_node_names(agent_id)
           librarian_result = await librarian_agent.run(
               "Normalize and deduplicate the extracted data.",
               deps=LibrarianAgentDeps(
                   episode_text=text,
                   node_types=[t.name for t in node_types],
                   edge_types=[t.name for t in edge_types],
                   extracted_entities=extraction_result.output.entities,
                   extracted_relations=extraction_result.output.relations,
                   known_node_names=known_names,
               ),
           )

           # 6. Persist graph data
           payload = librarian_result.output
           await _persist_payload(repo, embeddings, agent_id, episode_id, payload)


   async def _persist_payload(
       repo: MemoryRepository,
       embeddings: EmbeddingService | None,
       agent_id: str,
       episode_id: int,
       payload: LibrarianPayload,
   ) -> None:
       """Persist librarian output to the knowledge graph."""

       # Persist any remaining type proposals
       for nt in payload.accepted_node_types:
           await repo.get_or_create_node_type(agent_id, nt.name, nt.description)
       for et in payload.accepted_edge_types:
           await repo.get_or_create_edge_type(agent_id, et.name, et.description)

       # Batch-embed entity descriptions (single API call instead of N+1)
       entity_embeddings: list[list[float] | None] = [None] * len(payload.entities)
       if embeddings:
           texts_to_embed = [e.description or "" for e in payload.entities]
           has_text = [bool(t) for t in texts_to_embed]
           if any(has_text):
               batch_results = await embeddings.embed_batch(
                   [t for t, h in zip(texts_to_embed, has_text) if h]
               )
               # Map batch results back to entity indices
               batch_idx = 0
               for i, h in enumerate(has_text):
                   if h:
                       entity_embeddings[i] = batch_results[batch_idx]
                       batch_idx += 1

       # Persist entities as nodes
       name_to_node_id: dict[str, int] = {}
       for i, entity in enumerate(payload.entities):
           node_type = await repo.get_or_create_node_type(agent_id, entity.type_name)
           node = await repo.upsert_node(
               agent_id=agent_id,
               name=entity.name,
               type_id=node_type.id,
               content=entity.description,
               properties={**entity.properties, "_source_episode": episode_id},
               embedding=entity_embeddings[i],
           )
           name_to_node_id[entity.name] = node.id

       # Persist relations as edges
       for rel in payload.relations:
           src_id = name_to_node_id.get(rel.source_name)
           tgt_id = name_to_node_id.get(rel.target_name)
           if src_id is None or tgt_id is None:
               # Try finding nodes by name in existing graph.
               # find_nodes_by_name returns a list (name may match multiple types);
               # we pick the first match — acceptable for PoC.
               if src_id is None:
                   src_nodes = await repo.find_nodes_by_name(agent_id, rel.source_name)
                   src_id = src_nodes[0].id if src_nodes else None
               if tgt_id is None:
                   tgt_nodes = await repo.find_nodes_by_name(agent_id, rel.target_name)
                   tgt_id = tgt_nodes[0].id if tgt_nodes else None
           if src_id is None or tgt_id is None:
               logger.warning("edge_skipped_missing_node",
                   source=rel.source_name, target=rel.target_name)
               continue
           edge_type = await repo.get_or_create_edge_type(agent_id, rel.relation_type)
           await repo.upsert_edge(
               agent_id=agent_id,
               source_id=src_id,
               target_id=tgt_id,
               type_id=edge_type.id,
               weight=rel.weight,
               properties={**rel.properties, "_source_episode": episode_id},
           )
   ```

5. **Unit tests** (`tests/test_extraction_pipeline.py`)
   - Mock the LLM with `pydantic_ai.models.test.TestModel`
   - Verify pipeline creates node types, edge types, nodes, edges
   - Verify deduplication (run same text twice → no duplicate nodes)
   - Run against `InMemoryRepository`

   **Known limitation (PoC-acceptable):** `_persist_payload` does not wrap all operations
   in a single transaction. Each `repo.upsert_node` / `repo.upsert_edge` call acquires its
   own schema-scoped connection. If a failure occurs mid-persist, partial graph state remains.
   Both `upsert_node` and `upsert_edge` are idempotent, so Procrastinate retries are safe —
   no duplicate nodes or edges. For production, the adapter would need a `transaction()` context
   manager that holds a single connection across multiple operations.

### Verification
```bash
uv run pytest tests/test_extraction_pipeline.py -v
```

### Commit
`feat(extraction): port 3-agent pipeline to NeoCortex with async PostgreSQL support`

---

## Stage 5: Wire Extraction into Remember & Ingest

### Purpose
Connect the extraction pipeline to the main data flow. When a user stores a memory
or ingests text, an extraction job is enqueued and processed in the background.

### Steps

1. **`get_episode` already on protocol** — added in Stage 1 alongside other graph mutation methods.

2. **Update `remember` tool** (`src/neocortex/tools/remember.py`)
   ```python
   # After storing episode and embedding:
   settings = ctx.lifespan_context["settings"]
   job_app = ctx.lifespan_context.get("job_app")
   if job_app and settings.extraction_enabled:
       from neocortex.jobs.tasks import extract_episode
       job_id = await extract_episode.defer_async(
           job_app, agent_id=agent_id, episode_ids=[episode_id]
       )
       logger.bind(action_log=True).info("extraction_enqueued",
           job_id=job_id, episode_id=episode_id, agent_id=agent_id)
   ```
   The extraction pipeline resolves the target schema internally via the repo's
   `GraphRouter` — no need to pass `schema_name` through the job args.

   Update `RememberResult` to include `extraction_job_id: int | None`.

3. **Update ingestion processor** (`src/neocortex/ingestion/stub_processor.py`)
   - Rename to `episode_processor.py` (it's no longer a stub)
   - After storing episode, defer extraction task via Procrastinate
   - Same pattern as remember tool: `extract_episode.defer_async(job_app, ...)`

4. **Expose `job_app` in lifespan context** (`src/neocortex/server.py`, `services.py`)
   - Ensure `job_app` is in lifespan context dict (added to `ServiceContext` in Stage 2)
   - Worker is already started in lifespan (Stage 2 Step 5)

5. **Integration test** (`tests/test_remember_extraction.py`)
   - Mock DB mode: verify job enqueue is skipped gracefully
   - With pool: verify job is created after remember

### Verification
```bash
uv run pytest tests/test_remember_extraction.py -v
NEOCORTEX_MOCK_DB=true uv run python -m neocortex  # Smoke test: server starts
```

### Commit
`feat(integration): wire extraction jobs into remember tool and ingestion processor`

---

## Stage 6: Enhanced Recall with Graph Traversal

### Purpose
When a recall query matches nodes (via text or vector search), return the node along
with its connected edges and neighbor nodes up to a configurable depth. This provides
structured graph context alongside raw episode matches.

### Steps

1. **Add node search to protocol** (`src/neocortex/db/protocol.py`)
   ```python
   async def search_nodes(
       self, agent_id: str, query: str, limit: int = 5,
       query_embedding: list[float] | None = None,
   ) -> list[Node]: ...
   ```

2. **Implement node search in adapter** (`src/neocortex/db/adapter.py`)
   - Combine vector similarity (on node embeddings) + text search (on node tsv)
   - Fan-out across agent's schemas (same pattern as episode recall)
   - Return top-N matching nodes

3. **Update `RecallItem` schema** (`src/neocortex/schemas/memory.py`)
   ```python
   class GraphContext(BaseModel):
       """Subgraph around a matched node."""
       center_node: dict  # {id, name, type, properties}
       edges: list[dict]  # [{source, target, type, weight, properties}]
       neighbor_nodes: list[dict]  # [{id, name, type}]
       depth: int

   class RecallItem(BaseModel):
       item_id: int
       name: str
       content: str
       item_type: str
       score: float
       source: str | None = None
       source_kind: Literal["node", "episode"]
       graph_name: str | None = None
       graph_context: GraphContext | None = None  # NEW: populated for node matches
   ```

4. **Update `recall` tool** (`src/neocortex/tools/recall.py`)
   ```python
   # After episode recall, also search nodes:
   matched_nodes = await repo.search_nodes(agent_id, query, limit=5, query_embedding=qemb)

   # For each matched node, get neighborhood
   traversal_depth = settings.recall_traversal_depth  # default 2
   for node in matched_nodes:
       neighborhood = await repo.get_node_neighborhood(agent_id, node.id, depth=traversal_depth)
       # Build RecallItem with graph_context
       ...

   # Merge node results with episode results, re-sort by score
   ```

5. **Add setting** (`src/neocortex/mcp_settings.py`)
   ```python
   recall_traversal_depth: int = 2  # hops from matched node
   ```

6. **Implement in mock** (`src/neocortex/db/mock.py`)
   - `search_nodes`: simple text matching on node names
   - `get_node_neighborhood`: BFS over in-memory edges

7. **Unit tests** (`tests/test_recall_graph_traversal.py`)
   - Create a small graph (5 nodes, 6 edges)
   - Recall query that matches a node → verify graph_context populated
   - Verify depth limiting works
   - Verify episode + node results are merged

### Verification
```bash
uv run pytest tests/test_recall_graph_traversal.py -v
```

### Commit
`feat(recall): add node search with configurable-depth graph traversal`

---

## Stage 7: TUI Enhancements, Discover Polish & E2E Validation

### Purpose
Update the TUI to display graph context in recall results and rich ontology in discover.
Validate the full pipeline end-to-end.

### Steps

1. **Update TUI recall display** (`src/neocortex/tui/app.py`)
   - When `RecallItem.graph_context` is present, show expandable subgraph:
     ```
     ┌─ Node: Serotonin [Neurotransmitter] ─────────── score: 0.92
     │  ├── REGULATES → Mood Regulation [BiologicalProcess]
     │  ├── INHIBITED_BY → Fluoxetine [Drug]
     │  └── PRODUCED_IN → Raphe Nuclei [BrainRegion]
     └────────────────────────────────────────────────────
     ```
   - Episode results display unchanged (backward compatible)

2. **Update TUI discover display** (`src/neocortex/tui/app.py`)
   - Show ontology as a structured tree:
     ```
     Node Types (7):
       Neurotransmitter .......... 4 entities
       Drug ...................... 6 entities
       Disease ................... 3 entities
       ...
     Edge Types (5):
       TREATS .................... 8 relations
       INHIBITS .................. 5 relations
       ...
     ```
   - Show total counts from `GraphStats`

3. **Update discover tool** (`src/neocortex/tools/discover.py`)
   - No protocol changes needed — `get_node_types` and `get_edge_types` already return
     `TypeInfo` with counts. Ensure adapter counts are accurate across schemas.

4. **Parse graph_context in TUI client** (`src/neocortex/tui/client.py`)
   - Handle new `graph_context` field in recall results

5. **Create E2E demo script** (`scripts/demo_e2e.sh`)
   ```bash
   #!/usr/bin/env bash
   set -euo pipefail

   echo "=== NeoCortex PoC Demo ==="

   # 1. Start infrastructure
   docker compose up -d postgres
   sleep 3

   # 2. Start MCP server (background)
   NEOCORTEX_AUTH_MODE=dev_token uv run python -m neocortex &
   MCP_PID=$!
   sleep 2

   # 3. Start ingestion API (background)
   NEOCORTEX_AUTH_MODE=dev_token uv run python -m neocortex.ingestion &
   ING_PID=$!
   sleep 2

   # 4. Ingest seed corpus
   uv run python -m neocortex.extraction.cli --ingest-corpus

   # 5. Wait for extraction jobs to complete
   echo "Waiting for extraction jobs..."
   sleep 30  # or poll job status

   # 6. Launch TUI for interactive demo
   echo "Launching TUI..."
   NEOCORTEX_AUTH_MODE=dev_token uv run python -m neocortex.tui

   # Cleanup
   kill $MCP_PID $ING_PID 2>/dev/null
   ```

6. **E2E integration test** (`tests/test_e2e_extraction.py`)
   - Requires Docker (PostgreSQL)
   - Ingest 2–3 seed messages
   - Wait for extraction jobs to complete
   - Verify: nodes created, edges created, ontology populated
   - Verify: recall returns graph context
   - Verify: discover shows types with counts > 0

7. **Update existing tests** — ensure no regressions from protocol changes

### Verification
```bash
# Unit tests
uv run pytest tests/ -v

# E2E (requires Docker)
docker compose up -d postgres
uv run pytest tests/test_e2e_extraction.py -v --timeout=120
```

### Commit
`feat(tui): display graph context in recall, rich ontology in discover, E2E validation`

---

## Stage 8: CLI-Reproducible E2E Smoke Tests

### Purpose
Create a standalone E2E test script that validates the entire extraction pipeline —
from ingestion through agent processing to graph-enriched recall — using only CLI
commands and HTTP calls. This script must be runnable by a human with a single command
and produce clear PASS/FAIL output for each check.

### Prerequisites
- Docker running (for PostgreSQL)
- `GOOGLE_API_KEY` set (for Gemini embeddings + extraction agents)
- No other NeoCortex processes on ports 8000/8001

### Steps

1. **Create extraction E2E test script** (`scripts/e2e_extraction_pipeline_test.py`)

   Follows the established pattern from `e2e_mcp_test.py` and `e2e_ingestion_test.py`:
   async main, httpx + fastmcp Client, direct asyncpg verification.

   ```python
   """E2E test for the extraction pipeline: ingest → extract → recall with graph context.

   Validates the full data path:
   1. Ingest medical text via /ingest/text
   2. Wait for Procrastinate extraction jobs to complete
   3. Verify ontology was created (node types, edge types)
   4. Verify nodes and edges were extracted into the graph
   5. Recall with a semantic query → expect graph_context on matched nodes
   6. Discover → expect non-zero type counts

   Prerequisites:
     docker compose up -d postgres
     GOOGLE_API_KEY=... NEOCORTEX_AUTH_MODE=dev_token \
       NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
       NEOCORTEX_MOCK_DB=false uv run python -m neocortex &
     GOOGLE_API_KEY=... NEOCORTEX_AUTH_MODE=dev_token \
       NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
       NEOCORTEX_MOCK_DB=false uv run python -m neocortex.ingestion &

   Usage:
     GOOGLE_API_KEY=... uv run python scripts/e2e_extraction_pipeline_test.py

   Via unified runner:
     GOOGLE_API_KEY=... ./scripts/run_e2e.sh scripts/e2e_extraction_pipeline_test.py
   """
   from __future__ import annotations

   import asyncio
   import os
   import time

   import asyncpg
   import httpx
   from fastmcp import Client

   from neocortex.config import PostgresConfig

   BASE_URL = os.environ.get("NEOCORTEX_BASE_URL", "http://127.0.0.1:8000")
   INGESTION_URL = os.environ.get("NEOCORTEX_INGESTION_BASE_URL", "http://127.0.0.1:8001")
   MCP_URL = os.environ.get("NEOCORTEX_MCP_URL", f"{BASE_URL}/mcp")
   TOKEN = os.environ.get("NEOCORTEX_ALICE_TOKEN", "alice-token")
   AGENT_SCHEMA = "ncx_alice__personal"

   # --- Seed texts (subset of medical corpus for speed) ---

   SEED_TEXTS = [
       (
           "Serotonin (5-hydroxytryptamine, 5-HT) is a monoamine neurotransmitter "
           "primarily found in the gastrointestinal tract, blood platelets, and the "
           "central nervous system. In the brain, serotonin is synthesized in the "
           "raphe nuclei of the brainstem. It modulates mood, appetite, sleep, and "
           "cognitive functions including memory and learning."
       ),
       (
           "Selective serotonin reuptake inhibitors (SSRIs) such as fluoxetine and "
           "sertraline work by blocking the reuptake of serotonin in the synaptic "
           "cleft, increasing its availability for postsynaptic receptors. They are "
           "first-line treatment for major depressive disorder and several anxiety "
           "disorders."
       ),
       (
           "SSRI-induced sexual dysfunction is one of the most common reasons for "
           "treatment discontinuation. Symptoms include decreased libido, delayed "
           "ejaculation, and anorgasmia. The mechanism involves serotonin's "
           "inhibitory effect on dopamine and norepinephrine pathways that mediate "
           "sexual arousal and orgasm."
       ),
   ]

   JOB_WAIT_TIMEOUT = 120  # seconds
   JOB_POLL_INTERVAL = 3   # seconds


   def _headers() -> dict[str, str]:
       return {"Authorization": f"Bearer {TOKEN}"}


   async def mcp_call(tool_name: str, arguments: dict) -> dict:
       async with Client(MCP_URL, auth=TOKEN) as client:
           result = await client.call_tool(tool_name, arguments)
       if not isinstance(result.structured_content, dict):
           raise AssertionError(f"{tool_name} did not return structured content: {result}")
       return result.structured_content


   def _quote(identifier: str) -> str:
       return '"' + identifier.replace('"', '""') + '"'


   # ── Step 1: Ingest seed texts ──────────────────────────────────────

   async def step_ingest() -> list[int]:
       """POST seed texts to ingestion API, return episode IDs from MCP remember."""
       print("\n=== Step 1: Ingest seed texts ===")
       episode_ids: list[int] = []
       for i, text in enumerate(SEED_TEXTS):
           # Use MCP remember so extraction is triggered
           result = await mcp_call("remember", {"text": text, "context": "e2e_extraction_test"})
           eid = int(result["episode_id"])
           assert eid > 0, f"Bad episode id: {result}"
           episode_ids.append(eid)
           print(f"  [{i+1}/{len(SEED_TEXTS)}] Stored episode {eid}: {text[:60]}...")
       return episode_ids


   # ── Step 2: Wait for extraction jobs ───────────────────────────────

   async def step_wait_for_extraction() -> None:
       """Poll the database until no pending/running extraction jobs remain."""
       print(f"\n=== Step 2: Wait for extraction jobs (timeout {JOB_WAIT_TIMEOUT}s) ===")
       conn = await asyncpg.connect(dsn=PostgresConfig().dsn)
       try:
           start = time.monotonic()
           while time.monotonic() - start < JOB_WAIT_TIMEOUT:
               # Procrastinate stores jobs in procrastinate_jobs table
               row = await conn.fetchrow(
                   """SELECT
                       count(*) FILTER (WHERE status = 'todo') AS pending,
                       count(*) FILTER (WHERE status = 'doing') AS running,
                       count(*) FILTER (WHERE status = 'succeeded') AS completed,
                       count(*) FILTER (WHERE status = 'failed') AS failed
                   FROM procrastinate_jobs
                   WHERE queue_name = 'extraction'"""
               )
               pending, running, completed, failed = (
                   int(row["pending"]), int(row["running"]),
                   int(row["completed"]), int(row["failed"]),
               )
               elapsed = int(time.monotonic() - start)
               print(f"  [{elapsed:3d}s] pending={pending} running={running} "
                     f"completed={completed} failed={failed}")
               if pending == 0 and running == 0:
                   if failed > 0:
                       # Fetch error details for debugging
                       err_rows = await conn.fetch(
                           """SELECT id, args, status
                              FROM procrastinate_jobs
                              WHERE queue_name = 'extraction' AND status = 'failed'
                              LIMIT 3"""
                       )
                       details = [(int(r["id"]), r["status"]) for r in err_rows]
                       print(f"  [WARN] {failed} job(s) failed: {details}")
                   if completed > 0:
                       print(f"  [PASS] All extraction jobs finished ({completed} completed, {failed} failed)")
                       return
                   # No jobs at all — maybe extraction isn't enabled or wiring is broken
                   if completed == 0 and failed == 0:
                       print("  [WARN] No extraction jobs found — checking if extraction is wired...")
                       await asyncio.sleep(JOB_POLL_INTERVAL)
                       continue
               await asyncio.sleep(JOB_POLL_INTERVAL)
           raise AssertionError(f"Extraction jobs did not complete within {JOB_WAIT_TIMEOUT}s")
       finally:
           await conn.close()


   # ── Step 3: Verify ontology created ────────────────────────────────

   async def step_verify_ontology() -> None:
       """Check that node types and edge types were created in the agent's schema."""
       print("\n=== Step 3: Verify ontology ===")
       result = await mcp_call("discover", {})
       node_types = result.get("node_types", [])
       edge_types = result.get("edge_types", [])
       stats = result.get("stats", {})

       print(f"  Node types ({len(node_types)}):")
       for nt in node_types:
           print(f"    {nt['name']} — {nt.get('count', 0)} entities")
       print(f"  Edge types ({len(edge_types)}):")
       for et in edge_types:
           print(f"    {et['name']} — {et.get('count', 0)} relations")
       print(f"  Stats: {stats}")

       assert len(node_types) > 0, f"No node types created. discover returned: {result}"
       assert len(edge_types) > 0, f"No edge types created. discover returned: {result}"
       print(f"  [PASS] Ontology populated: {len(node_types)} node types, {len(edge_types)} edge types")


   # ── Step 4: Verify graph data in PostgreSQL ────────────────────────

   async def step_verify_graph_data() -> dict[str, int]:
       """Directly query the agent's schema to count nodes and edges."""
       print("\n=== Step 4: Verify graph data in PostgreSQL ===")
       conn = await asyncpg.connect(dsn=PostgresConfig().dsn)
       try:
           schema = _quote(AGENT_SCHEMA)
           node_count = await conn.fetchval(f"SELECT count(*) FROM {schema}.node")
           edge_count = await conn.fetchval(f"SELECT count(*) FROM {schema}.edge")
           episode_count = await conn.fetchval(f"SELECT count(*) FROM {schema}.episode")
           node_type_count = await conn.fetchval(f"SELECT count(*) FROM {schema}.node_type")
           edge_type_count = await conn.fetchval(f"SELECT count(*) FROM {schema}.edge_type")

           counts = {
               "nodes": int(node_count),
               "edges": int(edge_count),
               "episodes": int(episode_count),
               "node_types": int(node_type_count),
               "edge_types": int(edge_type_count),
           }
           for label, count in counts.items():
               status = "PASS" if count > 0 else "FAIL"
               print(f"  [{status}] {label}: {count}")

           assert counts["nodes"] > 0, "No nodes extracted"
           assert counts["edges"] > 0, "No edges extracted"
           assert counts["episodes"] == len(SEED_TEXTS), (
               f"Expected {len(SEED_TEXTS)} episodes, got {counts['episodes']}"
           )

           # Print sample nodes for human inspection
           rows = await conn.fetch(
               f"""SELECT n.name, nt.name AS type_name
                   FROM {schema}.node n
                   JOIN {schema}.node_type nt ON nt.id = n.type_id
                   ORDER BY n.name LIMIT 10"""
           )
           print("  Sample nodes:")
           for r in rows:
               print(f"    {r['name']} [{r['type_name']}]")

           # Print sample edges
           edge_rows = await conn.fetch(
               f"""SELECT src.name AS source, et.name AS rel, tgt.name AS target
                   FROM {schema}.edge e
                   JOIN {schema}.node src ON src.id = e.source_id
                   JOIN {schema}.node tgt ON tgt.id = e.target_id
                   JOIN {schema}.edge_type et ON et.id = e.type_id
                   LIMIT 10"""
           )
           print("  Sample edges:")
           for r in edge_rows:
               print(f"    {r['source']} --[{r['rel']}]--> {r['target']}")

           return counts
       finally:
           await conn.close()


   # ── Step 5: Recall with graph context ──────────────────────────────

   async def step_recall_with_graph_context() -> None:
       """Recall using a semantic query and verify graph_context is populated."""
       print("\n=== Step 5: Recall with graph context ===")
       queries = [
           ("serotonin mood regulation", "serotonin"),
           ("SSRI antidepressant mechanism", "SSRI"),
           ("sexual dysfunction treatment side effects", "sexual"),
       ]
       for query, expected_keyword in queries:
           result = await mcp_call("recall", {"query": query, "limit": 10})
           results = result.get("results", [])
           print(f"\n  Query: '{query}'")
           print(f"  Results: {len(results)}")

           # Check for any node-sourced results (from extraction)
           node_results = [r for r in results if r.get("source_kind") == "node"]
           episode_results = [r for r in results if r.get("source_kind") == "episode"]
           print(f"    Nodes: {len(node_results)}, Episodes: {len(episode_results)}")

           # Check graph_context on node results
           with_context = [r for r in node_results if r.get("graph_context")]
           if with_context:
               print(f"    [PASS] {len(with_context)} node(s) have graph_context")
               ctx = with_context[0]["graph_context"]
               center = ctx.get("center_node", {})
               edges = ctx.get("edges", [])
               neighbors = ctx.get("neighbor_nodes", [])
               print(f"    Center: {center.get('name')} [{center.get('type')}]")
               print(f"    Edges: {len(edges)}, Neighbors: {len(neighbors)}")
           else:
               if node_results:
                   print(f"    [WARN] Node results found but no graph_context attached")
               else:
                   print(f"    [INFO] No node results (only episodes) — graph may still be building")

           # At minimum, episodes should match
           contents = " ".join(str(r.get("content", "")) for r in results).lower()
           if expected_keyword.lower() in contents:
               print(f"    [PASS] Found '{expected_keyword}' in results")
           else:
               print(f"    [WARN] '{expected_keyword}' not found in results")


   # ── Step 6: Cross-agent isolation ──────────────────────────────────

   async def step_verify_isolation() -> None:
       """Verify Bob cannot see Alice's extracted graph."""
       print("\n=== Step 6: Cross-agent isolation ===")
       bob_token = os.environ.get("NEOCORTEX_BOB_TOKEN", "bob-token")
       async with Client(MCP_URL, auth=bob_token) as client:
           result = await client.call_tool("discover", {})
       if not isinstance(result.structured_content, dict):
           raise AssertionError("discover did not return structured content for Bob")
       bob_discover = result.structured_content

       bob_node_types = bob_discover.get("node_types", [])
       bob_stats = bob_discover.get("stats", {})
       bob_nodes = bob_stats.get("total_nodes", 0)

       # Bob should have 0 nodes (he never ingested anything)
       # He might see shared graph types, but not Alice's personal nodes
       print(f"  Bob's node types: {len(bob_node_types)}")
       print(f"  Bob's total nodes: {bob_nodes}")
       # Don't hard-assert on 0 because shared graph may have types,
       # but Bob should NOT have Alice's extracted nodes in his personal schema
       conn = await asyncpg.connect(dsn=PostgresConfig().dsn)
       try:
           bob_schema = "ncx_bob__personal"
           exists = await conn.fetchval(
               "SELECT 1 FROM information_schema.schemata WHERE schema_name = $1",
               bob_schema,
           )
           if exists:
               bob_nodes_count = await conn.fetchval(
                   f"SELECT count(*) FROM {_quote(bob_schema)}.node"
               )
               assert int(bob_nodes_count) == 0, (
                   f"Bob has {bob_nodes_count} nodes — extraction leaked across agents"
               )
               print(f"  [PASS] Bob's personal schema has 0 nodes")
           else:
               print(f"  [PASS] Bob's personal schema doesn't exist (no data stored)")
       finally:
           await conn.close()


   # ── Main ───────────────────────────────────────────────────────────

   async def main() -> None:
       print("=" * 60)
       print("E2E Extraction Pipeline Test")
       print(f"MCP:       {MCP_URL}")
       print(f"Ingestion: {INGESTION_URL}")
       print(f"Token:     {TOKEN[:8]}...")
       print("=" * 60)

       episode_ids = await step_ingest()
       await step_wait_for_extraction()
       await step_verify_ontology()
       counts = await step_verify_graph_data()
       await step_recall_with_graph_context()
       await step_verify_isolation()

       print("\n" + "=" * 60)
       print("SUMMARY")
       print(f"  Episodes ingested:  {len(episode_ids)}")
       print(f"  Nodes extracted:    {counts['nodes']}")
       print(f"  Edges extracted:    {counts['edges']}")
       print(f"  Node types:         {counts['node_types']}")
       print(f"  Edge types:         {counts['edge_types']}")
       print("=" * 60)
       print("ALL CHECKS PASSED")


   if __name__ == "__main__":
       asyncio.run(main())
   ```

### How to run

**Option A — Via unified runner (recommended):**
```bash
GOOGLE_API_KEY=... ./scripts/run_e2e.sh scripts/e2e_extraction_pipeline_test.py
```
This starts PostgreSQL, MCP server, ingestion API, runs the test, and tears everything down.

**Option B — Manual (for debugging):**
```bash
# Terminal 1: infrastructure
docker compose up -d postgres

# Terminal 2: MCP server
GOOGLE_API_KEY=... NEOCORTEX_AUTH_MODE=dev_token \
  NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
  NEOCORTEX_MOCK_DB=false uv run python -m neocortex

# Terminal 3: ingestion API
GOOGLE_API_KEY=... NEOCORTEX_AUTH_MODE=dev_token \
  NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
  NEOCORTEX_MOCK_DB=false uv run python -m neocortex.ingestion

# Terminal 4: run the test
GOOGLE_API_KEY=... uv run python scripts/e2e_extraction_pipeline_test.py
```

**Option C — Keep services running after test (for manual TUI exploration):**
```bash
GOOGLE_API_KEY=... KEEP_RUNNING=1 ./scripts/run_e2e.sh scripts/e2e_extraction_pipeline_test.py

# Now poke around with the TUI while services are still up:
NEOCORTEX_AUTH_MODE=dev_token uv run python -m neocortex.tui
```

### What each step validates

| Step | What it does | Pass criteria |
|---|---|---|
| 1. Ingest | Stores 3 medical texts via MCP `remember` | All episode IDs > 0 |
| 2. Wait | Polls `procrastinate_jobs` table until extraction finishes | 0 pending + 0 running within 120s |
| 3. Ontology | Calls `discover`, checks types | At least 1 node type AND 1 edge type |
| 4. Graph data | Direct SQL on `ncx_alice__personal` schema | nodes > 0, edges > 0, episodes == 3 |
| 5. Recall | Semantic queries via MCP `recall` | Results contain expected keywords; node results have `graph_context` |
| 6. Isolation | Bob's `discover` + direct SQL on Bob's schema | Bob has 0 nodes in his personal schema |

### Verification
```bash
# Full automated run
GOOGLE_API_KEY=... ./scripts/run_e2e.sh scripts/e2e_extraction_pipeline_test.py

# Just the test (services already running)
GOOGLE_API_KEY=... uv run python scripts/e2e_extraction_pipeline_test.py
```

### Commit
`test(e2e): add extraction pipeline E2E smoke test with CLI runner`

---

## Execution Protocol

### For human or AI executor

1. Read this plan fully before starting.
2. Execute stages **in order** (1 → 8). Each stage depends on prior stages.
3. After each stage: run verification, commit, update progress tracker.
4. If a stage fails: document the issue, attempt to fix. If blocked, stop and report.
5. One commit per stage. Include plan tracker update in each commit.

### Pre-flight checklist

- [ ] `uv sync` — dependencies installed
- [ ] `docker compose up -d postgres` — PostgreSQL running (for stages 5–8)
- [ ] `GOOGLE_API_KEY` set — for Gemini embeddings and extraction agents
- [ ] Existing tests pass: `uv run pytest tests/ -v`

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `GOOGLE_API_KEY` | Gemini API for embeddings + agents | (required for live) |
| `NEOCORTEX_MOCK_DB` | Use in-memory mock (no Docker) | `false` |
| `NEOCORTEX_AUTH_MODE` | Auth mode | `none` |
| `NEOCORTEX_EXTRACTION_ENABLED` | Enable extraction worker | `true` |
| `NEOCORTEX_EXTRACTION_MODEL` | LLM model for extraction agents | `gemini-2.5-flash` |
| `NEOCORTEX_RECALL_TRAVERSAL_DEPTH` | Hops in graph traversal | `2` |

---

## Progress Tracker

| Stage | Title | Status | Notes |
|---|---|---|---|
| 1 | Extend MemoryRepository Protocol | DONE | Protocol, adapter, mock, 22 tests |
| 2 | Background Jobs Framework | DONE | Procrastinate app factory, task registration, context holder, settings, service lifecycle, worker in MCP lifespan, 11 tests |
| 3 | Medical Domain Seed Corpus | DONE | 10 medical passages (neuro/pharma/sexual), CLI ingest command |
| 4 | Extraction Pipeline Module | DONE | Schemas, 3 agents (ontology/extractor/librarian), pipeline orchestration, _persist_payload, 10 tests |
| 5 | Wire Extraction into Remember & Ingest | DONE | remember tool enqueues extraction, EpisodeProcessor replaces StubProcessor, backward-compat shim, 9 tests |
| 6 | Enhanced Recall with Graph Traversal | DONE | search_nodes on protocol/adapter/mock, GraphContext model, recall tool with traversal, recall_traversal_depth setting, 15 tests |
| 7 | TUI, Discover & E2E Validation | DONE | TUI recall shows graph context trees, discover uses dot-leader format, E2E demo script, 9 integration tests |
| 8 | CLI-Reproducible E2E Smoke Tests | PENDING | |

- **Last stage completed**: Stage 7 — TUI, Discover & E2E Validation
- **Last updated by**: plan-runner-agent
- **Blocked**: —

---

## Risk & Mitigation

| Risk | Impact | Mitigation |
|---|---|---|
| Gemini API rate limits during extraction | Jobs fail | Retry with backoff (max_attempts=3), TestModel fallback |
| LLM output doesn't match Pydantic schema | Extraction fails | Pydantic AI validates automatically; librarian agent normalizes |
| Large graph traversal at high depth | Slow recall | Cap depth at settings level, default=2 |
| Extraction worker blocks event loop | Server unresponsive | Procrastinate worker is async-native, agents are I/O-bound |
| Schema routing for new methods | Wrong graph written | Reuse existing `route_store()` / `route_recall()` from GraphRouter |

## Non-Goals (Deferred)

- Full DAG job scheduler — Procrastinate with manual chaining (`defer_async` from handler) sufficient for PoC
- Incremental ontology merging across agents — each agent builds independent ontology
- Fact mention provenance tables — provenance stored in edge.properties for PoC
- Advanced deduplication (fuzzy matching, entity resolution) — exact name match for PoC
- Streaming extraction progress to TUI — polling-based for now
