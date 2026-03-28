# Plan 11: Upper Ontology & Automatic Knowledge Routing

## Overview

Extend NeoCortex with an upper ontology system that automatically routes knowledge from agents and ingestion endpoints into semantically organized shared knowledge graphs. Instead of requiring manual `target_graph` targeting, a PydanticAI classification agent analyzes incoming knowledge, maps it to semantic domains (upper ontology), and routes extraction to the appropriate shared schemas. The system auto-provisions shared schemas and permissions, supports multi-domain routing (one episode can populate multiple shared graphs), and extends the ontology when knowledge genuinely doesn't fit existing domains.

**Design principle**: Unify, don't scatter. Domains are broad, cross-cutting categories (e.g., "technical knowledge") rather than source-specific silos (e.g., "hackernews data"). This ensures shared graphs provide clear utility for consumer agents regardless of where the knowledge originated.

## Execution Protocol

To execute this plan, follow this loop for each stage:

1. **Read the progress tracker** below and find the first stage that is not DONE
2. **Read the stage details** — understand the goal, dependencies, and steps
3. **Clarify ambiguities** — if anything is unclear or multiple approaches exist, ask the user before implementing. Do not guess.
4. **Implement** — execute the steps described in the stage
5. **Validate** — run the verification checks listed in the stage. If validation fails, fix the issue before proceeding. Do not skip verification.
6. **Update this plan** — mark the stage as DONE in the progress tracker, add brief notes about what was done and any deviations from the original steps
7. **Commit** — create an atomic commit with the message specified in the stage. Include all changed files (code, config, docs, and this plan file).

Repeat until all stages are DONE or a stage is BLOCKED.

**If a stage cannot be completed**: mark it BLOCKED in the tracker with a note explaining why, and stop. Do not proceed to subsequent stages.

**If assumptions are wrong**: stop, document the issue in the Issues section below, revise affected stages, and get user confirmation before continuing.

## Architecture

### Knowledge Flow (Before)

```
remember/ingest → store_episode(personal) → extract_episode(personal)
                                             ↓
remember/ingest → store_episode_to(shared) → extract_episode(shared)  [only with explicit target_graph]
```

### Knowledge Flow (After)

```
remember/ingest → store_episode(personal) → extract_episode(personal)     [unchanged]
                                           ↘ route_episode(personal)       [NEW — async job]
                                              ↓
                                           classify(text, domains)          [PydanticAI agent]
                                              ↓
                                           for each matched domain:
                                             check write permission
                                             ensure shared schema exists
                                             extract_episode(shared schema)
```

Personal graph extraction is preserved (backward compatible). Ontology routing is an **additive** pipeline that runs alongside personal extraction, populating shared domain-specific graphs. When an explicit `target_graph` is provided, ontology routing is skipped (explicit beats automatic).

### Upper Ontology Structure

```
ontology_domains (public schema, PostgreSQL table)
├── user_profile         → ncx_shared__user_profile         (preferences, goals, habits, values)
├── technical_knowledge  → ncx_shared__technical_knowledge   (tools, technologies, patterns)
├── work_context         → ncx_shared__work_context          (projects, tasks, people, orgs)
└── domain_knowledge     → ncx_shared__domain_knowledge      (general facts, concepts, trends)
    ↑ extensible: classification agent can propose new domains when knowledge doesn't fit
```

### Seed Domains

| Slug | Name | Description | Routing Signals |
|------|------|-------------|-----------------|
| `user_profile` | User Profile & Preferences | Personal preferences, goals, habits, values, opinions, communication style, work style | Mentions of likes/dislikes, preferences, personal goals, routines |
| `technical_knowledge` | Technical Knowledge | Programming languages, frameworks, libraries, tools, architecture patterns, APIs, technical concepts | Code references, technology names, technical patterns |
| `work_context` | Work & Projects | Ongoing projects, tasks, deadlines, team members, organizations, meetings, decisions | Project names, task descriptions, people, organizations, events |
| `domain_knowledge` | Domain Knowledge | General factual knowledge, industry concepts, scientific facts, business concepts, trends | Facts, definitions, concepts, explanations not fitting above |

