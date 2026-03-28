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
                                           classify(text, domains)          [DomainClassifier]
                                              ↓
                                           for each matched domain:
                                             check write permission
                                             ensure shared schema exists
                                             extract_episode(shared schema)
```

Personal graph extraction is preserved (backward compatible). Domain routing is an **additive** pipeline that runs alongside personal extraction, populating shared domain-specific graphs. When an explicit `target_graph` is provided, domain routing is skipped (explicit beats automatic).

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
src/neocortex/domains/
  __init__.py              # Public exports
  models.py                # SemanticDomain, ClassificationResult, RoutingResult, ProposedDomain
  protocol.py              # DomainService protocol
  pg_service.py            # PostgresDomainService — asyncpg implementation
  memory_service.py        # InMemoryDomainService — tests/mock mode
  classifier.py            # DomainClassifier protocol + AgentDomainClassifier (PydanticAI) + MockDomainClassifier
  router.py                # DomainRouter — orchestrates classify → permissions → provision → extract
```

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | Domain Data Model & Storage | DONE | Models, protocol, PG + in-memory services, migration 008, 13 tests passing | `feat(domains): add semantic domain data model, migration, and storage services` |
| 2 | Classification Agent | DONE | DomainClassifier protocol, AgentDomainClassifier (PydanticAI/Gemini), MockDomainClassifier (keyword-based), 4 settings added, 8 tests passing | `feat(domains): add classification agent with PydanticAI and mock implementations` |
| 3 | Domain Router & Auto-Provisioning | DONE | DomainRouter with classify→permission→provision→extract flow, _sanitize_slug, 9 tests passing | `feat(domains): add domain router with auto-provisioning and permission-aware routing` |
| 4 | Pipeline Integration | DONE | route_episode task, services.py wiring (mock+PG), remember tool routing enqueue, EpisodeProcessor routing, existing tests updated | `feat(domains): integrate domain routing into remember tool and ingestion pipeline` |
| 5 | Integration Tests | DONE | 10 tests: full routing pipeline (3), domain provisioning (2), pipeline integration (5 — remember + ingestion wiring) | `test(domains): add integration tests for domain routing pipeline` |
| 6 | E2E Validation & Documentation | PENDING | | |

Statuses: `PENDING` → `IN_PROGRESS` → `DONE` | `BLOCKED`

---

## Stage 1: Domain Data Model & Storage

**Goal**: Define the domain data model (Pydantic models), create PostgreSQL migration, implement PG and in-memory services, seed the 4 initial domains.

**Dependencies**: None

### Steps

1. **Create `src/neocortex/domains/__init__.py`** — export public API:
   ```python
   from neocortex.domains.models import (
       ClassificationResult,
       DomainClassification,
       ProposedDomain,
       RoutingResult,
       SemanticDomain,
   )
   from neocortex.domains.memory_service import InMemoryDomainService
   from neocortex.domains.pg_service import PostgresDomainService
   from neocortex.domains.protocol import DomainService
   ```

2. **Create `src/neocortex/domains/models.py`** — Pydantic models:

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

3. **Create `src/neocortex/domains/protocol.py`** — DomainService protocol:
   ```python
   @runtime_checkable
   class DomainService(Protocol):
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

4. **Create `migrations/init/008_ontology_domains.sql`**:
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

   INSERT INTO ontology_domains (slug, name, description, schema_name, seed) VALUES
   ('user_profile', 'User Profile & Preferences',
    'Personal preferences, goals, habits, values, opinions, communication style, routines, and work style preferences. Knowledge about what the user likes, dislikes, wants to achieve, and how they prefer to work.',
    'ncx_shared__user_profile', true),
   ('technical_knowledge', 'Technical Knowledge',
    'Programming languages, frameworks, libraries, tools, architecture patterns, APIs, technical concepts, best practices, and engineering approaches. Knowledge about technologies, how they work, and how to use them.',
    'ncx_shared__technical_knowledge', true),
   ('work_context', 'Work & Projects',
    'Ongoing projects, tasks, deadlines, team members, organizations, meetings, decisions, and professional activities. Knowledge about what is being worked on, by whom, and when.',
    'ncx_shared__work_context', true),
   ('domain_knowledge', 'Domain Knowledge',
    'General factual knowledge, industry concepts, scientific facts, business concepts, market trends, and domain-specific expertise. Broad knowledge that does not fit the other specific categories.',
    'ncx_shared__domain_knowledge', true)
   ON CONFLICT (slug) DO NOTHING;
   ```

