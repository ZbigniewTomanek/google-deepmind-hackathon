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
2. Build a lightweight background jobs framework (PostgreSQL-backed, asyncio worker)
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
  │                     │  Job Worker      │
  │                     │  (asyncio task)  │
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

   # ── Node CRUD ──
   async def upsert_node(
       self, agent_id: str, name: str, type_id: int,
       content: str | None = None, properties: dict | None = None,
       embedding: list[float] | None = None, source: str | None = None,
   ) -> Node: ...
   """Upsert by (name, type_id). If exists, merge properties and update."""

   async def find_node_by_name(
       self, agent_id: str, name: str
   ) -> Node | None: ...

   # ── Edge CRUD ──
   async def create_edge(
       self, agent_id: str, source_id: int, target_id: int,
       type_id: int, weight: float = 1.0, properties: dict | None = None,
   ) -> Edge: ...

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
   - `get_or_create_node_type`: use `graph.get_node_type_by_name()`, fallback to `graph.create_node_type()`
   - `upsert_node`: query `SELECT id FROM node WHERE name = $1 AND type_id = $2`, then create or update
   - `get_node_neighborhood`: iterative BFS using `graph.get_neighbors()` up to depth
   - Schema routing: use `self._router.route_store(agent_id)` for writes, fan-out for reads
   - All SQL via `schema_scoped_connection(self._pool, schema_name)`

3. **Implement in `InMemoryRepository`** (`src/neocortex/db/mock.py`)

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
   - `get_node_neighborhood`: simple BFS over `self._edges`
   - `upsert_node`: lookup by `(name, type_id)` tuple

4. **Unit tests** (`tests/test_protocol_graph_mutations.py`)
   - Test upsert_node idempotency (same name+type → same node, merged properties)
   - Test get_or_create_node_type idempotency
   - Test get_node_neighborhood at depth 1, 2, 3
   - Test create_edge and verify traversal
   - Run against `InMemoryRepository`

### Verification
```bash
uv run pytest tests/test_protocol_graph_mutations.py -v
```

### Commit
`feat(db): extend MemoryRepository protocol with graph mutation methods`

---

## Stage 2: Background Jobs Framework

### Purpose
Provide asynchronous job processing for extraction and other long-running tasks.
PostgreSQL-backed for persistence and visibility, asyncio-based worker for simplicity.

### Steps

1. **Create migration** (`migrations/init/007_extraction_jobs.sql`)

   ```sql
   CREATE TABLE IF NOT EXISTS public.extraction_jobs (
       id            SERIAL PRIMARY KEY,
       agent_id      TEXT NOT NULL,
       episode_ids   INTEGER[] NOT NULL,
       schema_name   TEXT NOT NULL,
       status        TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','running','completed','failed')),
       error         TEXT,
       attempts      INTEGER DEFAULT 0,
       max_attempts  INTEGER DEFAULT 3,
       created_at    TIMESTAMPTZ DEFAULT now(),
       started_at    TIMESTAMPTZ,
       completed_at  TIMESTAMPTZ
   );
   CREATE INDEX idx_extraction_jobs_pending
       ON public.extraction_jobs (status, created_at)
       WHERE status = 'pending';
   ```