### New Module Layout

```
src/neocortex/ontology/
  __init__.py              # Public exports
  models.py                # SemanticDomain, ClassificationResult, RoutingResult, ProposedDomain
  protocol.py              # OntologyService protocol
  pg_service.py            # PostgresOntologyService — asyncpg implementation
  memory_service.py        # InMemoryOntologyService — tests/mock mode
  classifier.py            # OntologyClassifier protocol + AgentOntologyClassifier (PydanticAI) + MockOntologyClassifier
  router.py                # OntologyRouter — orchestrates classify → permissions → provision → extract
```

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | Ontology Data Model & Storage | PENDING | | |
| 2 | Classification Agent | PENDING | | |
| 3 | Ontology Router & Auto-Provisioning | PENDING | | |
| 4 | Pipeline Integration | PENDING | | |
| 5 | Integration Tests | PENDING | | |
| 6 | E2E Validation & Documentation | PENDING | | |

Statuses: `PENDING` → `IN_PROGRESS` → `DONE` | `BLOCKED`

---

## Stage 1: Ontology Data Model & Storage

**Goal**: Define the ontology data model (Pydantic models), create PostgreSQL migration, implement PG and in-memory services, seed the 4 initial domains.

**Dependencies**: None

### Steps

1. **Create `src/neocortex/ontology/__init__.py`** — export public API:
   ```python
   from neocortex.ontology.models import (
       ClassificationResult,
       DomainClassification,
       ProposedDomain,
       RoutingResult,
       SemanticDomain,
   )
   from neocortex.ontology.memory_service import InMemoryOntologyService
   from neocortex.ontology.pg_service import PostgresOntologyService
   from neocortex.ontology.protocol import OntologyService
   ```

2. **Create `src/neocortex/ontology/models.py`** — Pydantic models:

   - `SemanticDomain` — core domain model:
     - `id: int | None = None`
     - `slug: str` (e.g., `"user_profile"`)
     - `name: str` (e.g., `"User Profile & Preferences"`)
     - `description: str` (detailed — used in classification prompt)
     - `schema_name: str | None = None` (mapped shared schema, e.g., `"ncx_shared__user_profile"`)
     - `seed: bool = False` (seed domains cannot be deleted)
     - `created_at: datetime | None = None`
     - `created_by: str | None = None`

   - `DomainClassification` — a single domain match:
     - `domain_slug: str`
     - `confidence: float` (Field ge=0, le=1)
     - `reasoning: str`

   - `ProposedDomain` — new domain proposal from classifier:
     - `slug: str`, `name: str`, `description: str`, `reasoning: str`

   - `ClassificationResult` — full classification output:
     - `matched_domains: list[DomainClassification] = []`
     - `proposed_domain: ProposedDomain | None = None`

   - `RoutingResult` — result of routing to a shared schema:
     - `domain_slug: str`, `schema_name: str`, `confidence: float`, `extraction_job_id: int | None = None`

3. **Create `src/neocortex/ontology/protocol.py`** — OntologyService protocol:
   ```python
   @runtime_checkable
   class OntologyService(Protocol):
       async def list_domains(self) -> list[SemanticDomain]: ...
       async def get_domain(self, slug: str) -> SemanticDomain | None: ...
       async def create_domain(
           self, slug: str, name: str, description: str,
           created_by: str, schema_name: str | None = None,
       ) -> SemanticDomain: ...
       async def update_schema_name(self, slug: str, schema_name: str) -> None: ...
       async def delete_domain(self, slug: str) -> bool: ...
       async def seed_defaults(self) -> None: ...
   ```

