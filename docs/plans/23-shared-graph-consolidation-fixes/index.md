# Plan: Fix Multi-Agent Shared Knowledge Graph Consolidation

**Date**: 2026-03-31
**Branch**: `functional-improvements`
**Predecessors**: [Plan 22](../22-multi-agent-shared-graph-validation/index.md), [Plan 16](../16-graph-quality-fixes/index.md)
**Goal**: Fix the 3 failing metrics from Plan 22 (M3: content merging, M4: conflict resolution, M7: type resolution) by removing RLS from shared graphs, improving extraction content merging, and hardening the pipeline.

---

## Context

Plan 22 validated multi-agent shared knowledge graph consolidation and produced a
**4/7 PASS → OVERALL FAIL** verdict. The system works as a shared knowledge *store*
(dedup, recall, permissions all pass) but fails as a knowledge *consolidation* system.

### Root Cause Chain

```
RLS UPDATE policy (owner_role = current_user)  [schema_manager.py:233]
  → Bob cannot update Alice's nodes in shared graph
    → UPDATE matches 0 rows → fetchrow() returns None  [adapter.py:728]
      → RuntimeError("Failed to update node")  [adapter.py:729]
        → Entire librarian agent run crashes
          → cleanup_partial_curation deletes all progress  [pipeline.py:154]
            → Retry hits same RLS wall → 3 failed attempts → episode lost
```

This single root cause (RLS blocking cross-agent writes) cascades into:
- **M3 = 0/5 FAIL**: No content merging — Bob's librarian crashes before merging
- **M4 = 0/3 FAIL**: No conflict resolution — corrections can't update existing nodes
- **29% extraction failure rate**: 4/14 jobs failed (RLS + tool call limit combined)

### Additional Issues (not RLS-caused)

| Issue | Location | Impact |
|-------|----------|--------|
| `tool_calls_limit=50` hardcoded | `pipeline.py:181` | Complex episodes (20+ entities) exceed budget |
| `cleanup_partial_curation` deletes all on retry | `pipeline.py:154` | Systemic failures lose all work across 3 retries |
| Recall `item_type` shows "Unknown" | `adapter.py:1624, 1892` | `type_names` map misses IDs not in the local schema's `node_type` table |
| Content UPDATE uses `COALESCE` (replace) | `adapter.py:709` | Even without RLS, new content overwrites old instead of merging |

### Design Decision: Remove RLS from Shared Graphs

**User directive**: Shared knowledge graphs should NOT use row-based permissions.
Other agents must be able to fix false knowledge contributed by any agent.

**Rationale**: The `graph_permissions` table + `PermissionChecker` already validates
access at the API/ingestion boundary. RLS was defense-in-depth but actively prevents
the core feature: cross-agent knowledge consolidation. The `owner_role` column is
retained for audit/provenance tracking but no longer enforced at the DB level.

---

## Strategy

**Phase A: Access Model (Stage 1)**
Remove RLS policies from shared graph creation. Simplify `graph_scoped_connection`
to no longer SET LOCAL ROLE for shared graphs. Keep `owner_role` for provenance.

**Phase B: Content Merging (Stages 2-3)**
Fix `upsert_node` to intelligently merge content instead of replacing it.
Update librarian prompt to be aware of cross-agent contributions and produce
merged descriptions. Make `tool_calls_limit` configurable with a higher default.

**Phase C: Pipeline Robustness (Stage 4)**
Fix `cleanup_partial_curation` to preserve progress when upsert is idempotent.
Handle the `RuntimeError("Failed to update node")` case gracefully as a fallback.

**Phase D: Recall Quality (Stage 5)**
Fix `item_type` resolution to handle cross-schema type lookups. Ensure type names
resolve correctly for all nodes in shared graphs.

**Phase E: Test & Validate (Stage 6)**
Unit tests for all changes. Document how to re-run Plan 22 for E2E validation.

---

## Success Criteria

| Metric | Baseline (Plan 22) | Target | Rationale |
|--------|---------------------|--------|-----------|
| M3: Complementary fact merge | 0/5 (0%) | ≥ 3/5 (60%) | Cross-agent content consolidation works |
| M4: Conflict handling | 0/3 (0%) | ≥ 2/3 (67%) | Corrections and supersessions propagate |
| M7: Recall type resolution | "Unknown" for many nodes | 0 "Unknown" types | Type names always resolved |
| Extraction failure rate | 29% (4/14) | ≤ 10% | Pipeline robust under shared-graph load |
| Unit test coverage | N/A | All changed functions have tests | Regression safety |

---

## Files That May Be Changed

### Schema & Connections
- `src/neocortex/schema_manager.py` -- Remove `_build_rls_block`, keep `owner_role` columns
- `src/neocortex/db/scoped.py` -- Simplify `graph_scoped_connection` (no SET LOCAL ROLE for shared)

### Extraction Pipeline
- `src/neocortex/extraction/pipeline.py` -- Configurable `tool_calls_limit`, smarter cleanup
- `src/neocortex/extraction/agents.py` -- Librarian prompt for cross-agent content merging

### Data Layer
- `src/neocortex/db/adapter.py` -- Content-merging UPDATE logic, type resolution fix, graceful error handling

### Configuration
- `src/neocortex/settings.py` -- New `extraction_tool_calls_limit` setting

### Tests
- `tests/mcp/test_rls.py` -- Update/remove RLS-specific assertions
- `tests/unit/test_extraction_target_schema.py` -- Verify shared graph writes work cross-agent
- `tests/unit/test_shared_graph_consolidation.py` -- New: content merge, type resolution tests

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [Remove RLS from Shared Graphs](stages/01-remove-shared-rls.md) | DONE | Removed RLS policies from shared schema provisioning, simplified graph_scoped_connection (no SET LOCAL ROLE), set owner_role explicitly in INSERT statements for provenance, updated tests | `refactor(shared-graphs): remove RLS from shared schemas, retain owner_role for provenance` |
| 2 | [Content-Merging Upsert](stages/02-content-merging-upsert.md) | PENDING | | |
| 3 | [Extraction Pipeline Hardening](stages/03-extraction-pipeline-hardening.md) | PENDING | | |
| 4 | [Graceful Update Failure Handling](stages/04-graceful-update-failure.md) | PENDING | | |
| 5 | [Fix Recall Type Resolution](stages/05-fix-recall-type-resolution.md) | PENDING | | |
| 6 | [Tests & Validation](stages/06-tests-and-validation.md) | PENDING | | |

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

- **Remove RLS entirely from shared graphs** — user directive: agents must fix each other's false knowledge. App-level `graph_permissions` + `PermissionChecker` already handle authorization at the API boundary.
- **Keep `owner_role` column** — retain for audit/provenance tracking (who contributed what), just don't enforce via RLS.
- **`owner_role` stores raw `agent_id`** — with RLS removed, pg-role-formatted names (`ncx_agent_alice`) are unnecessary overhead. Raw `agent_id` (e.g., `"alice"`) is simpler, more readable, and avoids importing `oauth_sub_to_pg_role` into adapter.py.
- **Content merging = append with separator** — LLM-based synthesis is too expensive per-upsert. Instead, the librarian prompt already instructs merging old+new content; the DB just needs to stop overwriting.
- **Tool call limit as setting** — configurable per-deployment, default raised from 50 to 150.
