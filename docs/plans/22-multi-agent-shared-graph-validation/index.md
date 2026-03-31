# Plan: Multi-Agent Shared Knowledge Graph Validation

**Date**: 2026-03-31
**Branch**: `functional-improvements`
**Predecessors**: [Plan 12](../12-manual-e2e-test.md), [Plan 18.5](../18.5-e2e-revalidation/index.md), [Plan 19](../19-fix-e2e-failures/index.md)
**Goal**: Validate that two agents contributing to a shared knowledge graph produce a properly consolidated graph where entities are deduplicated, facts from both agents are merged, and recall returns coherent cross-agent results.

---

## Context

Existing E2E tests (Plans 12, 18.5, 19) validate:
- **Permission enforcement**: alice can write, bob read-only, eve denied (e2e_permission_test.py)
- **Data isolation**: alice's personal graph invisible to bob (e2e_mcp_test.py)
- **Single-agent extraction quality**: entity dedup, content updates, cognitive heuristics (e2e_plan15_scenarios_test.py, e2e_content_update_test.py)

**What is NOT tested**: the full multi-agent shared knowledge consolidation pipeline.
No test verifies that when Alice and Bob both write complementary and overlapping knowledge
about the same domain into a shared graph, the extraction pipeline:
1. Deduplicates entities mentioned by both agents (e.g., both mention "Kubernetes")
2. Merges complementary facts (Alice: "K8s uses etcd", Bob: "K8s runs pods")
3. Handles conflicting facts (Alice: "v1.28", Bob: "v1.29")
4. Produces correct recall results for either agent querying the shared graph
5. Maintains cognitive heuristic correctness (activation, importance) in shared context

This is a critical gap because shared graphs are the primary collaboration mechanism
between agents in NeoCortex — the feature that makes it a *multi-agent* memory system
rather than N independent single-agent memory stores.

### Test Domain

The test uses a realistic **software project knowledge base** scenario:
- **Project Titan**: a distributed data pipeline being built by a team
- **Agent Alice**: the backend engineer who knows about system architecture, databases, and APIs
- **Agent Bob**: the ML engineer who knows about model training, data quality, and feature engineering
- Both share knowledge about the project's overall goals, team structure, and timeline

This creates natural overlap (both know team members, project name, deadlines) and
natural complementarity (different technical domains), which exercises both dedup and merge.

---

## Strategy

**Phase A: Infrastructure Setup (Stage 1)**
Start services fresh, create the shared graph, grant permissions to alice and bob.

**Phase B: Knowledge Ingestion (Stages 2-3)**
Alice ingests her perspective (5 episodes about backend architecture).
Wait for extraction. Bob ingests his perspective (5 episodes about ML pipeline).
Wait for extraction. Both write to the same shared graph via `target_graph`.

**Phase C: Consolidation Verification (Stages 4-5)**
Verify the shared graph state: entity counts, deduplication quality, edge coherence.
Run targeted recall queries from both agents and verify cross-agent knowledge access.

**Phase D: Advanced Scenarios (Stage 6)**
Test conflict resolution (contradictory facts), permission boundaries (eve denied),
and cognitive heuristics (activation/importance in shared context).

**Phase E: Report (Stage 7)**
Compile all metrics, compare to targets, produce verdict.

---

## Success Criteria

| # | Metric | Target | Rationale |
|---|--------|--------|-----------|
| M1 | Entity dedup rate | ≥ 70% of shared entities appear as single nodes | Both agents mention same entities; extraction should merge them |
| M2 | Cross-agent recall | ≥ 8/10 recall queries return relevant results from both agents' contributions | Shared graph must serve both agents equally |
| M3 | Complementary fact merge | ≥ 3/5 multi-facet entities have properties from both agents | Proves knowledge is consolidated, not siloed |
| M4 | Conflict handling | Newer/higher-importance fact ranks above older in ≥ 2/3 conflict queries | Temporal and importance signals must work in shared context |
| M5 | Permission enforcement | 0 unauthorized accesses (eve sees nothing, bob's write denied if read-only) | Regression check on existing permission tests |
| M6 | No corrupted types | 0 invalid node/edge type names in shared graph ontology | Extraction quality must hold under multi-agent load |
| M7 | Recall score sanity | Max activation score ≤ 0.80 across all shared-graph queries | No single item should dominate shared recall |

---

## Files That May Be Changed

### Test Script (new)
- `scripts/e2e_multi_agent_shared_test.py` -- New E2E test script for multi-agent validation

### Plan Documentation
- `docs/plans/22-multi-agent-shared-graph-validation/` -- This plan directory

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [Infrastructure Setup](stages/01-infrastructure-setup.md) | PENDING | | |
| 2 | [Alice Knowledge Ingestion](stages/02-alice-ingestion.md) | PENDING | | |
| 3 | [Bob Knowledge Ingestion](stages/03-bob-ingestion.md) | PENDING | | |
| 4 | [Shared Graph Consolidation Check](stages/04-consolidation-check.md) | PENDING | | |
| 5 | [Cross-Agent Recall Validation](stages/05-cross-agent-recall.md) | PENDING | | |
| 6 | [Advanced Scenarios](stages/06-advanced-scenarios.md) | PENDING | | |
| 7 | [Report & Verdict](stages/07-report.md) | PENDING | | |

Statuses: `PENDING` -> `IN_PROGRESS` -> `DONE` | `BLOCKED` | `SKIPPED`

---

## Execution Protocol

This plan is executed via CLI — **not by writing a Python test script**. The executor
(Claude agent) runs each stage by making MCP tool calls, HTTP requests, and SQL queries
directly using the CLI tools documented in `resources/commands.md`.

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
8. **Commit** -- No code commits for this plan. This is a validation-only plan.
   Update the plan files with results as you go.

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

- **Test domain**: Software project (Project Titan) chosen for natural overlap + complementarity
- **Execution mode**: CLI-driven (curl, MCP tools via ingest.sh) rather than Python script, matching Plan 12/18.5 methodology
- **Shared graph**: Explicit `target_graph` parameter (not domain routing) to control exactly what lands in the shared graph
- **Agent tokens**: alice-token and bob-token from dev_tokens_test.json, admin-token-neocortex for setup
