# Plan 32: Episodic + Long-Term Memory E2E Validation

**Date**: 2026-04-15
**Branch**: mem-machine
**Predecessors**: [Plan 31 — Episodic Memory Improvements](../31-episodic-memory-improvements/)
**Goal**: Validate that Plan 31's episodic memory improvements (session tagging, neighbor expansion, STM boost, structured output) work correctly end-to-end against a live PostgreSQL-backed server, and that episodic recall integrates properly with long-term knowledge graph recall.

---

## Context

Plan 31 implemented five features inspired by the MemMachine paper:
1. **Session tagging** — `session_id` + `session_sequence` on episodes
2. **FOLLOWS edges** — temporal spine between consecutive personal episodes
3. **Temporal neighbor expansion** — nucleus + 1 before + 2 after from same session
4. **Short-term recency boost** — 1.5x linear-decay multiplier for episodes < 2h old
5. **Structured output** — `formatted_context` JSON grouping episodes by session, with role-bias embedding

All five stages were validated with unit tests using `InMemoryRepository` (mock DB). However, **no E2E test exists** that validates these features against a live MCP server + PostgreSQL:

| Feature | Unit test (mock DB) | E2E test (live server) |
|---------|:-------------------:|:----------------------:|
| Session tagging on episodes | Yes | **No** |
| FOLLOWS edges in extraction | Yes | **No** |
| Neighbor expansion in recall | Yes | **No** |
| STM boost scoring | Yes | **No** |
| Formatted context JSON | Yes | **No** |
| Episodic + graph node co-ranking | Partial | **No** |

This plan creates a single E2E test script (`scripts/e2e_episodic_memory_test.py`) that exercises all Plan 31 features against a running server, following the established pattern of existing E2E tests (e.g., `e2e_cognitive_recall_test.py`, `e2e_hybrid_recall_test.py`).

**Key constraint**: The `remember` MCP tool does not expose `session_id`. Session-tagged episodes must be ingested via the HTTP ingestion API (`POST /ingest/text` with `session_id` field). Recall is performed via the MCP `recall` tool.

**Update (Stage 6)**: Running the E2E test against a live server revealed five bugs — including a production-breaking neighbor expansion bug that made the MemMachine feature non-functional. See Stage 6 for details.

---

## Strategy

**Phase A — Ingestion & Session Recall (Stages 1-2)**: Create the test script, ingest a realistic multi-turn conversation as session-tagged episodes via the ingestion API, then recall and verify session clustering, neighbor expansion, and chronological ordering.

**Phase B — Scoring Validation (Stage 3)**: Ingest episodes and verify that the STM boost and recency scoring affect recall ordering as expected — recent episodes should rank higher than stale ones with equivalent semantic relevance.

**Phase C — Full Pipeline (Stages 4-5)**: Wait for extraction to complete, verify that extracted knowledge graph nodes and FOLLOWS edges exist in the DB, then test combined recall that returns both episodic matches and graph-node matches in a single query. Validate `formatted_context` JSON structure end-to-end.

**Phase D — Bug Fixes (Stage 6)**: Fix the production and infrastructure bugs discovered during E2E execution. Includes: startup race condition in `manage.sh`, token file override, 1-based session sequences, and a production-breaking neighbor expansion bug in `adapter.py` + `recall.py` where neighbors were always truncated before reaching the caller.

---

## Success Criteria

| Metric | Baseline | Target | Rationale |
|--------|----------|--------|-----------|
| Session-tagged episodes in DB | Not tested E2E | All ingested episodes have correct `session_id` + `session_sequence` | Proves session tagging survives real DB round-trip |
| Neighbor expansion in recall | Not tested E2E | Recall with session query returns nucleus + neighbor episodes with `neighbor_of` provenance | Core MemMachine technique validated end-to-end |
| STM boost ordering | Not tested E2E | Recent episode outranks older equivalent in live recall | Proves STM boost integrates with full scoring pipeline |
| FOLLOWS edges in graph | Not tested E2E | At least 1 FOLLOWS edge exists between session episodes after extraction | Proves extraction pipeline creates temporal spine |
| formatted_context JSON valid | Not tested E2E | `formatted_context` field parses as valid JSON with session clusters | Proves structured output survives full pipeline |
| Combined episodic + graph recall | Not tested E2E | Single recall query returns both `source_kind: "episode"` and `source_kind: "node"` items | Proves episodic and long-term memory co-rank |
| Script exit code | N/A | 0 (all assertions pass) | Runnable via `./scripts/run_e2e.sh` |

