# Plan 31: Episodic Memory Improvements (MemMachine-Inspired)

**Date**: 2026-04-15
**Branch**: mem-machine
**Predecessors**: [Plan 30 — elastic upper ontology](../30-elastic-upper-ontology/)
**Goal**: Make the personal episode memory more robust and chronologically coherent by incorporating key heuristics from the MemMachine paper (arXiv:2604.04853).

---

## Context

The NeoCortex personal graph stores agent episodes as isolated atomic rows in the `episode` table. Episodes are ingested, embedded, and extracted into nodes/edges, but the temporal relationships between them are not explicitly preserved. This causes several problems:

- A recalled episode has no way to surface its conversational context (adjacent turns in the same session)
- The extraction pipeline does not link consecutive episodes with `FOLLOWS` edges, so the knowledge graph contains islands of facts with no temporal spine
- Recency scoring applies the same 7-day half-life to a 2-hour-old episode and a 2-week-old one — the decay curve is appropriate at the week scale but coarse within a session
- Recall returns the top-K episodes by hybrid score but cannot answer "give me the episode plus the 2 that came after it" — a pattern MemMachine shows is critical for conversational queries

**Key findings from MemMachine (arXiv:2604.04853, March 2026):**

The paper presents a ground-truth-preserving architecture that stores raw episodes and optimizes retrieval rather than per-message extraction. Its most transferable results for this system:

| Technique | LongMemEval gain |
|-----------|-----------------|
| Retrieval depth tuning (k: 20→30) | +4.2% |
| Context formatting (structured JSON) | +2.0% |
| Search prompt design | +1.8% |
| Query-role bias correction ("user:" prefix) | +1.4% |
| Sentence-level chunking | +0.8% |

The paper also shows **nucleus + neighboring context expansion** (retrieve matched episode + 1 preceding + 2 following in time) dramatically improves multi-session reasoning, and that sorting final results chronologically before injecting into the LLM context is a low-cost win.

**Identified gaps in current NeoCortex implementation:**

- No `session_id` on episodes — no grouping by conversation/session
- No explicit `FOLLOWS` edges between consecutive episodes (the edge type exists in seed ontology but is never created)
- Recall fetches episodes as isolated units — no temporal neighbor expansion
- Recency decay rate is uniform (168h half-life) — no differentiation between intra-session and cross-session recency
- `_source_episode` property on nodes is not indexed — tracing episode provenance is a full JSONB scan
- Consolidated episodes receive a permanent 0.5× score penalty but are never purged

This plan targets the highest-ROI subset of these gaps.

---

## Strategy

**Phase A — Temporal grounding (Stages 1–2)**: Add `session_id` to the episode schema and create `FOLLOWS` edges in the extraction pipeline to give the knowledge graph a temporal spine. This is purely additive and does not touch recall behavior.

**Phase B — Context-aware recall (Stages 3–4)**: Implement episode neighborhood expansion during recall (MemMachine's nucleus+neighbors strategy) and add differentiated short-term recency boosting so intra-session episodes surface first. Both changes operate in `db/adapter.py` and `scoring.py`.

**Phase C — Output quality (Stage 5)**: Improve how retrieved episodes are formatted for the answer LLM (structured JSON) and add `session_id` + neighbor provenance to recall results so the agent can reason about conversational flow.

---

## Success Criteria

| Metric | Baseline | Target | Rationale |
|--------|----------|--------|-----------|
| Episode sessions queryable | None | `session_id` present on all new episodes | Enables session-aware temporal queries |
| FOLLOWS edges created | 0 per extraction | ≥1 per episode that has a predecessor in same session | Temporal spine in graph |
| Neighbor expansion in recall | Not available | Neighbor episodes returned when requested | MemMachine core technique |
| Short-term recency boost | None (uniform 7d half-life) | Separate boost for episodes < 2h old | Intra-session context surfaces first |
| Unit tests passing | Current | All existing + new tests pass | No regressions |

---

## Files That May Be Changed

### Database Migrations
- `migrations/public/013_episode_session.sql` (new) -- adds `session_id` + `session_sequence` columns to `episode` table (public schema)
- `migrations/graph/007_episode_session.sql` (new) -- same columns for per-agent graph schemas

### Ingestion
- `src/neocortex/ingestion/episode_processor.py` -- propagate `session_id` from ingestion payload into episode metadata

### Ingestion API
- `src/neocortex/ingestion/routes.py` -- accept optional `session_id` in text/event ingestion request body

### Extraction
- `src/neocortex/extraction/pipeline.py` -- after marking episode consolidated, query for previous episode in same session and create `FOLLOWS` edge

### Recall & Scoring
- `src/neocortex/db/adapter.py` -- add optional `expand_neighbors: bool` flag to recall that fetches temporal neighbors of matched episodes
- `src/neocortex/scoring.py` -- add short-term recency boost function (separate from standard recency decay)
- `src/neocortex/mcp_settings.py` -- new settings: `episode_stm_window_hours`, `episode_stm_boost`, `recall_expand_neighbors`

### Tools
- `src/neocortex/tools/recall.py` -- pass `expand_neighbors` setting through to adapter; include `session_id` in returned episode results

### Tests
- `tests/test_episode_session.py` (new) -- tests for session tagging, FOLLOWS edge creation, neighbor expansion
- `tests/test_scoring.py` -- extend with short-term recency boost tests

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [Episode session tagging](stages/01-episode-session-tagging.md) | PENDING | | |
| 2 | [FOLLOWS edge creation in extraction](stages/02-follows-edge-creation.md) | PENDING | | |
| 3 | [Temporal neighbor expansion in recall](stages/03-temporal-neighbor-expansion.md) | PENDING | | |
| 4 | [Short-term recency boost](stages/04-short-term-recency-boost.md) | PENDING | | |
| 5 | [Recall output formatting & provenance](stages/05-recall-output-formatting.md) | PENDING | | |

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

**D1 — session_id is caller-supplied, not auto-generated**: Rather than auto-generating sessions by time-gap heuristics on the server side, the ingestion API will accept an optional `session_id` string. When absent, a UUID is generated per ingestion request. This keeps the system simple and lets clients group episodes explicitly (e.g., one session = one MCP conversation turn batch). Auto-session detection can be added as a follow-up.

**D2 — FOLLOWS edges are graph-local (per-agent schema only)**: Session ordering is a personal memory concern. FOLLOWS edges are written only to the originating agent's personal schema, never to shared domain graphs.

**D3 — Neighbor expansion is opt-in via settings flag**: Adding neighbors to every recall response would inflate token usage. The `recall_expand_neighbors` setting (default `true`) can be disabled for latency-sensitive use cases.

**D4 — Sentence-level sub-indexing deferred**: MemMachine's sentence chunking contributes only +0.8% on LongMemEval. The extraction pipeline already achieves fine-grained indexing via entity/relation nodes. Sentence-level chunking is excluded from this plan to keep scope focused.