4. **Create `migrations/init/007-ontology-domains.sql`**:
   ```sql
   CREATE TABLE IF NOT EXISTS ontology_domains (
       id SERIAL PRIMARY KEY,
       slug TEXT UNIQUE NOT NULL,
       name TEXT NOT NULL,
       description TEXT NOT NULL,
       schema_name TEXT,
       seed BOOLEAN DEFAULT false,
       created_at TIMESTAMPTZ DEFAULT now(),
       updated_at TIMESTAMPTZ DEFAULT now(),
       created_by TEXT
   );

   CREATE INDEX IF NOT EXISTS idx_ontology_domains_slug ON ontology_domains (slug);

   INSERT INTO ontology_domains (slug, name, description, seed) VALUES
   ('user_profile', 'User Profile & Preferences',
    'Personal preferences, goals, habits, values, opinions, communication style, routines, and work style preferences. Knowledge about what the user likes, dislikes, wants to achieve, and how they prefer to work.',
    true),
   ('technical_knowledge', 'Technical Knowledge',
    'Programming languages, frameworks, libraries, tools, architecture patterns, APIs, technical concepts, best practices, and engineering approaches. Knowledge about technologies, how they work, and how to use them.',
    true),
   ('work_context', 'Work & Projects',
    'Ongoing projects, tasks, deadlines, team members, organizations, meetings, decisions, and professional activities. Knowledge about what is being worked on, by whom, and when.',
    true),
   ('domain_knowledge', 'Domain Knowledge',
    'General factual knowledge, industry concepts, scientific facts, business concepts, market trends, and domain-specific expertise. Broad knowledge that does not fit the other specific categories.',
    true)
   ON CONFLICT (slug) DO NOTHING;
   ```

5. **Create `src/neocortex/ontology/pg_service.py`** — PostgreSQL implementation:
   - Constructor takes `PostgresService` (same pattern as `PostgresPermissionService` in `permissions/pg_service.py`)
   - All queries use `asyncpg` parameterized queries (`$1`, `$2`) via `self._pg.pool`
   - `list_domains()` → `SELECT * FROM ontology_domains ORDER BY id`
   - `get_domain(slug)` → `SELECT * FROM ontology_domains WHERE slug = $1`
   - `create_domain(...)` → `INSERT INTO ontology_domains (...) VALUES (...) RETURNING *`
   - `update_schema_name(slug, schema_name)` → `UPDATE ... SET schema_name = $1, updated_at = now() WHERE slug = $2`
   - `delete_domain(slug)` → `DELETE FROM ontology_domains WHERE slug = $1 AND seed = false` (protect seed domains, return True/False)
   - `seed_defaults()` → same INSERT as migration with `ON CONFLICT DO NOTHING` (idempotent)

6. **Create `src/neocortex/ontology/memory_service.py`** — in-memory implementation:
   - Stores domains in `dict[str, SemanticDomain]`
   - Auto-increments IDs
   - `seed_defaults()` populates the 4 seed domains
   - `delete_domain()` protects seed domains
   - Used for tests and `NEOCORTEX_MOCK_DB=true` mode

### Verification

- [ ] `uv run python -c "from neocortex.ontology import SemanticDomain, OntologyService, InMemoryOntologyService"` succeeds
- [ ] Write `tests/test_ontology_models.py`:
  - InMemoryOntologyService `seed_defaults()` creates 4 domains
  - `list_domains()` returns all 4
  - `get_domain("user_profile")` returns correct domain
  - `create_domain()` with new slug succeeds
  - `create_domain()` with duplicate slug raises error
  - `update_schema_name()` persists
  - `delete_domain()` on seed domain returns False
  - `delete_domain()` on non-seed domain returns True
- [ ] `uv run pytest tests/test_ontology_models.py -v` passes

**Commit**: `feat(ontology): add upper ontology data model, migration, and storage services`

---

## Stage 2: Classification Agent

**Goal**: Build a PydanticAI agent that classifies incoming knowledge into ontology domains, plus a deterministic mock for tests.

**Dependencies**: Stage 1

### Steps