5. **Create `src/neocortex/domains/pg_service.py`** — PostgreSQL implementation (`PostgresDomainService`):
   - Constructor takes `PostgresService` (same pattern as `PostgresPermissionService` in `permissions/pg_service.py`)
   - All queries use `asyncpg` parameterized queries (`$1`, `$2`) via `self._pg.pool`
   - `list_domains()` → `SELECT * FROM ontology_domains ORDER BY id`
   - `get_domain(slug)` → `SELECT * FROM ontology_domains WHERE slug = $1`
   - `create_domain(...)` → `INSERT INTO ontology_domains (...) VALUES (...) RETURNING *`
   - `update_schema_name(slug, schema_name)` → `UPDATE ... SET schema_name = $1, updated_at = now() WHERE slug = $2`
   - `delete_domain(slug)` → `DELETE FROM ontology_domains WHERE slug = $1 AND seed = false` (protect seed domains, return True/False)
   - `seed_defaults()` → same INSERT as migration with `ON CONFLICT DO NOTHING` (idempotent)

6. **Create `src/neocortex/domains/memory_service.py`** — in-memory implementation (`InMemoryDomainService`):
   - Stores domains in `dict[str, SemanticDomain]`
   - Auto-increments IDs
   - `seed_defaults()` populates the 4 seed domains **with `schema_name` pre-set** (e.g., `ncx_shared__user_profile`) so that `_ensure_schema()` short-circuits without needing `SchemaManager`
   - `delete_domain()` protects seed domains
   - Used for tests and `NEOCORTEX_MOCK_DB=true` mode

### Verification

- [ ] `uv run python -c "from neocortex.domains import SemanticDomain, DomainService, InMemoryDomainService"` succeeds
- [ ] Write `tests/test_domain_models.py`:
  - InMemoryDomainService `seed_defaults()` creates 4 domains with `schema_name` pre-set
  - `list_domains()` returns all 4
  - `get_domain("user_profile")` returns correct domain with `schema_name="ncx_shared__user_profile"`
  - `create_domain()` with new slug succeeds
  - `create_domain()` with duplicate slug raises error
  - `update_schema_name()` persists
  - `delete_domain()` on seed domain returns False
  - `delete_domain()` on non-seed domain returns True
- [ ] `uv run pytest tests/test_domain_models.py -v` passes

**Commit**: `feat(domains): add semantic domain data model, migration, and storage services`

---

## Stage 2: Classification Agent

**Goal**: Build a PydanticAI agent that classifies incoming knowledge into semantic domains, plus a deterministic mock for tests.

**Dependencies**: Stage 1

### Steps