2. **Create jobs module** (`src/neocortex/jobs/__init__.py`, `models.py`, `queue.py`, `worker.py`)

   `models.py`:
   ```python
   class ExtractionJob(BaseModel):
       id: int
       agent_id: str
       episode_ids: list[int]
       schema_name: str
       status: Literal["pending", "running", "completed", "failed"]
       error: str | None = None
       attempts: int = 0
       max_attempts: int = 3
       created_at: datetime
       started_at: datetime | None = None
       completed_at: datetime | None = None
   ```

   `queue.py` — job lifecycle operations:
   ```python
   async def enqueue_extraction(
       pool: asyncpg.Pool, agent_id: str, episode_ids: list[int], schema_name: str
   ) -> int: ...
   """INSERT into extraction_jobs, return job id."""

   async def claim_next_job(pool: asyncpg.Pool) -> ExtractionJob | None: ...
   """SELECT ... WHERE status='pending' ORDER BY created_at
   FOR UPDATE SKIP LOCKED — atomic claim, set status='running'."""

   async def complete_job(pool: asyncpg.Pool, job_id: int) -> None: ...
   async def fail_job(pool: asyncpg.Pool, job_id: int, error: str) -> None: ...
   async def get_job(pool: asyncpg.Pool, job_id: int) -> ExtractionJob | None: ...
   async def list_pending_jobs(pool: asyncpg.Pool, agent_id: str | None = None) -> list[ExtractionJob]: ...
   ```

   `worker.py` — asyncio background task:
   ```python
   class ExtractionWorker:
       def __init__(self, pool: asyncpg.Pool, repo: MemoryRepository,
                    embeddings: EmbeddingService | None, settings: MCPSettings):
           self._pool = pool
           self._repo = repo
           self._embeddings = embeddings
           self._settings = settings
           self._running = False
           self._task: asyncio.Task | None = None

       async def start(self) -> None:
           """Launch the background polling loop as asyncio.Task."""
           self._running = True
           self._task = asyncio.create_task(self._run_loop())

       async def stop(self) -> None:
           """Gracefully stop the worker."""
           self._running = False
           if self._task:
               self._task.cancel()
               with suppress(asyncio.CancelledError):
                   await self._task

       async def _run_loop(self) -> None:
           poll_interval = self._settings.job_poll_interval  # default 2.0s
           while self._running:
               job = await claim_next_job(self._pool)
               if job:
                   await self._process_job(job)
               else:
                   await asyncio.sleep(poll_interval)

       async def _process_job(self, job: ExtractionJob) -> None:
           """Run extraction pipeline for a job's episodes."""
           try:
               # Import here to avoid circular deps
               from neocortex.extraction.pipeline import run_extraction
               await run_extraction(
                   repo=self._repo,
                   embeddings=self._embeddings,
                   agent_id=job.agent_id,
                   episode_ids=job.episode_ids,
               )
               await complete_job(self._pool, job.id)
           except Exception as e:
               logger.exception("extraction_job_failed", job_id=job.id)
               await fail_job(self._pool, job.id, str(e))
   ```

3. **Add settings** (`src/neocortex/mcp_settings.py`)
   ```python
   job_poll_interval: float = 2.0        # seconds between job polls
   extraction_enabled: bool = True        # feature flag
   extraction_max_attempts: int = 3
   ```

4. **Wire worker into service lifecycle** (`src/neocortex/services.py`)
   - Add `worker: ExtractionWorker | None` to `ServiceContext`
   - In `create_services()`: if not mock and `settings.extraction_enabled`, create and start worker
   - In `shutdown_services()`: stop worker before closing pool

5. **Unit tests** (`tests/test_jobs.py`)
   - Test enqueue + claim + complete flow (mock pool or in-memory)
   - Test claim skips running jobs (SKIP LOCKED semantics)
   - Test fail_job increments attempts
   - Test worker start/stop lifecycle

### Verification
```bash
uv run pytest tests/test_jobs.py -v
```