1. **Create `src/neocortex/ontology/classifier.py`**:

   **Protocol**:
   ```python
   @runtime_checkable
   class OntologyClassifier(Protocol):
       async def classify(self, text: str, domains: list[SemanticDomain]) -> ClassificationResult: ...
   ```

   **AgentOntologyClassifier** — PydanticAI implementation:
   - Constructor: `__init__(self, model_name: str, thinking_effort: ThinkingLevel = "low")`
   - Creates `pydantic_ai.Agent` with `ClassificationResult` as result type
   - System prompt built dynamically from current domain list:
     ```
     You are a knowledge classification agent for a memory system.
     Classify incoming knowledge into one or more semantic domains from the ontology.

     GUIDELINES:
     - CONSERVATIVE: strongly prefer existing domains over proposing new ones.
     - UNIFYING: knowledge should consolidate into fewer, broader domains, not scatter.
     - MULTI-LABEL: a single piece of knowledge may belong to multiple domains.
     - Only propose a new domain if the knowledge genuinely does not fit ANY existing domain.
     - New domains must be broad cross-cutting categories, NOT narrow topics or source-specific silos.
     - Set confidence >= 0.3 for relevant domains, higher for strong matches.

     Available domains:
     {% for domain in domains %}
     - {{ domain.slug }}: {{ domain.name }}
       {{ domain.description }}
     {% endfor %}

     Classify the following knowledge text. Return matched domains with confidence scores.
     ```
   - `classify(text, domains)` → runs the agent with the text as user message
   - Uses the same Gemini model as extraction pipeline (configurable via settings)

   **MockOntologyClassifier** — deterministic keyword-based classifier for tests:
   - Keyword maps per domain:
     - `user_profile`: "prefer", "goal", "habit", "like", "dislike", "want", "value", "opinion"
     - `technical_knowledge`: "python", "react", "api", "database", "framework", "library", "code", "architecture"
     - `work_context`: "project", "task", "deadline", "meeting", "team", "milestone", "sprint"
     - `domain_knowledge`: "concept", "theory", "fact", "research", "trend", "industry"
   - Matches all domains that have at least one keyword hit (case-insensitive)
   - Falls back to `domain_knowledge` if no keywords match
   - Confidence: 0.8 for keyword match, 0.4 for fallback
   - Never proposes new domains

2. **Add settings to `src/neocortex/mcp_settings.py`** (add after extraction pipeline settings around line 84):
   ```python
   # Upper ontology routing
   ontology_routing_enabled: bool = True
   ontology_classifier_model: str = "gemini-3-flash-preview"
   ontology_classifier_thinking_effort: ThinkingLevel = "low"
   ontology_classification_threshold: float = 0.3
   ```

### Verification

- [ ] Write `tests/test_ontology_classifier.py`:
  - MockOntologyClassifier: "I prefer Python for backend work" → `user_profile` + `technical_knowledge`
  - MockOntologyClassifier: "We need to ship project X by Friday" → `work_context`
  - MockOntologyClassifier: "React hooks simplify state management" → `technical_knowledge`
  - MockOntologyClassifier: "The theory of relativity explains..." → `domain_knowledge`
  - MockOntologyClassifier: fallback for text with no keywords → `domain_knowledge`
  - All returned confidences are above 0.3
- [ ] `uv run pytest tests/test_ontology_classifier.py -v` passes

**Commit**: `feat(ontology): add classification agent with PydanticAI and mock implementations`

---

## Stage 3: Ontology Router & Auto-Provisioning

**Goal**: Build the `OntologyRouter` service that orchestrates classification, permission checking, schema auto-provisioning, and extraction job enqueuing.

**Dependencies**: Stage 1, Stage 2

### Steps

