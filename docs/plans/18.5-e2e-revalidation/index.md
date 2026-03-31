# Plan 18.5: E2E Recall Quality Re-Validation

**Date**: 2026-03-31
**Branch**: `memory-updates` (no code changes -- validation only)
**Predecessors**: [Plan 18 -- Recall Quality Overhaul](../18-recall-quality-overhaul/index.md)
**Goal**: Re-run the 28-episode E2E memory test to validate that Plan 18's 7 stages resolved the recall quality issues found in the [original E2E report](../../demo-data/e2e-memory-test-report.md). Executed by Claude using MCP tools -- no test scripts needed.

---

## Context

Plan 18 implemented 7 fixes for recall quality issues discovered in a 28-episode E2E test simulating 3 months of work on the DataWalk Entity Resolution project:

| Fix | Stage | What Changed |
|-----|-------|-------------|
| Activation dampening | 1 | `access_count^0.5` sublinear growth, increment cap = 3/query |
| MMR diversity reranking | 2 | Maximal Marginal Relevance with lambda=0.7 after hybrid scoring |
| Temporal recency bias | 3 | `max(created_at, updated_at)` for nodes, weights rebalanced (recency 0.15, activation 0.20), 1.3x unconsolidated boost |
| Domain classifier fix | 4 | Empty-domains guard, keyword fallback, `seed_defaults` in job context |
| Type name validation | 5 | Invalid char stripping + PascalCase/SCREAMING_SNAKE regex rejection |
| Fact supersession | 6 | SUPERSEDES/CORRECTS edges seeded, 0.5x penalty / 1.2x boost in scoring |
| Type consistency | 7 | `type_examples` injection into ontology + extractor agents, expanded merge-safe groups |

All 7 stages have 45+ passing unit tests. But unit tests validate formulas in isolation -- they don't prove the system works end-to-end with real episodic content over a simulated multi-month project timeline.

**Original E2E baseline** (from `demo-data/e2e-memory-test-report.md`):
- 28 episodes stored, 19/28 extracted (68%), 121 nodes, 45 edges
- Episode #24 dominated 8/9 queries, activation 0.49 -> 0.91
- 0% recall for specific events, 33% for temporal evolution
- 0/28 episodes classified to any domain
- Corrupted type: `Constraint}OceanScience`

### Execution Model

This plan is executed by **Claude with MCP access** -- not by a Python test script. Each stage uses:
- `remember` to store episodes as natural-language memories
- `recall` to test retrieval quality with targeted queries
- `discover_graphs`, `discover_ontology`, `browse_nodes`, `inspect_node` to inspect graph structure
- Direct observation and measurement of returned scores, ranks, and types

### Source Material

Episode content is synthesized from real documentation in the DataWalk ER research repository at `/Users/zbigniewtomanek/PycharmProjects/datawalk-entity-resolution`:
- `docs/mvp-plan/` -- system design, blocking strategies, feature specs
- `docs/Fellegi-Sunter Model Research.md` -- mathematical foundations
- `docs/plans/` -- 43 implementation plans with decisions and benchmarks
- `docs/mvp-plan/00-er-functions/phonetic-encoding.md` -- Metaphone3 details
- `app/config/` -- blocking rules, normalization specs

All 28 episodes are pre-written in [`resources/episodes.md`](resources/episodes.md).
All 9 recall queries are pre-written in [`resources/recall-queries.md`](resources/recall-queries.md).

---

## Strategy

**Phase A -- Setup (Stage 1)**: Verify MCP tools are functional, record baseline graph state before any episodes are stored.

**Phase B -- Ingestion (Stages 2--3)**: Store all 28 episodes via `remember` with specified importance values, then wait for the extraction pipeline to consolidate them into graph nodes and edges.

**Phase C -- Measurement (Stages 4--6)**: Validate domain routing success rate, graph quality (type corruption, consistency), and recall quality (gravity wells, diversity, specific events, temporal evolution).

**Phase D -- Report (Stage 7)**: Compile all metrics into a comparison report saved to `demo-data/e2e-revalidation-report.md`.

All stages are strictly sequential.

---

## Success Criteria

| # | Metric | Baseline (Original E2E) | Target | How Measured |
|---|--------|------------------------|--------|-------------|
| M1 | Max activation after 9 queries | 0.91 | <= 0.70 | Highest `activation_score` across all recall results over 9 queries |
| M2 | Single-episode dominance | 8/9 (89%) | <= 3/9 (33%) | Count queries where the same item holds the #1 rank position |
| M3 | Specific event recall rate | 0% (0/3) | >= 66% (2/3) | 3 queries targeting specific bugs; pass = target episode in top 5 results |
| M4 | Temporal evolution recall rate | 33% (1/3) | >= 66% (2/3) | 3 queries about evolving decisions; pass = latest correction ranks above older version |
| M5 | Domain routing success rate | 0% (0/28) | >= 75% (21/28) | Count episodes classified to >= 1 domain (via graph inspection) |
| M6 | Corrupted type names | 1+ | 0 | `discover_ontology` -- scan all node/edge types for invalid characters |
| M7 | Cross-extraction type consistency | Multiple semantic duplicates | Fewer than baseline | Same entity appearing with different types across extractions |

---

## Files That May Be Changed

This plan produces **no code changes**. Output artifacts:

- `demo-data/e2e-revalidation-report.md` -- Final comparison report (Stage 7)
- This `index.md` -- Progress tracker updated per stage

---

## Progress Tracker

| # | Stage | Status | Notes |
|---|-------|--------|-------|
| 1 | [Setup & Baseline](stages/01-setup-baseline.md) | PENDING | |
| 2 | [Episode Ingestion](stages/02-episode-ingestion.md) | PENDING | |
| 3 | [Extraction Wait & Monitoring](stages/03-extraction-wait.md) | PENDING | |
| 4 | [Domain Routing Validation](stages/04-domain-routing.md) | PENDING | |
| 5 | [Graph Quality Inspection](stages/05-graph-quality.md) | PENDING | |
| 6 | [Recall Quality Measurement](stages/06-recall-measurement.md) | PENDING | |
| 7 | [Report Generation](stages/07-report.md) | PENDING | |

Statuses: `PENDING` -> `IN_PROGRESS` -> `DONE` | `BLOCKED` | `SKIPPED`

---

## Execution Protocol

To execute this plan, follow this loop for each stage:

1. **Read the progress tracker** above and find the first stage that is not DONE
2. **Read the stage file** -- follow the link in the tracker to the stage's .md file
3. **Read resources** -- episodes and recall queries are in `resources/`
4. **Execute** -- use MCP tools as instructed in the stage. Do not write code.
5. **Record measurements** -- capture exact numeric values from MCP responses
6. **Update this index** -- mark the stage as DONE in the progress tracker, add brief notes

Key constraints:
- **Use MCP tools directly** -- `remember`, `recall`, `discover_graphs`, `discover_ontology`, `browse_nodes`, `inspect_node`
- **No code to write** -- this is a measurement plan, not an implementation plan
- **No commits** -- validation only, no codebase changes
- **Record ALL numeric results** -- every activation score, every rank position, every count
- **Be patient with extraction** -- the 3-agent LLM pipeline processes ~1.3 episodes/minute; 28 episodes takes ~22 minutes
- **Episode content** -- use the exact text from `resources/episodes.md`, do not paraphrase

---

## Issues

[Document any problems discovered during execution]

---

## Decisions

[Record any judgment calls made during execution]
