# Plan: Post-Fix Empirical Verification — Plan 16 Graph Quality Fixes

**Date**: 2026-03-30
**Branch**: memory-updates
**Predecessors**: [16-graph-quality-fixes](../16-graph-quality-fixes/index.md) (the fixes), [15-memory-update-experiments](../15-memory-update-experiments/index.md) (original gap analysis)
**Goal**: Empirically verify through live MCP interactions that Plan 16's graph quality fixes resolve the 5 critical issues identified in Plan 15.

---

## Context

Plan 15 ran a series of MCP-based experiments that revealed 5 critical graph quality issues.
Plan 16 implemented fixes across 5 stages. The fixes have unit tests and scripted E2E tests,
but have **not** been validated through the same interactive MCP workflow that originally
found the problems.

This plan replays Plan 15's methodology — store knowledge, recall it, inspect the graph —
with scenarios specifically designed to trigger each bug that was fixed. The server starts
from a clean state.

### What Plan 15 Found (Baseline)

| # | Issue | Plan 15 Behavior | Plan 16 Fix |
|---|-------|-------------------|-------------|
| 1 | Content never updates | Alice says "billing" after 2 updates to "auth" | Librarian requires descriptions; pipeline fallback |
| 2 | Edge type instability | Same edge: IMPLEMENTS→HAS_DEADLINE→FORMER_MEMBER_OF→FOLLOWS | Tool-driven curation + adapter edge dedup |
| 3 | Duplicate nodes (type drift) | "WNP" as 2 nodes (Algorithm vs Metric) | Name-primary lookup + merge-safe type guard |
| 4 | Edge weight creep | Weights 1.0 → 1.75+ in days | Logarithmic reinforcement + micro-decay |
| 5 | No contradiction handling | Old+new coexist, scores near-identical | Librarian tools detect contradictions + update content |

### Scenario Domain

We use a realistic **software team** domain (not toy examples):
- Team "Atlas" building a data pipeline product
- People: Maya (tech lead), Jonas (backend), Priya (ML), Leo (DevOps)
- Project evolves: architecture decisions, team changes, shifting deadlines, experimental results

This domain naturally produces all 5 issue types: people move teams (content updates),
relationships evolve (edge stability), people have multiple roles (type drift),
facts get corrected (contradictions), and information is recalled frequently (weight creep).

---

## Strategy

**Phase A: Baseline & Content Updates** (Stages 1-2)
Establish baseline knowledge, then update facts and verify content actually changes.
Direct test of Plan 16 Stage 1 fix.

**Phase B: Relationship Stability & Dedup** (Stages 3-4)
Store facts that would previously cause edge type drift and node duplication.
Tests Plan 16 Stages 2-4.

**Phase C: Weight & Scoring** (Stage 5)
Recall the same queries repeatedly, verify weights stay bounded.
Tests Plan 16 Stage 5.

**Phase D: Complex Evolution** (Stage 6)
Simulate a realistic 2-week knowledge evolution with corrections, team changes,
and strategic reversals. Holistic integration test.

**Phase E: Verdict** (Stage 7)
Compare results against Plan 15 baseline. Score each of the 14 original scenarios.

---

## Success Criteria

| Metric | Plan 15 Baseline | Target | Rationale |
|--------|-------------------|--------|-----------|
| Content updates reflected | FAIL (stale "billing") | Node content shows latest value | Core P0 fix |
| Nodes per entity after updates | 2+ (type drift dupes) | 1 per entity (verified via browse_nodes) | Dedup fix |
| Edge types per relationship | 5+ types for same rel | 1 stable type per relationship | Edge stability |
| Max edge weight after 10 recalls | 1.75+ | ≤1.5 (ceiling) | Weight management |
| Recall returns current info | Old info ranked equal/higher | Latest info ranked #1 or content correct | Usability |
| Plan 15 scenarios acceptable | 5/14 (35%) | ≥12/14 (86%) | Overall quality gate |

---

## Files That May Be Changed

### Plan outputs (documentation only — no code changes)
- `docs/plans/16.5-post-fix-verification/` — this plan + stage results

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [Baseline: Fresh Graph](stages/01-baseline.md) | DONE | 32 nodes, 24 edges, 4 eps. DataForge 2x (Tool+Project). Person dedup perfect. | |
| 2 | [Content Updates](stages/02-content-updates.md) | DONE | All 3 tests PASS. Maya→Director, Pulsar migration, Aug 1 deadline. CONTRADICTS edge created. | |
| 3 | [Edge Type Stability](stages/03-edge-stability.md) | DONE | REPORTS_TO, MEMBER_OF stable. 28 edge types, meaningful not random. Librarian archives dupes. | |
| 4 | [Node Dedup & Type Drift](stages/04-node-dedup.md) | DONE | Persons 1:1 perfect. DataForge 2 nodes (Tool+Project). Atlas Wiki vs Team Atlas correctly separate. | |
| 5 | [Weight Management](stages/05-weight-management.md) | DONE | Max 1.339 after 10 recalls (ceiling 1.5). Diminishing returns confirmed. Micro-decay working. | |
| 6 | [Complex Knowledge Evolution](stages/06-complex-evolution.md) | DONE | Kafka reversion+Jonas departure PASS. Precision+architecture PARTIAL (episode only). | |
| 7 | [Verdict: Plan 15 Comparison](stages/07-verdict.md) | DONE | 11/14 Acceptable (79%), 0 Fails. Up from 5/14 (35%). Target was 12/14. | |

Statuses: `PENDING` -> `IN_PROGRESS` -> `DONE` | `BLOCKED` | `SKIPPED`

---

## Execution Protocol

This plan is **experiment-driven** (like Plan 15), not code-change-driven.

For each stage:

1. **Read the stage file** for the experiment design
2. **Execute MCP tool calls** as specified (remember, recall, discover_*, browse_nodes, inspect_node)
3. **Log raw results** in the stage file's Results section
4. **Compare** actual vs expected behavior — note PASS/FAIL for each check
5. **Update this index** — mark stage DONE with key findings in Notes
6. **No code commits** — this is a verification plan; results are documented in-plan

### Important

- The MCP server must be running with a **clean database** at Stage 1 start.
- Each stage builds on the accumulated graph from prior stages.
- **Wait for extraction** — after `remember()`, the system asynchronously extracts
  into the graph. Wait ~5 seconds before inspecting graph state, or use `recall()`
  which triggers scoring/traversal.
- If a stage reveals a regression, mark it FAIL and continue — document everything.
- Use `discover_graphs` to find the auto-created graph name after first `remember()`.

---

## Issues

[Document any problems discovered during execution]

---

## Decisions

1. **Same domain, different names** — We use team "Atlas" (not Plan 15's entities) so
   the graph starts truly clean. No leftover state from prior experiments.
2. **No code changes** — This plan only documents MCP interactions and results.
   If issues are found, they inform a follow-up plan.
3. **Extraction timing** — We use `recall()` after `remember()` to ensure extraction
   has completed, since recall triggers graph traversal on extracted nodes.
