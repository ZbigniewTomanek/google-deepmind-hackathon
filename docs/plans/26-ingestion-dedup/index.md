# Plan: Ingestion Content Deduplication

**Date**: 2026-04-02
**Branch**: feat/ingestion-dedup
**Predecessors**: None
**Goal**: Track ingested content by SHA-256 hash so users can safely re-ingest daily notes without creating duplicate episodes or triggering redundant extraction jobs.

---

## Context

The NeoCortex ingestion API is fully append-only for episodes. Every call to
`/ingest/text`, `/ingest/document`, `/ingest/events`, `/ingest/audio`, or
`/ingest/video` creates a new episode unconditionally. While the downstream
extraction pipeline is idempotent at the node level (upsert semantics), duplicate
episodes still waste storage, trigger redundant extraction jobs, and pollute the
episodic memory log.

The primary use case: a user wants to periodically re-ingest a directory of daily
notes (markdown files) without manually tracking which ones have already been
processed. The system should compute a content hash (SHA-256), store it alongside
each episode, and skip duplicates automatically — with an optional `force` flag to
override when needed.

**Current episode table columns**: `id, agent_id, content, embedding, source_type,
metadata, access_count, last_accessed_at, importance, consolidated, created_at`.
No hash or unique constraint exists.

**Multi-schema consideration**: Episodes live in per-agent schemas
(`ncx_{agent}__personal`) and shared schemas. Both `store_episode()` and
`store_episode_to()` paths need dedup support. The hash check is agent-scoped —
each agent only sees their own ingestion history.

---

## Strategy

**Phase A (Foundation)**: Add `content_hash` column to the episode table via
migration, update the schema template, and backfill existing schemas (Stages 1-2).

**Phase B (API)**: Expose a batch hash-check endpoint and wire auto-dedup with
`force` flag into all existing ingestion endpoints (Stages 3-4).

**Phase C (Verification)**: Comprehensive tests covering dedup logic, the check
endpoint, force override, and multi-schema behavior (Stage 5).

---

## Success Criteria

| Metric | Baseline | Target | Rationale |
|--------|----------|--------|-----------|
| Duplicate episodes on re-ingestion | Created every time | Skipped by default | Core requirement |
| Hash check latency (batch of 100) | N/A | < 100ms | Must be fast for pre-filtering |
| Existing tests | All pass | All pass + new dedup tests | No regressions |

---

## Files That May Be Changed

### Database
- `migrations/init/011_episode_content_hash.sql` -- New migration: add content_hash column + index
- `migrations/templates/graph_schema.sql` -- Add content_hash to episode DDL + index

### Core
- `src/neocortex/db/protocol.py` -- Add `check_episode_hashes()` and update `store_episode*` signatures
- `src/neocortex/db/adapter.py` -- Implement hash storage, dedup check, hash lookup
- `src/neocortex/db/mock.py` -- In-memory implementation of hash tracking
- `src/neocortex/schema_manager.py` -- Add `ensure_content_hash()` for existing schemas
- `src/neocortex/services.py` -- Call `ensure_content_hash()` during service initialization
- `src/neocortex/models.py` -- Add `content_hash` field to Episode model
- `src/neocortex/graph_service.py` -- Update `create_episode()` to accept/store hash

### Ingestion
- `src/neocortex/ingestion/models.py` -- Add `force` flag to request models, `"skipped"` status, hash fields to result
- `src/neocortex/ingestion/protocol.py` -- Update processor protocol signatures
- `src/neocortex/ingestion/episode_processor.py` -- Hash computation + dedup logic
- `src/neocortex/ingestion/routes.py` -- Add `POST /ingest/check` endpoint

### Tests
- `tests/unit/test_ingestion_dedup.py` -- New: dedup logic tests
- `tests/test_ingestion_api.py` -- Extend with dedup endpoint tests

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [DB Migration](stages/01-db-migration.md) | DONE | Migration 011, template updated, ensure_content_hash() added | `feat(db): add content_hash column to episode table for ingestion dedup` |
| 2 | [Protocol & Repository](stages/02-protocol-and-repository.md) | DONE | Protocol, adapter, mock, Episode model, GraphService updated with content_hash support | `feat(db): add content hash storage and lookup to MemoryRepository` |
| 3 | [Check Endpoint](stages/03-check-endpoint.md) | DONE | HashCheckRequest/Result models, POST /ingest/check route with audit logging | `feat(ingestion): add POST /ingest/check endpoint for batch hash lookup` |
| 4 | [Auto-Dedup in Ingestion](stages/04-auto-dedup-ingestion.md) | DONE | Hash computation, dedup check, force flag, skipped status across all endpoints | `feat(ingestion): auto-dedup ingestion with force override flag` |
| 5 | [Tests](stages/05-tests.md) | DONE | 20 unit tests + 9 API tests; full suite green (756 passed) | `test(ingestion): add dedup and hash check endpoint tests` |

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

[None yet]

---

## Decisions

1. **SHA-256 for content hashing** -- standard, collision-resistant, fast enough for
   text content. Stored as hex string (64 chars).
2. **Agent-scoped dedup** -- each agent's hash check only queries their own episodes
   (filtered by `agent_id`). Agents don't see each other's ingestion history.
3. **`force` flag** -- default `false`. When `true`, skips dedup check and creates
   a new episode even if hash exists. Allows re-processing updated content.
4. **Hash computed on raw content** -- for text, hash the text string. For document
   and media, hash the raw uploaded bytes. Media descriptions from Gemini are
   non-deterministic, so hashing post-description text would never match on
   re-ingestion of the same file. Hashing raw bytes also lets media dedup skip
   the expensive compress+describe pipeline entirely.
5. **`"skipped"` status** -- new `IngestionResult.status` variant alongside
   `"stored"`, `"failed"`, `"partial"`.