1. **Create `src/neocortex/domains/classifier.py`**:

   **Protocol**:
   ```python
   @runtime_checkable
   class DomainClassifier(Protocol):
       async def classify(self, text: str, domains: list[SemanticDomain]) -> ClassificationResult: ...
   ```

   **AgentDomainClassifier** — PydanticAI implementation:
   - Constructor: `__init__(self, model_name: str, thinking_effort: ThinkingLevel = "low")`
   - Creates `pydantic_ai.Agent` with `ClassificationResult` as result type
   - System prompt built dynamically from current domain list using f-strings (matching the existing extraction agent pattern — no Jinja2 dependency):
     ```python
     domain_lines = "\n".join(
         f"- {d.slug}: {d.name}\n  {d.description}" for d in domains
     )
     prompt = f"""You are a knowledge classification agent for a memory system.
     Classify incoming knowledge into one or more semantic domains.

     GUIDELINES:
     - CONSERVATIVE: strongly prefer existing domains over proposing new ones.
     - UNIFYING: knowledge should consolidate into fewer, broader domains, not scatter.
     - MULTI-LABEL: a single piece of knowledge may belong to multiple domains.
     - Only propose a new domain if the knowledge genuinely does not fit ANY existing domain.
     - New domains must be broad cross-cutting categories, NOT narrow topics or source-specific silos.
     - Set confidence >= 0.3 for relevant domains, higher for strong matches.

     Available domains:
     {domain_lines}

     Classify the following knowledge text. Return matched domains with confidence scores."""
     ```
   - `classify(text, domains)` → runs the agent with the text as user message
   - Uses the same Gemini model as extraction pipeline (configurable via settings)

   **MockDomainClassifier** — deterministic keyword-based classifier for tests:
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
   # Domain routing (upper ontology — automatic knowledge routing to shared graphs)
   domain_routing_enabled: bool = True
   domain_classifier_model: str = "gemini-3-flash-preview"
   domain_classifier_thinking_effort: ThinkingLevel = "low"
   domain_classification_threshold: float = 0.3
   ```
   Note: These use the `domain_` prefix to avoid collision with existing `ontology_model` / `ontology_thinking_effort` settings which configure the extraction pipeline's ontology agent (node/edge type proposals).

### Verification

- [ ] Write `tests/test_domain_classifier.py`:
  - MockDomainClassifier: "I prefer Python for backend work" → `user_profile` + `technical_knowledge`
  - MockDomainClassifier: "We need to ship project X by Friday" → `work_context`
  - MockDomainClassifier: "React hooks simplify state management" → `technical_knowledge`
  - MockDomainClassifier: "The theory of relativity explains..." → `domain_knowledge`
  - MockDomainClassifier: fallback for text with no keywords → `domain_knowledge`
  - All returned confidences are above 0.3
- [ ] `uv run pytest tests/test_domain_classifier.py -v` passes

**Commit**: `feat(domains): add classification agent with PydanticAI and mock implementations`

---

## Stage 3: Domain Router & Auto-Provisioning

**Goal**: Build the `DomainRouter` service that orchestrates classification, permission checking, schema auto-provisioning, and extraction job enqueuing.

**Dependencies**: Stage 1, Stage 2

### Steps

1. **Create `src/neocortex/domains/router.py`**:

   ```python
   class DomainRouter:
       def __init__(
           self,
           domain_service: DomainService,
           classifier: DomainClassifier,
           schema_mgr: SchemaManager | None,
           permissions: PermissionChecker,
           job_app: procrastinate.App | None = None,
           classification_threshold: float = 0.3,
       ) -> None:
           ...
   ```

   **`route_and_extract(agent_id, episode_id, episode_text) -> list[RoutingResult]`**:
   1. Fetch current domains via `domain_service.list_domains()`
   2. Classify episode text via `classifier.classify(text, domains)` — **wrapped in try/except**: on classification failure, log with `action_log=True` at warning level and return `[]` (graceful degradation; the Procrastinate retry will handle transient failures, but systematic errors should not block the pipeline)
   3. Filter matches below `classification_threshold`
   4. If `proposed_domain` is not None and `schema_mgr is not None`, call `_provision_domain()` and append to matches (skip provisioning when no schema manager — mock mode)
   5. For each matched domain:
      a. `get_domain(slug)` — skip if not found
      b. `_ensure_schema(domain, agent_id)` — get or create shared schema; skip domain if returns None
      c. Check `permissions.can_write_schema(agent_id, schema_name)` — skip if no permission
      d. `_enqueue_extraction(agent_id, episode_id, schema_name)` — defer `extract_episode` task
      e. Append `RoutingResult` to results
   6. Log routing results and return

   **`_provision_domain(proposed: ProposedDomain, agent_id: str) -> SemanticDomain`**:
   1. Sanitize slug (lowercase, alphanumeric + underscores only)
   2. Create domain via `domain_service.create_domain(slug, name, description, created_by=agent_id)`
   3. Create shared schema via `schema_mgr.create_graph(agent_id="shared", purpose=slug, is_shared=True)` (caller guarantees `schema_mgr is not None`)
   4. Compute `schema_name = f"ncx_shared__{slug}"`
   5. Grant permissions: `permissions.grant(agent_id, schema_name, can_read=True, can_write=True, granted_by="domain_router")`
   6. Update domain: `domain_service.update_schema_name(slug, schema_name)`
   7. Log: `logger.bind(action_log=True).info("domain_provisioned", ...)`
   8. Return the created domain

   **`_ensure_schema(domain: SemanticDomain, agent_id: str) -> str | None`**:
   1. If `domain.schema_name` is not None, return it (schema already mapped — this is the common path for seed domains)
   2. If `schema_mgr is None`, return None (mock mode — cannot provision schemas dynamically)
   3. Otherwise: `schema_name = f"ncx_shared__{domain.slug}"`
   4. Create shared schema via `schema_mgr.create_graph(agent_id="shared", purpose=domain.slug, is_shared=True)` (idempotent — `SchemaManager` handles duplicates)
   5. Grant permissions to `agent_id` if not already granted
   6. Update domain's schema_name
   7. Return schema_name

   **`_enqueue_extraction(agent_id, episode_id, target_schema) -> int | None`**:
   1. If `job_app is None`, return None
   2. Defer `extract_episode` task: `job_app.configure_task("extract_episode").defer_async(agent_id=agent_id, episode_ids=[episode_id], target_schema=target_schema)`
   3. Log routing event
   4. Return job_id

2. **Add `RoutingResult` to `src/neocortex/domains/models.py`** (if not already there from Stage 1):
   - Already defined in Stage 1 models list

### Verification

- [ ] Write `tests/test_domain_router.py`:
  - **Setup**: InMemoryDomainService (seeded) + MockDomainClassifier + InMemoryPermissionService + mock SchemaManager
  - Test: "I prefer Python" → routes to `user_profile` + `technical_knowledge` schemas
  - Test: agent without write permission to `ncx_shared__user_profile` → that schema is skipped
  - Test: agent with admin status → bypasses permission check, routes to all matched schemas
  - Test: classifier proposes new domain with `schema_mgr` present → domain auto-created, schema provisioned, agent gets permissions
  - Test: classifier proposes new domain with `schema_mgr=None` → proposal skipped, no error
  - Test: `_ensure_schema` is idempotent (calling twice for same domain doesn't error)
  - Test: `_ensure_schema` returns None when `schema_mgr=None` and domain has no `schema_name`
  - Test: classification matches below threshold are filtered out
  - Test: classifier raises exception → `route_and_extract` returns `[]` (graceful degradation)
- [ ] `uv run pytest tests/test_domain_router.py -v` passes

**Commit**: `feat(domains): add domain router with auto-provisioning and permission-aware routing`

---

## Stage 4: Pipeline Integration

**Goal**: Wire the domain router into the remember tool, ingestion pipeline, and Procrastinate job system. Update service initialization to create and wire domain services.

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
       """Route an episode to shared graphs via domain classification."""
       logger.info("route_episode_started", agent_id=agent_id, episode_id=episode_id)
       from neocortex.jobs.context import get_services

       services = get_services()
       domain_router = services.get("domain_router")
       if domain_router is None:
           logger.debug("route_episode_skipped_no_router")
           return

       results = await domain_router.route_and_extract(
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
     domain_router: "DomainRouter | None"
     ```

   - In the **mock_db** path (around line 41), after creating permissions:
     ```python
     domain_router = None
     if settings.domain_routing_enabled:
         from neocortex.domains import InMemoryDomainService
         from neocortex.domains.classifier import MockDomainClassifier
         from neocortex.domains.router import DomainRouter

         domain_svc = InMemoryDomainService()
         await domain_svc.seed_defaults()
         domain_router = DomainRouter(
             domain_service=domain_svc,
             classifier=MockDomainClassifier(),
             schema_mgr=None,           # No schema provisioning in mock mode
             permissions=permissions,
             job_app=None,
             classification_threshold=settings.domain_classification_threshold,
         )
     ```
     Add `domain_router=domain_router` to the mock ServiceContext return.

   - In the **PG** path (around line 56), after creating `pg_permissions` and before creating `job_app`:
     ```python
     domain_router = None
     if settings.domain_routing_enabled:
         from neocortex.domains import PostgresDomainService
         from neocortex.domains.classifier import AgentDomainClassifier
         from neocortex.domains.router import DomainRouter

         domain_svc = PostgresDomainService(pg)
         await domain_svc.seed_defaults()
         domain_classifier = AgentDomainClassifier(
             model_name=settings.domain_classifier_model,
             thinking_effort=settings.domain_classifier_thinking_effort,
         )
         # DomainRouter created after job_app (needs it for enqueuing)
     ```
     After `job_app` creation, create the router:
     ```python
     if settings.domain_routing_enabled and domain_svc is not None:
         domain_router = DomainRouter(
             domain_service=domain_svc,
             classifier=domain_classifier,
             schema_mgr=schema_mgr,
             permissions=pg_permissions,
             job_app=job_app,
             classification_threshold=settings.domain_classification_threshold,
         )
     ```
     Add `domain_router=domain_router` to the PG ServiceContext.

