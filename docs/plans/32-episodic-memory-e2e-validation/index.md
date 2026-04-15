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

---

## Strategy

**Phase A — Ingestion & Session Recall (Stages 1-2)**: Create the test script, ingest a realistic multi-turn conversation as session-tagged episodes via the ingestion API, then recall and verify session clustering, neighbor expansion, and chronological ordering.

**Phase B — Scoring Validation (Stage 3)**: Ingest episodes and verify that the STM boost and recency scoring affect recall ordering as expected — recent episodes should rank higher than stale ones with equivalent semantic relevance.

**Phase C — Full Pipeline (Stages 4-5)**: Wait for extraction to complete, verify that extracted knowledge graph nodes and FOLLOWS edges exist in the DB, then test combined recall that returns both episodic matches and graph-node matches in a single query. Validate `formatted_context` JSON structure end-to-end.

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

### Plan Documentation
- `docs/plans/32-episodic-memory-e2e-validation/index.md` -- This file (progress tracker updates)

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [Test skeleton + session ingestion](stages/01-test-skeleton-and-session-ingestion.md) | DONE | Script skeleton, session data, ingestion via HTTP API, DB verification | test(e2e): add episodic memory test skeleton with session ingestion |
| 2 | [Session recall with neighbor expansion](stages/02-session-recall-with-neighbors.md) | DONE | Recall + neighbor expansion test, cross-session isolation check | test(e2e): add session recall with neighbor expansion validation |
| 3 | [STM boost and recency validation](stages/03-stm-boost-validation.md) | DONE | Backdate helper, fresh episode ingestion, STM boost score comparison (soft check) | test(e2e): add STM boost recency validation |
| 4 | [Extraction pipeline + FOLLOWS edges](stages/04-extraction-and-follows-edges.md) | PENDING | | |
| 5 | [Combined recall + formatted context](stages/05-combined-recall-and-formatted-context.md) | PENDING | | |

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

[Document any problems discovered during execution]

---

## Decisions

**D1 — Single test script, not multiple**: All stages append to one file (`scripts/e2e_episodic_memory_test.py`) rather than creating separate scripts per feature. This mirrors the pattern of `e2e_cognitive_recall_test.py` which tests a complete cognitive pipeline in one script. The test runs sequentially because later stages depend on data ingested in earlier ones.

**D2 — Ingestion API for session-tagged episodes, MCP tools for recall**: The `remember` MCP tool does not expose `session_id`, so episodes are ingested via `POST /ingest/text` with explicit `session_id`. Recall uses the standard MCP `recall` tool. This tests the realistic path: ingestion API for bulk data, MCP tools for agent interaction.

**D3 — Extraction wait with polling**: Stages that depend on extraction must poll the DB for extraction job completion before asserting on graph state. Use the same `JOB_WAIT_TIMEOUT = 120` / `JOB_POLL_INTERVAL = 3` pattern from `e2e_cognitive_recall_test.py`.

**D4 — Test isolation via unique suffix**: Each test run generates a `uuid.uuid4().hex[:8]` suffix appended to all ingested text, preventing collisions with previous runs on the same DB instance. Same pattern as `e2e_hybrid_recall_test.py`.
