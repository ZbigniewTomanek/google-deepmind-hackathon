# Plan 25: Extraction Pipeline Performance Optimization

**Date**: 2026-04-01
**Branch**: `plan-25-extraction-performance`
**Predecessors**: [Plan 07](../07-extraction-pipeline-integration.md), [Plan 11](../11-upper-ontology-routing.md)
**Goal**: Increase extraction throughput via worker parallelism and reduce per-episode latency via batching and caching.

---

## Context

The knowledge extraction pipeline takes **~1 minute per episode** through a 3-agent pipeline (ontology -> extractor -> librarian). Key bottlenecks identified:

| Bottleneck | Location | Impact |
|---|---|---|
| Worker concurrency = 1 | `server.py:26` | Only 1 job at a time, even when jobs target different schemas |
| Polling interval = 5s | Procrastinate default | Up to 5s delay before job pickup |
| Sequential metadata fetches | `pipeline.py:91-99` | 3 DB calls in series before ontology agent |
| Redundant type reload | `pipeline.py:131-132` | Re-fetches types just created by ontology |
| Per-entity embedding calls | `agents.py:714-715` | N individual API calls in librarian's tool loop |
| Blocking cleanup | `pipeline.py:194` | `cleanup_empty_types()` blocks return |

**Safety analysis**: Jobs targeting different `target_schema` values have **zero shared mutable state**. Schema isolation is enforced by PostgreSQL schemas + RLS. Upsert semantics make re-runs idempotent. Concurrent execution across schemas is safe.

---

## Strategy

**Phase A (Stages 1-2)**: Throughput — configurable worker concurrency + polling. The single highest-impact change: enables N-fold throughput for multi-schema workloads.

**Phase B (Stages 3-4)**: Per-episode latency — parallel DB fetches, type cache+merge, pre-computed embedding cache. Cuts ~5-15s per episode.

**Phase C (Stage 5)**: Polish — fire-and-forget cleanup, stage timing instrumentation.

---

## Success Criteria

| Metric | Baseline | Target |
|---|---|---|
| Concurrent extraction jobs | 1 | 4 (configurable via `NEOCORTEX_WORKER_CONCURRENCY`) |
| Job pickup latency | up to 5s | ~1s |
| Metadata fetch overhead | ~30ms (sequential) | ~10ms (parallel) |
| Type reload after ontology | 2 DB round-trips | 0 (cache merge) |
| Per-entity embedding overhead | N individual API calls | 1 batch + cache hits |

---

## Files That May Be Changed

### Configuration
- `src/neocortex/mcp_settings.py` — New `worker_concurrency`, `worker_polling_interval` settings

### Server
- `src/neocortex/server.py` — Pass concurrency/polling to `run_worker_async()`

### Pipeline
- `src/neocortex/extraction/pipeline.py` — asyncio.gather for metadata, type merge, embedding pre-compute, fire-and-forget cleanup

### Agents
- `src/neocortex/extraction/agents.py` — `LibrarianAgentDeps` gains `precomputed_embeddings` dict; `create_or_update_node` checks cache before calling `embed()`

### Tests
- `tests/test_extraction_pipeline.py` or similar — verify parallel fetches, embedding cache, concurrency settings

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [Worker concurrency & polling](stages/01-.md) | PENDING | | |
| 2 | [Parallel metadata fetches](stages/02-.md) | PENDING | | |
| 3 | [Type cache+merge after ontology](stages/03-.md) | PENDING | | |
| 4 | [Pre-computed entity embeddings](stages/04-.md) | PENDING | | |
| 5 | [Fire-and-forget cleanup & polish](stages/05-.md) | PENDING | | |

Statuses: `PENDING` -> `IN_PROGRESS` -> `DONE` | `BLOCKED` | `SKIPPED`

---

## Execution Protocol

To execute this plan, follow this loop for each stage:

1. **Read the progress tracker** above and find the first stage that is not DONE
2. **Read the stage file** — follow the link in the tracker to the stage's .md file
3. **Read resources** — if the stage references shared resources,
   find them in the `resources/` directory
4. **Clarify ambiguities** — if anything is unclear or multiple approaches exist,
   ask the user before implementing. Do not guess.
5. **Implement** — execute the steps described in the stage
6. **Validate** — run the verification checks listed in the stage.
   If validation fails, fix the issue before proceeding. Do not skip verification.
7. **Update this index** — mark the stage as DONE in the progress tracker,
   add brief notes about what was done and any deviations
8. **Commit** — create an atomic commit with the message specified in the stage.
   Include all changed files (code, config, docs, and this plan's index.md).

Repeat until all stages are DONE or a stage is BLOCKED.

**If a stage cannot be completed**: mark it BLOCKED in the tracker with a note
explaining why, and stop. Do not proceed to subsequent stages.

**If assumptions are wrong**: stop, document the issue in the Issues section below,
revise affected stages, and get user confirmation before continuing.

---

## Issues

_(populated during execution)_

---

## Decisions

- **Worker concurrency default = 4**: Chosen because each extraction job makes 3 sequential LLM calls (~30-45s), and 4 concurrent jobs saturate a typical Gemini API quota without overwhelming PG connections.
- **Pre-compute embeddings vs. batch-at-end**: Chose pre-compute because it works within the existing PydanticAI tool-call model without architectural changes. The librarian's `create_or_update_node` can simply check a dict before calling `embed()`.
- **No schema-aware queue routing**: Procrastinate's built-in concurrency semaphore is sufficient for now. Schema-affinity routing would add complexity without clear benefit at current scale.