3. **Update `src/neocortex/tools/remember.py`** — add routing enqueue after the existing extraction block (after line 71):
   ```python
   # Enqueue domain routing if enabled (routes to shared domain graphs)
   # Requires: job_app (implies extraction_enabled), routing enabled, no explicit target
   if job_app and settings.domain_routing_enabled and target_graph is None:
       await job_app.configure_task("route_episode").defer_async(
           agent_id=agent_id, episode_id=episode_id, episode_text=text,
       )
       logger.bind(action_log=True).info(
           "domain_routing_enqueued",
           episode_id=episode_id,
           agent_id=agent_id,
       )
   ```
   Note: `job_app` is only created when `extraction_enabled=True`, so checking `job_app` implicitly gates on extraction being enabled. `domain_routing_enabled` is an additional opt-out. Routing is skipped when `target_graph is not None` (explicit targeting takes precedence).

4. **Update `src/neocortex/ingestion/episode_processor.py`**:

   - Add `domain_routing_enabled: bool = True` to `__init__` constructor parameters
   - Store as `self._domain_routing_enabled`
   - Add `_enqueue_routing()` method:
     ```python
     async def _enqueue_routing(
         self, agent_id: str, episode_id: int, text: str, target_schema: str | None = None,
     ) -> None:
         """Enqueue domain routing job if enabled and no explicit target.

         Requires self._job_app (which implies extraction_enabled) and
         self._domain_routing_enabled. Skipped when target_schema is set
         (explicit targeting takes precedence over automatic routing).
         """
         if not self._job_app or not self._domain_routing_enabled or target_schema is not None:
             return
         await self._job_app.configure_task("route_episode").defer_async(
             agent_id=agent_id, episode_id=episode_id, episode_text=text,
         )
         logger.bind(action_log=True).info(
             "domain_routing_enqueued",
             episode_id=episode_id,
             agent_id=agent_id,
             source="ingestion",
         )
     ```
   - Call `await self._enqueue_routing(agent_id, episode_id, text, target_schema)` after `_enqueue_extraction()` in:
     - `process_text()` (after line 70)
     - `process_document()` (after line 89) — use the decoded `text` variable
     - `process_events()` (after line 105) — use `event_text`