---

## Files That May Be Changed

### E2E Test Script
- `scripts/e2e_episodic_memory_test.py` (new) -- The main E2E test script exercising all Plan 31 features

### Infrastructure (Stage 6)
- `scripts/manage.sh` -- Stagger startup, fix token file override from `.env`

### Production Bug Fixes (Stage 6)
- `src/neocortex/db/adapter.py` -- Neighbor expansion: episode over-fetch, nucleus-only `seen_episode_ids`, neighbor-preserving truncation
- `src/neocortex/tools/recall.py` -- Neighbor-preserving truncation in recall tool (second truncation site)

### Plan Documentation
- `docs/plans/32-episodic-memory-e2e-validation/index.md` -- This file (progress tracker updates)

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [Test skeleton + session ingestion](stages/01-test-skeleton-and-session-ingestion.md) | DONE | Script skeleton, session data, ingestion via HTTP API, DB verification | test(e2e): add episodic memory test skeleton with session ingestion |
| 2 | [Session recall with neighbor expansion](stages/02-session-recall-with-neighbors.md) | DONE | Recall + neighbor expansion test, cross-session isolation check | test(e2e): add session recall with neighbor expansion validation |
| 3 | [STM boost and recency validation](stages/03-stm-boost-validation.md) | DONE | Backdate helper, fresh episode ingestion, STM boost score comparison (soft check) | test(e2e): add STM boost recency validation |
| 4 | [Extraction pipeline + FOLLOWS edges](stages/04-extraction-and-follows-edges.md) | DONE | Extraction wait helper, FOLLOWS edge verification, extracted nodes check via discover_graphs, wired into main() | test(e2e): add extraction pipeline and FOLLOWS edge validation |
| 5 | [Combined recall + formatted context](stages/05-combined-recall-and-formatted-context.md) | DONE | Combined episodic+node recall, formatted_context JSON validation, graph traversal check, wired into main() | test(e2e): add combined recall and formatted context validation |
| 6 | [Fix bugs found by E2E](stages/06-fix-bugs-found-by-e2e.md) | IN_PROGRESS | Fixed B1-B4 (startup race, token override, 1-based sequences, neighbor expansion dead). B5 (extraction API connection error) still open. Stages 1-3 pass; Stage 4+ blocked on B5. | fix: repair neighbor expansion, startup race, and token override bugs found by E2E |

Statuses: `PENDING` -> `IN_PROGRESS` -> `DONE` | `BLOCKED` | `SKIPPED`

---

## Execution Protocol

To execute this plan, follow this loop for each stage:

1. **Read the progress tracker** above and find the first stage that is not DONE
2. **Read the stage file** -- follow the link in the tracker to the stage's .md file
3. **Read resources** -- if the stage references shared resources,
   find them in the `resources/` directory
4. **Clarify ambiguities** -- if anything is unclear or multiple approaches exist,
   ask the user before implementing. Do not guess.
5. **Implement** -- execute the steps described in the stage
6. **Validate** -- run the verification checks listed in the stage.
   If validation fails, fix the issue before proceeding. Do not skip verification.
7. **Update this index** -- mark the stage as DONE in the progress tracker,
   add brief notes about what was done and any deviations