### Commit
`feat(jobs): add PostgreSQL-backed extraction job queue with asyncio worker`

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

   MODEL_NAME = "gemini-2.5-flash"

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
       use_test_model: bool = False,
   ) -> None:
       """Process episodes through the 3-agent pipeline and persist results."""

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

       # Persist entities as nodes
       name_to_node_id: dict[str, int] = {}
       for entity in payload.entities:
           node_type = await repo.get_or_create_node_type(agent_id, entity.type_name)
           # Generate embedding for entity description
           emb = None
           if embeddings and entity.description:
               emb = await embeddings.embed(entity.description)
           node = await repo.upsert_node(
               agent_id=agent_id,
               name=entity.name,
               type_id=node_type.id,
               content=entity.description,
               properties={**entity.properties, "_source_episode": episode_id},
               embedding=emb,
           )
           name_to_node_id[entity.name] = node.id

       # Persist relations as edges
       for rel in payload.relations:
           src_id = name_to_node_id.get(rel.source_name)
           tgt_id = name_to_node_id.get(rel.target_name)
           if src_id is None or tgt_id is None:
               # Try finding nodes by name in existing graph
               if src_id is None:
                   src_node = await repo.find_node_by_name(agent_id, rel.source_name)
                   src_id = src_node.id if src_node else None
               if tgt_id is None:
                   tgt_node = await repo.find_node_by_name(agent_id, rel.target_name)
                   tgt_id = tgt_node.id if tgt_node else None
           if src_id is None or tgt_id is None:
               logger.warning("edge_skipped_missing_node",
                   source=rel.source_name, target=rel.target_name)
               continue
           edge_type = await repo.get_or_create_edge_type(agent_id, rel.relation_type)
           await repo.create_edge(
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

1. **Add `get_episode` to protocol** (`src/neocortex/db/protocol.py`)
   ```python
   async def get_episode(self, agent_id: str, episode_id: int) -> Episode | None: ...
   ```
   Implement in both adapter (schema-scoped query) and mock (dict lookup).

2. **Update `remember` tool** (`src/neocortex/tools/remember.py`)
   ```python
   # After storing episode and embedding:
   pool = ctx.lifespan_context.get("pool")
   settings = ctx.lifespan_context["settings"]
   if pool and settings.extraction_enabled:
       schema = ctx.lifespan_context["router"].route_store(agent_id)[0]
       from neocortex.jobs.queue import enqueue_extraction
       job_id = await enqueue_extraction(pool, agent_id, [episode_id], schema)
       logger.bind(action_log=True).info("extraction_enqueued",
           job_id=job_id, episode_id=episode_id, agent_id=agent_id)
   ```
   Update `RememberResult` to include `extraction_job_id: int | None`.

3. **Update ingestion processor** (`src/neocortex/ingestion/stub_processor.py`)
   - Rename to `episode_processor.py` (it's no longer a stub)
   - After storing episode, enqueue extraction job
   - Same pattern as remember tool

4. **Expose pool and router in lifespan context** (`src/neocortex/server.py`, `services.py`)
   - Ensure `pool` and `router` are in lifespan context dict
   - Expose worker in ServiceContext for lifecycle management

5. **Add ingestion lifespan wiring** (`src/neocortex/ingestion/app.py`)
   - Start extraction worker in ingestion service lifespan too
   - Share the same ServiceContext pattern

6. **Integration test** (`tests/test_remember_extraction.py`)
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

## Execution Protocol

### For human or AI executor

1. Read this plan fully before starting.
2. Execute stages **in order** (1 → 7). Each stage depends on prior stages.
3. After each stage: run verification, commit, update progress tracker.
4. If a stage fails: document the issue, attempt to fix. If blocked, stop and report.
5. One commit per stage. Include plan tracker update in each commit.

### Pre-flight checklist

- [ ] `uv sync` — dependencies installed
- [ ] `docker compose up -d postgres` — PostgreSQL running (for stages 5–7)
- [ ] `GOOGLE_API_KEY` set — for Gemini embeddings and extraction agents
- [ ] Existing tests pass: `uv run pytest tests/ -v`

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `GOOGLE_API_KEY` | Gemini API for embeddings + agents | (required for live) |
| `NEOCORTEX_MOCK_DB` | Use in-memory mock (no Docker) | `false` |
| `NEOCORTEX_AUTH_MODE` | Auth mode | `none` |
| `NEOCORTEX_EXTRACTION_ENABLED` | Enable extraction worker | `true` |
| `NEOCORTEX_RECALL_TRAVERSAL_DEPTH` | Hops in graph traversal | `2` |
| `NEOCORTEX_JOB_POLL_INTERVAL` | Worker poll interval (seconds) | `2.0` |

---

## Progress Tracker

| Stage | Title | Status | Notes |
|---|---|---|---|
| 1 | Extend MemoryRepository Protocol | PENDING | |
| 2 | Background Jobs Framework | PENDING | |
| 3 | Medical Domain Seed Corpus | PENDING | |
| 4 | Extraction Pipeline Module | PENDING | |
| 5 | Wire Extraction into Remember & Ingest | PENDING | |
| 6 | Enhanced Recall with Graph Traversal | PENDING | |
| 7 | TUI, Discover & E2E Validation | PENDING | |

- **Last stage completed**: —
- **Last updated by**: —
- **Blocked**: —

---

## Risk & Mitigation

| Risk | Impact | Mitigation |
|---|---|---|
| Gemini API rate limits during extraction | Jobs fail | Retry with backoff (max_attempts=3), TestModel fallback |
| LLM output doesn't match Pydantic schema | Extraction fails | Pydantic AI validates automatically; librarian agent normalizes |
| Large graph traversal at high depth | Slow recall | Cap depth at settings level, default=2 |
| Extraction worker blocks event loop | Server unresponsive | Worker runs in `asyncio.Task`, agents are async I/O-bound |
| Schema routing for new methods | Wrong graph written | Reuse existing `route_store()` / `route_recall()` from GraphRouter |

## Non-Goals (Deferred)

- Production-grade job scheduler (Celery, Dramatiq) — asyncio worker sufficient for PoC
- Incremental ontology merging across agents — each agent builds independent ontology
- Fact mention provenance tables — provenance stored in edge.properties for PoC
- Advanced deduplication (fuzzy matching, entity resolution) — exact name match for PoC
- Streaming extraction progress to TUI — polling-based for now