5. **Update `src/neocortex/ingestion/app.py`** — pass `domain_routing_enabled=settings.domain_routing_enabled` to `EpisodeProcessor()` constructor (find the EpisodeProcessor instantiation and add the kwarg).

### Verification

- [ ] `uv run python -c "from neocortex.jobs.tasks import route_episode"` — task importable
- [ ] `NEOCORTEX_MOCK_DB=true uv run python -m neocortex` — server starts without errors
- [ ] `NEOCORTEX_MOCK_DB=true uv run python -m neocortex.ingestion` — ingestion starts without errors
- [ ] `uv run pytest tests/ -v` — all existing tests still pass (no regressions)
- [ ] Verify services.py correctly creates domain services in both mock and PG paths

**Commit**: `feat(domains): integrate domain routing into remember tool and ingestion pipeline`

---

## Stage 5: Integration Tests

**Goal**: Integration tests covering cross-cutting domain routing flows end-to-end with in-memory implementations.

**Dependencies**: Stage 4

### Steps

1. **Create `tests/test_domain_e2e.py`** — integration tests covering **cross-cutting flows** not already covered by unit tests in Stages 1-3. Avoid duplicating tests from `test_domain_models.py`, `test_domain_classifier.py`, and `test_domain_router.py`.

   **`TestFullRoutingPipeline`** — end-to-end flow through all components:
   - Uses InMemoryDomainService + MockDomainClassifier + InMemoryPermissionService
   - `test_episode_classified_and_routed` — text flows from classification through permission check to RoutingResult with correct schema names
   - `test_multi_domain_episode` — "I prefer Python for my project deadline" → routes to 2+ domain schemas in a single call
   - `test_admin_routes_to_all_matched` — admin agent bypasses permission checks, routes to all matched schemas

   **`TestDomainProvisioning`** — new domain lifecycle:
   - Mock the classifier to return a ProposedDomain
   - `test_new_domain_created_and_routed` — proposed domain created in service, schema provisioned, agent gets permissions, routing result returned
   - `test_provisioning_skipped_without_schema_mgr` — when `schema_mgr=None` (mock mode), proposed domain does not cause error

   **`TestPipelineIntegration`** — remember tool and ingestion processor wiring:
   - `test_remember_enqueues_routing` — remember tool with no target_graph enqueues `route_episode`
   - `test_remember_explicit_target_skips_routing` — remember tool with `target_graph` does NOT enqueue routing
   - `test_ingestion_enqueues_routing` — EpisodeProcessor enqueues routing after extraction
   - `test_routing_disabled` — when `domain_routing_enabled=False`, no routing jobs enqueued
   - `test_backward_compat` — existing personal graph extraction still happens alongside routing