1. **Create `src/neocortex/ontology/router.py`**:

   ```python
   class OntologyRouter:
       def __init__(
           self,
           ontology_service: OntologyService,
           classifier: OntologyClassifier,
           schema_mgr: SchemaManager,
           permissions: PermissionChecker,
           job_app: procrastinate.App | None = None,
           classification_threshold: float = 0.3,
       ) -> None:
           ...
   ```

   **`route_and_extract(agent_id, episode_id, episode_text) -> list[RoutingResult]`**:
   1. Fetch current domains via `ontology_service.list_domains()`
   2. Classify episode text via `classifier.classify(text, domains)`
   3. Filter matches below `classification_threshold`
   4. If `proposed_domain` is not None, call `_provision_domain()` and append to matches
   5. For each matched domain:
      a. `get_domain(slug)` — skip if not found
      b. `_ensure_schema(domain, agent_id)` — get or create shared schema
      c. Check `permissions.can_write_schema(agent_id, schema_name)` — skip if no permission
      d. `_enqueue_extraction(agent_id, episode_id, schema_name)` — defer `extract_episode` task
      e. Append `RoutingResult` to results
   6. Log routing results and return

   **`_provision_domain(proposed: ProposedDomain, agent_id: str) -> SemanticDomain`**:
   1. Sanitize slug (lowercase, alphanumeric + underscores only)
   2. Create domain via `ontology_service.create_domain(slug, name, description, created_by=agent_id)`
   3. Create shared schema via `schema_mgr.create_graph(agent_id="shared", purpose=slug, is_shared=True)`
   4. Compute `schema_name = f"ncx_shared__{slug}"`
   5. Grant permissions: `permissions.grant(agent_id, schema_name, can_read=True, can_write=True, granted_by="ontology_router")`
   6. Update domain: `ontology_service.update_schema_name(slug, schema_name)`
   7. Log: `logger.bind(action_log=True).info("ontology_domain_provisioned", ...)`
   8. Return the created domain

   **`_ensure_schema(domain: SemanticDomain, agent_id: str) -> str`**:
   1. If `domain.schema_name` is not None, return it (schema already mapped)
   2. Otherwise: `schema_name = f"ncx_shared__{domain.slug}"`
   3. Create shared schema via `schema_mgr.create_graph(agent_id="shared", purpose=domain.slug, is_shared=True)` (idempotent — `SchemaManager` handles duplicates)
   4. Grant permissions to `agent_id` if not already granted
   5. Update domain's schema_name
   6. Return schema_name

   **`_enqueue_extraction(agent_id, episode_id, target_schema) -> int | None`**:
   1. If `job_app is None`, return None
   2. Defer `extract_episode` task: `job_app.configure_task("extract_episode").defer_async(agent_id=agent_id, episode_ids=[episode_id], target_schema=target_schema)`
   3. Log routing event
   4. Return job_id

2. **Add `RoutingResult` to `src/neocortex/ontology/models.py`** (if not already there from Stage 1):
   - Already defined in Stage 1 models list

### Verification