8. **Commit** -- create an atomic commit with the message specified in the stage.
   Include all changed files (code, config, docs, and this plan's index.md).

Repeat until all stages are DONE or a stage is BLOCKED.

**If a stage cannot be completed**: mark it BLOCKED in the tracker with a note
explaining why, and stop. Do not proceed to subsequent stages.

**If assumptions are wrong**: stop, document the issue in the Issues section below,
revise affected stages, and get user confirmation before continuing.

---

## Issues

**I1 — Neighbor expansion was non-functional in production (Stage 6, B4)**: The MemMachine neighbor expansion feature passed unit tests against `InMemoryRepository` but was dead end-to-end due to two compounding bugs: (a) `seen_episode_ids` included all SQL-matched episodes, preventing any from appearing as neighbors, and (b) two separate `[:limit]` truncations in `adapter.py:recall()` and `tools/recall.py` always cut the lower-scored neighbors. Fixed by over-fetching episodes, restricting nucleus set to top-`limit` by vector_sim, and preserving neighbors of surviving nuclei in both truncation sites.

**I2 — Extraction API connection errors (Stage 6, B5)**: `extract_episode` jobs fail with `pydantic_ai.exceptions.ModelAPIError: Connection error` while `route_episode` jobs succeed. Both use Gemini API but different model calls. Needs investigation — may be rate limiting, model endpoint differences, or timeout on longer extraction calls. Blocks Stages 4-5 of the E2E test.

**I3 — `manage.sh` startup race (Stage 6, B1)**: Both MCP and ingestion servers started concurrently, racing on shared-schema provisioning (`CREATE SCHEMA` + `INSERT INTO graph_registry`). Fixed by waiting for MCP health before starting ingestion. Root cause (no idempotent schema creation) could recur in other deployment scenarios.

**I4 — `.env` overrides caller env vars (Stage 6, B2)**: `manage.sh` sources `.env` with `set -a` which overwrites env vars exported by the caller (`run_e2e.sh`). Fixed with save/restore for `NEOCORTEX_DEV_TOKENS_FILE`. Other env vars could have the same problem in the future.

---

## Decisions

**D1 — Single test script, not multiple**: All stages append to one file (`scripts/e2e_episodic_memory_test.py`) rather than creating separate scripts per feature. This mirrors the pattern of `e2e_cognitive_recall_test.py` which tests a complete cognitive pipeline in one script. The test runs sequentially because later stages depend on data ingested in earlier ones.

**D2 — Ingestion API for session-tagged episodes, MCP tools for recall**: The `remember` MCP tool does not expose `session_id`, so episodes are ingested via `POST /ingest/text` with explicit `session_id`. Recall uses the standard MCP `recall` tool. This tests the realistic path: ingestion API for bulk data, MCP tools for agent interaction.

**D3 — Extraction wait with polling**: Stages that depend on extraction must poll the DB for extraction job completion before asserting on graph state. Use the same `JOB_WAIT_TIMEOUT = 120` / `JOB_POLL_INTERVAL = 3` pattern from `e2e_cognitive_recall_test.py`.

**D4 — Test isolation via unique suffix**: Each test run generates a `uuid.uuid4().hex[:8]` suffix appended to all ingested text, preventing collisions with previous runs on the same DB instance. Same pattern as `e2e_hybrid_recall_test.py`.

**D5 — Neighbor expansion fix: over-fetch + nucleus-only seen set (Stage 6)**: To make neighbor expansion work, the episode SQL now over-fetches (`max(limit*3, limit+10)` candidates), sorts by `vector_sim`, and only the top `limit` become nucleus candidates in `seen_episode_ids`. Over-fetched episodes can still be discovered as session neighbors. Both `adapter.py:recall()` and `tools/recall.py` now truncate by counting only non-neighbor items toward `limit`, preserving neighbors of surviving nuclei. This means the caller may receive more than `limit` items — `limit` primary results plus their session-context neighbors.

**D6 — Session A test data restructured for neighbor coverage (Stage 6)**: Original Session A (4 PG-related turns) was too semantically homogeneous — all episodes matched any PG query via vector similarity, leaving nothing for expansion. Restructured to 6 turns spanning 3 topics (party, PG, hiring) so a PG-specific query hits only turns 3-5 as nucleus, and expansion pulls in adjacent unrelated turns as context neighbors.