2. **Ensure existing tests pass** — run full test suite and fix any regressions caused by new `domain_router` field in ServiceContext.

### Verification

- [ ] `uv run pytest tests/test_domain_e2e.py -v` — all new tests pass
- [ ] `uv run pytest tests/ -v` — all existing tests still pass (no regressions)
- [ ] Coverage: cross-cutting routing flows, domain provisioning lifecycle, pipeline integration (remember + ingestion)

**Commit**: `test(domains): add integration tests for domain routing pipeline`

---

## Stage 6: E2E Validation & Documentation

**Goal**: Full end-to-end validation, update CLAUDE.md codebase map and architecture rules, finalize plan document.

**Dependencies**: Stage 5

### Steps

1. **Run full E2E validation**:
   - `uv run pytest tests/ -v` — full test suite green
   - `NEOCORTEX_MOCK_DB=true uv run python -m neocortex` — MCP server starts cleanly
   - `NEOCORTEX_MOCK_DB=true uv run python -m neocortex.ingestion` — ingestion API starts cleanly
   - Check startup logs for domain service initialization messages

2. **Update `CLAUDE.md`** codebase map — add domains module under `src/neocortex/`:
   ```
   domains/               # Semantic domain routing (upper ontology)
     models.py            # SemanticDomain, ClassificationResult, RoutingResult
     protocol.py          # DomainService protocol
     pg_service.py        # PostgreSQL implementation
     memory_service.py    # In-memory implementation (tests/mock)
     classifier.py        # PydanticAI classification agent + mock
     router.py            # DomainRouter — classify → route → extract
   ```

3. **Add architecture rule to `CLAUDE.md`** (as rule #7):
   ```
   **7. Domain routing is additive, not replacing.**
   Personal graph extraction continues unchanged. Domain routing adds shared-graph
   extraction jobs alongside personal ones. When `target_graph` is explicitly set,
   domain routing is skipped (explicit beats automatic). The `ontology_domains` table
   maps semantic domains to shared schemas. Classification uses the same Gemini model
   as extraction. New domains auto-provision shared schemas and grant write permissions
   to the originating agent. Note: "ontology" in `domains/` refers to the upper
   ontology (semantic domain categories), distinct from the extraction pipeline's
   ontology agent (node/edge type proposals in `extraction/`).
   ```

4. **Update migration reference** in CLAUDE.md:
   - Change `migrations/init/` comment from `(001-006)` to `(001-008)`

5. **Finalize this plan document** — mark all stages as DONE with notes and commit hashes in the progress tracker.

### Verification

- [ ] `uv run pytest tests/ -v` — all tests green
- [ ] CLAUDE.md codebase map includes `domains/` module
- [ ] CLAUDE.md architecture rules include rule #7 about domain routing
- [ ] `NEOCORTEX_MOCK_DB=true uv run python -m neocortex` — clean startup with domain service logs
- [ ] Plan document has all stages marked DONE

**Commit**: `docs(domains): add E2E validation, update CLAUDE.md, and finalize plan 11`

---

## Overall Verification

After all stages are complete, run:

```bash
# Unit tests
uv run pytest tests/test_domain_models.py tests/test_domain_classifier.py tests/test_domain_router.py -v

# Integration tests
uv run pytest tests/test_domain_e2e.py -v

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
- **Chosen**: A — same Gemini model (configurable via `domain_classifier_model` setting)
- **Rationale**: Consistent quality, simpler configuration. Classification is a lightweight prompt so cost difference is negligible.

### Decision: Feature flag interaction
- `domain_routing_enabled` controls whether routing jobs are enqueued
- Routing depends on `job_app` existing, which requires `extraction_enabled=True`
- Therefore: `extraction_enabled=False` implicitly disables routing (no job queue available)
- No explicit cross-check needed — the `if job_app and settings.domain_routing_enabled` guard handles both cases naturally