- [ ] Write `tests/test_ontology_router.py`:
  - **Setup**: InMemoryOntologyService (seeded) + MockOntologyClassifier + InMemoryPermissionService + mock SchemaManager
  - Test: "I prefer Python" → routes to `user_profile` + `technical_knowledge` schemas
  - Test: agent without write permission to `ncx_shared__user_profile` → that schema is skipped
  - Test: agent with admin status → bypasses permission check, routes to all matched schemas
  - Test: classifier proposes new domain → domain auto-created, schema provisioned, agent gets permissions
  - Test: `_ensure_schema` is idempotent (calling twice for same domain doesn't error)
  - Test: classification matches below threshold are filtered out
- [ ] `uv run pytest tests/test_ontology_router.py -v` passes

**Commit**: `feat(ontology): add ontology router with auto-provisioning and permission-aware routing`

---

## Stage 4: Pipeline Integration

**Goal**: Wire the ontology router into the remember tool, ingestion pipeline, and Procrastinate job system. Update service initialization to create and wire ontology services.

**Dependencies**: Stage 3

### Steps

1. **Add `route_episode` task to `src/neocortex/jobs/tasks.py`** (after the existing `extract_episode` task):
   ```python
   @app.task(
       name="route_episode",
       retry=procrastinate.RetryStrategy(max_attempts=3, wait=5),
       queue="extraction",
   )
   async def route_episode(
       agent_id: str,
       episode_id: int,
       episode_text: str,
   ) -> None:
       """Route an episode to shared graphs via ontology classification."""
       logger.info("route_episode_started", agent_id=agent_id, episode_id=episode_id)
       from neocortex.jobs.context import get_services

       services = get_services()
       ontology_router = services.get("ontology_router")
       if ontology_router is None:
           logger.debug("route_episode_skipped_no_router")
           return

       results = await ontology_router.route_and_extract(
           agent_id=agent_id,
           episode_id=episode_id,
           episode_text=episode_text,
       )
       logger.bind(action_log=True).info(
           "route_episode_completed",
           agent_id=agent_id,
           episode_id=episode_id,
           routed_to=[r.schema_name for r in results],
           domain_count=len(results),
       )
   ```

2. **Update `src/neocortex/services.py`**:

   - Add to `ServiceContext` TypedDict:
     ```python
     ontology_router: "OntologyRouter | None"
     ```

   - In the **mock_db** path (around line 41), after creating permissions:
     ```python
     ontology_router = None
     if settings.ontology_routing_enabled:
         from neocortex.ontology import InMemoryOntologyService
         from neocortex.ontology.classifier import MockOntologyClassifier
         from neocortex.ontology.router import OntologyRouter

         ontology_svc = InMemoryOntologyService()
         await ontology_svc.seed_defaults()
         ontology_router = OntologyRouter(
             ontology_service=ontology_svc,
             classifier=MockOntologyClassifier(),
             schema_mgr=None,           # No schema provisioning in mock mode
             permissions=permissions,
             job_app=None,
             classification_threshold=settings.ontology_classification_threshold,
         )
     ```
     Add `ontology_router=ontology_router` to the mock ServiceContext return.

   - In the **PG** path (around line 56), after creating `pg_permissions` and before creating `job_app`:
     ```python
     ontology_router = None
     if settings.ontology_routing_enabled:
         from neocortex.ontology import PostgresOntologyService
         from neocortex.ontology.classifier import AgentOntologyClassifier
         from neocortex.ontology.router import OntologyRouter

         ontology_svc = PostgresOntologyService(pg)
         await ontology_svc.seed_defaults()
         ontology_classifier = AgentOntologyClassifier(
             model_name=settings.ontology_classifier_model,
             thinking_effort=settings.ontology_classifier_thinking_effort,
         )
         # OntologyRouter created after job_app (needs it for enqueuing)
     ```
     After `job_app` creation, create the router:
     ```python
     if settings.ontology_routing_enabled and ontology_svc is not None:
         ontology_router = OntologyRouter(
             ontology_service=ontology_svc,
             classifier=ontology_classifier,
             schema_mgr=schema_mgr,
             permissions=pg_permissions,
             job_app=job_app,
             classification_threshold=settings.ontology_classification_threshold,
         )
     ```
     Add `ontology_router=ontology_router` to the PG ServiceContext.

3. **Update `src/neocortex/tools/remember.py`** — add routing enqueue after the existing extraction block (after line 71):
   ```python
   # Enqueue ontology routing if enabled (routes to shared domain graphs)
   if job_app and settings.ontology_routing_enabled and target_graph is None:
       await job_app.configure_task("route_episode").defer_async(
           agent_id=agent_id, episode_id=episode_id, episode_text=text,
       )
       logger.bind(action_log=True).info(
           "ontology_routing_enqueued",
           episode_id=episode_id,
           agent_id=agent_id,
       )
   ```
   Note: only enqueue routing when `target_graph is None` — explicit targeting takes precedence.

4. **Update `src/neocortex/ingestion/episode_processor.py`**:

   - Add `ontology_routing_enabled: bool = True` to `__init__` constructor parameters
   - Store as `self._ontology_routing_enabled`
   - Add `_enqueue_routing()` method:
     ```python
     async def _enqueue_routing(
         self, agent_id: str, episode_id: int, text: str, target_schema: str | None = None,
     ) -> None:
         """Enqueue ontology routing job if enabled and no explicit target."""
         if not self._job_app or not self._ontology_routing_enabled or target_schema is not None:
             return
         await self._job_app.configure_task("route_episode").defer_async(
             agent_id=agent_id, episode_id=episode_id, episode_text=text,
         )
         logger.bind(action_log=True).info(
             "ontology_routing_enqueued",
             episode_id=episode_id,
             agent_id=agent_id,
             source="ingestion",
         )
     ```
   - Call `await self._enqueue_routing(agent_id, episode_id, text, target_schema)` after `_enqueue_extraction()` in:
     - `process_text()` (after line 70)
     - `process_document()` (after line 89) — use the decoded `text` variable
     - `process_events()` (after line 105) — use `event_text`

5. **Update `src/neocortex/ingestion/app.py`** — pass `ontology_routing_enabled=settings.ontology_routing_enabled` to `EpisodeProcessor()` constructor (find the EpisodeProcessor instantiation and add the kwarg).

### Verification

- [ ] `uv run python -c "from neocortex.jobs.tasks import route_episode"` — task importable
- [ ] `NEOCORTEX_MOCK_DB=true uv run python -m neocortex` — server starts without errors
- [ ] `NEOCORTEX_MOCK_DB=true uv run python -m neocortex.ingestion` — ingestion starts without errors
- [ ] `uv run pytest tests/ -v` — all existing tests still pass (no regressions)
- [ ] Verify services.py correctly creates ontology services in both mock and PG paths

**Commit**: `feat(ontology): integrate ontology routing into remember tool and ingestion pipeline`

---

## Stage 5: Integration Tests

**Goal**: Comprehensive tests covering the full ontology routing flow end-to-end with in-memory implementations.

**Dependencies**: Stage 4

### Steps

1. **Create `tests/test_ontology_e2e.py`** — integration test file with the following test classes:

   **`TestOntologyDataModel`**:
   - `test_seed_domains_created` — InMemoryOntologyService seeds 4 domains with correct slugs
   - `test_crud_lifecycle` — create domain, get it, update schema_name, delete it
   - `test_seed_domain_protected` — deleting a seed domain returns False
   - `test_duplicate_slug_rejected` — creating domain with existing slug raises error

   **`TestClassificationRouting`**:
   - `test_technical_content_routes_to_tech` — "Python asyncio event loop" → includes `technical_knowledge`
   - `test_preference_content_routes_to_profile` — "I prefer dark mode" → includes `user_profile`
   - `test_multi_domain_routing` — "I prefer Python for my project deadline" → routes to 2+ domains
   - `test_threshold_filtering` — low confidence matches filtered out

   **`TestOntologyRouter`**:
   - Uses InMemoryOntologyService + MockOntologyClassifier + InMemoryPermissionService
   - `test_basic_routing_flow` — episode text classified and RoutingResults returned
   - `test_permission_enforcement` — agent without write access to a domain schema is skipped
   - `test_admin_bypass` — admin agent routes to all matched schemas regardless of permissions
   - `test_explicit_target_skips_routing` — when target_graph is set, ontology routing not triggered

   **`TestDomainProvisioning`**:
   - Mock the classifier to return a ProposedDomain
   - `test_new_domain_created` — proposed domain is created in ontology service
   - `test_schema_provisioned_for_new_domain` — shared schema name assigned
   - `test_creator_gets_permissions` — originating agent gets read+write on new schema
   - `test_ensure_schema_idempotent` — calling _ensure_schema twice doesn't error

   **`TestPipelineIntegration`**:
   - `test_remember_enqueues_routing` — remember tool with no target_graph enqueues `route_episode`
   - `test_remember_explicit_target_skips_routing` — remember tool with `target_graph` does NOT enqueue routing
   - `test_ingestion_enqueues_routing` — EpisodeProcessor enqueues routing after extraction
   - `test_routing_disabled` — when `ontology_routing_enabled=False`, no routing jobs enqueued
   - `test_backward_compat` — existing personal graph extraction still happens alongside routing

2. **Ensure existing tests pass** — run full test suite and fix any regressions caused by new `ontology_router` field in ServiceContext.

### Verification

- [ ] `uv run pytest tests/test_ontology_e2e.py -v` — all new tests pass
- [ ] `uv run pytest tests/ -v` — all existing tests still pass (no regressions)
- [ ] Coverage: ontology models, classifier mock, router logic, permission enforcement, pipeline integration

**Commit**: `test(ontology): add comprehensive integration tests for ontology routing`

---

## Stage 6: E2E Validation & Documentation

**Goal**: Full end-to-end validation, update CLAUDE.md codebase map and architecture rules, finalize plan document.

**Dependencies**: Stage 5

### Steps

1. **Run full E2E validation**:
   - `uv run pytest tests/ -v` — full test suite green
   - `NEOCORTEX_MOCK_DB=true uv run python -m neocortex` — MCP server starts cleanly
   - `NEOCORTEX_MOCK_DB=true uv run python -m neocortex.ingestion` — ingestion API starts cleanly
   - Check startup logs for ontology service initialization messages

2. **Update `CLAUDE.md`** codebase map — add ontology module under `src/neocortex/`:
   ```
   ontology/              # Upper ontology & automatic knowledge routing
     models.py            # SemanticDomain, ClassificationResult, RoutingResult
     protocol.py          # OntologyService protocol
     pg_service.py        # PostgreSQL implementation
     memory_service.py    # In-memory implementation (tests/mock)
     classifier.py        # PydanticAI classification agent + mock
     router.py            # OntologyRouter — classify → route → extract
   ```

3. **Add architecture rule to `CLAUDE.md`** (as rule #7):
   ```
   **7. Ontology routing is additive, not replacing.**
   Personal graph extraction continues unchanged. Ontology routing adds shared-graph
   extraction jobs alongside personal ones. When `target_graph` is explicitly set,
   ontology routing is skipped (explicit beats automatic). The upper ontology
   (ontology_domains table) maps semantic domains to shared schemas. Classification
   uses the same Gemini model as extraction. New domains auto-provision shared schemas
   and grant write permissions to the originating agent.
   ```

4. **Update migration reference** in CLAUDE.md:
   - Change `migrations/init/` comment from `(001-006)` to `(001-007)`

5. **Finalize this plan document** — mark all stages as DONE with notes and commit hashes in the progress tracker.

### Verification

- [ ] `uv run pytest tests/ -v` — all tests green
- [ ] CLAUDE.md codebase map includes `ontology/` module
- [ ] CLAUDE.md architecture rules include rule #7 about ontology routing
- [ ] `NEOCORTEX_MOCK_DB=true uv run python -m neocortex` — clean startup with ontology logs
- [ ] Plan document has all stages marked DONE

**Commit**: `docs(ontology): add E2E validation, update CLAUDE.md, and finalize plan 11`

---

## Overall Verification

After all stages are complete, run:

```bash
# Unit tests
uv run pytest tests/test_ontology_models.py tests/test_ontology_classifier.py tests/test_ontology_router.py -v

# Integration tests
uv run pytest tests/test_ontology_e2e.py -v

# Full test suite (including all existing tests)
uv run pytest tests/ -v

# Server startup (mock mode)
NEOCORTEX_MOCK_DB=true uv run python -m neocortex

# Ingestion startup (mock mode)
NEOCORTEX_MOCK_DB=true uv run python -m neocortex.ingestion
```

## Issues

[Document any problems discovered during execution]

## Decisions

### Decision: Routing timing
- **Options**: A) Inline at remember/ingestion time B) Separate async Procrastinate job C) First step of extraction pipeline
- **Chosen**: B — separate `route_episode` Procrastinate job
- **Rationale**: Non-blocking for the user (remember returns fast), classification LLM call is isolated, naturally generates multiple `extract_episode` jobs per episode. Uses the existing job infrastructure.

### Decision: Personal vs shared extraction
- **Options**: A) Replace personal with shared-only B) Run both personal and shared C) Configurable toggle
- **Chosen**: B — run both (additive)
- **Rationale**: Backward compatible, personal graphs retain full functionality, shared graphs add cross-agent knowledge organization. No existing behavior changes.

### Decision: Domain creation authorization
- **Options**: A) Auto-create shared schema + grant permissions B) Require admin approval
- **Chosen**: A — auto-create with permissions
- **Rationale**: Reduces friction, keeps the system self-organizing. Admins can review and revoke via existing `/admin/permissions` endpoints.

### Decision: Seed domains
- **Options**: A) 3 domains B) 4 domains (+ domain_knowledge)
- **Chosen**: B — 4 domains including `domain_knowledge`
- **Rationale**: Provides a catch-all for factual/conceptual knowledge that doesn't fit the 3 specific categories. Prevents forced fitting and over-fragmentation.

### Decision: Classification model
- **Options**: A) Same model as extraction B) Separate cheaper model
- **Chosen**: A — same Gemini model (configurable via `ontology_classifier_model` setting)
- **Rationale**: Consistent quality, simpler configuration. Classification is a lightweight prompt so cost difference is negligible.
