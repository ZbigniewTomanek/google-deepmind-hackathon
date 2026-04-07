# Plan 30: Elastic Upper Ontology

| Field | Value |
| --- | --- |
| Date | 2026-04-06 |
| Branch | `elastic-upper-ontology` |
| Predecessors | Plan 11 (upper ontology routing), Plan 17 (entity normalization), Plan 28 (ontology alignment), Plan 29 (ontology validation) |
| Goal | Make the upper ontology elastic: novel knowledge can create new shared domains and child domains instead of defaulting to the 4 rigid seed domains |

---

## Context

### Problem Statement

After Plans 28/29, the per-domain type ontology is healthy, but the upper
ontology is still rigid. The system starts with 4 seed domains
(`user_profile`, `technical_knowledge`, `work_context`, `domain_knowledge`) and
the current classifier strongly prefers those existing domains. As a result,
novel content is usually absorbed into `domain_knowledge` instead of creating a
more specific shared domain.

### Root Cause Analysis

| # | Root Cause | Severity | Evidence |
| --- | --- | --- | --- |
| 1 | Classifier prompt is too conservative | Critical | `classifier.py` explicitly says to strongly prefer existing domains |
| 2 | `domain_knowledge` is the default fallback | Critical | Keyword fallback currently routes unmatched text to `domain_knowledge` |
| 3 | No hierarchy in `ontology_domains` | High | Domains are flat; there is no `parent_id`, `depth`, or `path` |
| 4 | New domains have no seed guidance | High | `DOMAIN_SEEDS` only covers the 4 hardcoded seeds |
| 5 | No review/reporting loop for taxonomy health | Medium | No report exists for routed volume, type diversity, or catch-all pressure |

### Measurement Note

This codebase does **not** store routed episodes inside shared domain schemas
unless ingestion explicitly sets `target_graph`. Normal routing works as:

1. ingest episode into the personal graph
2. enqueue `route_episode`
3. enqueue shared-schema `extract_episode` jobs with `target_schema`
4. write nodes/edges/types into the shared graph

Therefore this plan measures routing via:
- `ontology_domains`
- `procrastinate_jobs`
- shared-schema nodes/edges/types
- `log/agent_actions.log`

It does **not** use shared-schema `episode` counts as a routing metric.

---

## Strategy

**Approach: correct the measurement model first, then implement elastic domain
creation, then add lightweight hierarchy and reporting.**

### Phase A: Baseline and Correct Diagnostics (Stages 1–2)

Validate the command/query pack and capture the current baseline using the real
routing/storage model.

### Phase B: Elastic Domain Creation (Stages 3–5)

1. Add hierarchy fields to `ontology_domains`
2. Rewrite the classifier to use the domain tree and stop defaulting unmatched
   content to `domain_knowledge`
3. Generate or inherit ontology seeds for newly created domains

### Phase C: Reporting and Re-validation (Stages 6–7)

1. Add a report-only taxonomy steward based on routed-episode counts and
   shared-schema graph usage
2. Re-run the same corpus and compare against the corrected baseline

---

## Success Criteria

| Metric | Baseline | Target |
| --- | --- | --- |
| Successful route jobs for 12-doc corpus | Measure current state | 12 successful `route_episode` jobs |
| Non-seed domains created from novel docs | Measure current state | >=2 |
| Novel docs routed outside `domain_knowledge` | Measure current state | >=3 of docs 07–12 |
| Novel docs left unrouted | Measure current state | <=1 of docs 07–12 |
| Catch-all absorption rate | Measure current state | materially lower than baseline |
| Created domains with non-zero shared graph artifacts | N/A | every created domain |
| Child domains created (`parent_id IS NOT NULL`) | 0 | >=1 |
| Seed generation quality | N/A | >=5 recommended node types and >=5 edge types for a new domain |
| Steward report coverage | N/A | report runs cleanly for all domains |

---

## Files That May Be Changed

### New Files

- `migrations/public/012_domain_hierarchy.sql`
- `src/neocortex/domains/seed_generator.py`
- `src/neocortex/domains/steward.py`
- `scripts/taxonomy_steward.sh`
- `tests/test_seed_generator.py`
- `tests/test_taxonomy_steward.py`

### Modified Files

- `src/neocortex/domains/models.py`
- `src/neocortex/domains/protocol.py`
- `src/neocortex/domains/pg_service.py`
- `src/neocortex/domains/memory_service.py`
- `src/neocortex/domains/classifier.py`
- `src/neocortex/domains/router.py`
- `src/neocortex/domains/ontology_seeds.py`
- `src/neocortex/extraction/pipeline.py`
- `src/neocortex/services.py`
- `src/neocortex/jobs/tasks.py`
- `src/neocortex/mcp_settings.py`
- `tests/test_domain_classifier.py`
- `tests/test_domain_router.py`
- `tests/test_domain_models.py`
- `tests/test_domain_e2e.py`
- `tests/test_jobs.py`
- `docs/plans/30-elastic-upper-ontology/resources/commands.md`
- `docs/plans/30-elastic-upper-ontology/resources/queries.md`

---

## Progress Tracker

| # | Stage | Status | Commit | Notes |
| --- | --- | --- | --- | --- |
| 1 | [Corpus, Diagnostics, and Environment Smoke Check](stages/01-.md) | DONE | — | Q1 split into pre/post-hierarchy variants; corpus + commands validated; 801 unit tests pass; live E2E deferred (Docker infra issue) |
| 2 | [Baseline Experiment](stages/02-.md) | DONE | — | Baseline captured: 4 seed domains only, 0 novel domains created, domain_knowledge absorbed all 6 novel docs (37.5% catch-all rate), 12 route + 24 shared extract jobs all succeeded |
| 3 | [Domain Hierarchy Schema](stages/03-.md) | PENDING | — | Add `parent_id`, `depth`, `path` |
| 4 | [Hierarchical Domain Classifier](stages/04-.md) | PENDING | — | Tree-aware prompt + no forced catch-all fallback |
| 5 | [Dynamic Seed Generation](stages/05-.md) | PENDING | — | Generated/inherited seed guidance for new domains |
| 6 | [Taxonomy Steward Report](stages/06-.md) | PENDING | — | Report-only taxonomy health review |
| 7 | [Re-validation](stages/07-.md) | PENDING | — | Compare against corrected baseline |

---

## Execution Protocol

You are an autonomous agent executing this plan stage by stage.

**Before each stage**
- Read the stage file
- Check dependencies in this tracker
- Read every file listed in the stage's `Files` section before changing code

**During each stage**
- Follow the steps in order
- Run the verification commands exactly as written
- If a query or command disagrees with the current codebase, fix the plan artifact before continuing

**After each stage**
- Run the verification checklist
- Create a single commit with the stage's commit message
- Update this index with the new status and commit hash

**If blocked**
- Log the blocker in `Issues`
- Do not continue past a blocking dependency

---

## Issues

| # | Stage | Severity | Description | Resolution |
| --- | --- | --- | --- | --- |

---

## Decisions

| # | Decision | Rationale |
| --- | --- | --- |
| D1 | Measure routing via `procrastinate_jobs` + shared-schema graph artifacts | Shared-domain routing does not populate shared-schema `episode` tables in the default path |
| D2 | Keep Stage 6 report-only | Taxonomy restructuring is a separate workflow and should not be mixed into the first elastic-routing rollout |
| D3 | Do not auto-create synthetic parent domains | A hallucinated `parent_slug` should not silently create shared graphs with generic metadata |
| D4 | Use parent seed inheritance before LLM generation | New child domains should start from existing context instead of a cold start |
