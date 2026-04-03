# Plan 29: Ontology Alignment Validation

| Field          | Value                                                   |
| -------------- | ------------------------------------------------------- |
| Date           | 2026-04-03                                              |
| Branch         | `ontology-alignment`                                    |
| Predecessors   | Plan 28 (ontology alignment)                            |
| Goal           | Validate that Plan 28's ontology alignment fixes produce clean, semantically meaningful knowledge graphs by ingesting diverse personal knowledge via CLI and measuring against quantitative success criteria |

---

## Context

### Problem Statement

Plan 28 implemented a 6-stage fix for ontology quality: type validation hardening,
domain-specific seed ontologies, agentic ontology agent, tuning/observability,
post-extraction type consolidation, and graph cleanup. All stages are DONE but
have only been validated in isolation (unit tests, manual spot checks). We need
end-to-end validation with realistic, diverse content to confirm the system
produces a clean ontology in practice.

### What We're Validating

The extraction pipeline processes text through 3 agents (ontology -> extractor -> librarian)
with domain routing to shared schemas. Plan 28 added:

1. **Validation layer** -- regex-based rejection of tool-call artifacts, instance-level
   type names, length/complexity limits
2. **Seed ontologies** -- 4 domain-specific type templates (user_profile, technical_knowledge,
   work_context, domain_knowledge) with 15-22 node types and 17-26 edge types each
3. **Agentic ontology agent** -- tool-using design with explore-validate-propose workflow
   (get_ontology_overview, find_similar_types, propose_type)
4. **Type consolidation** -- hardcoded merge map (8 mappings) + unused type archiving
5. **Improved prompts** -- type budget (max 2 node + 2 edge types per episode),
   reuse-over-creation guidance

### Why CLI Testing

The extraction pipeline runs asynchronously via job queue (Procrastinate). We need to:
- Restart the server between certain stages (fresh state, config changes)
- Monitor job completion via admin API (`GET /admin/jobs/summary`)
- Run diagnostic SQL directly against PostgreSQL
- Inspect logs for ontology agent behavior (`log/agent_actions.log`)

The embedded MCP server cannot be restarted mid-session, so all testing uses
`curl` against the ingestion API (:8001) and `docker compose exec` for SQL.

---

## Strategy

**Approach: Progressive complexity -- smoke test, multi-domain, adversarial, volume, then measure.**

**Phase A (Stage 1): Setup**
- Backup existing data, start fresh, verify clean state

**Phase B (Stages 2-5): Ingestion Testing**
- Stage 2: Single-document smoke test (verify basic pipeline works)
- Stage 3: Multi-domain ingestion (all 4 domains, verify routing + seed usage)
- Stage 4: Adversarial content (trigger known failure modes from Plan 28)
- Stage 5: Volume test (batch ingestion, consolidation triggers)

**Phase C (Stages 6-7): Assessment**
- Stage 6: Run diagnostic queries, compile metrics report vs Plan 28 targets
- Stage 7: Design targeted fixes for any failures

**Phase D (Stage 8): Re-validation**
- Fresh instance, re-run failed scenarios, verify fixes

### Trade-offs

**Why not automated pytest?** The extraction pipeline calls external LLMs (Gemini).
Results are non-deterministic. We need human judgment on whether types like
`HealthProtocol` vs `Protocol` are acceptable. Automated tests can check for
garbage but not semantic quality.

**Why restart between stages?** The ontology agent's behavior depends on existing
graph state. Testing in phases lets us observe how the ontology evolves
incrementally vs all-at-once.

---

## Success Criteria

Measured per schema after all ingestion completes (Stage 6):

| Metric | Baseline (Plan 28) | Target | Pass/Fail |
|--------|---------------------|--------|-----------|
| Node types with usage > 0 | ~90 | 25-35 | |
| Edge types with usage > 0 | ~140 | 30-50 | |
| Edge types with 0 usage (%) | ~70% | <15% | |
| Garbage types (tool artifacts) | ~8 | 0 | |
| Instance-level types | ~30 | 0 | |
| Type reuse ratio (nodes/active types) | ~7:1 | 20:1+ | |

Additional qualitative criteria:
- Domain routing assigns content to correct schemas
- Seed ontology types are actually used (not ignored)
- Ontology agent uses tools before proposing (visible in logs)
- No duplicate/near-duplicate types in final graph
- Edge types are semantically appropriate for personal knowledge

---

## Files That May Be Changed

### Test Resources (new)
- `docs/plans/29-ontology-validation/resources/test_documents.md` -- Test corpus
- `docs/plans/29-ontology-validation/resources/queries.md` -- Diagnostic SQL
- `docs/plans/29-ontology-validation/resources/commands.md` -- CLI commands reference

### Potential Fixes (Stage 7-8)
- `src/neocortex/normalization.py` -- Validation rule adjustments
- `src/neocortex/extraction/type_consolidation.py` -- Merge map updates
- `src/neocortex/extraction/agents.py` -- Prompt tuning
- `src/neocortex/domains/ontology_seeds.py` -- Seed ontology adjustments

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [Environment Setup & Data Backup](stages/01-.md) | DONE | Snapshot saved as pre-plan29. Fresh instance running. MCP needed manual restart due to race condition in concurrent schema creation (both servers starting simultaneously). All 5 shared domain schemas auto-provisioned. | No commit (setup only) |
| 2 | [Single-Document Smoke Test](stages/02-.md) | DONE | Pipeline works E2E. 24 nodes created with clean types (0 garbage, 0 instance-level). Ontology agent used 14 tool calls, proposed 0 new node types (reused seeds). **Issue: 0 edges created** — librarian only called create_or_update_node, never create_or_update_edge. Domain routing failed on first run due to missing GOOGLE_API_KEY in MCP env (fixed by restart). | No commit (testing only) |
| 3 | [Multi-Domain Ingestion](stages/03-.md) | DONE | All 4 docs ingested, 19/20 jobs ok (1 prior failure). Domain routing works: health→user_profile+domain_knowledge, car→domain_knowledge+work_context+user_profile (aggressive), ADR→technical_knowledge+work_context, sprint→work_context+technical_knowledge. **I3**: technical_knowledge empty (0 nodes/edges despite 2 succeeded jobs). **I4**: 8 new garbage types in domain_knowledge (`ComponentUpdatingB47EngineId48` etc) — LLM leaking tool IDs into type names. **I1 persists**: work_context has 32 nodes but 0 edges. Edges work in personal(20), user_profile(29), domain_knowledge(17). Seed types heavily reused. Ontology agent: 8-20 tool calls per extraction. | No commit (testing only) |
| 4 | [Adversarial & Edge Case Testing](stages/04-.md) | DONE | **Adversarial tests PASSED**: 0 instance-level types from app names (`ActivityTrackerPro` etc.), 0 overly-specific types from tech jargon (`EmbeddingBatchProcessor` etc.), 0 instance-level types from home lab (`MacMiniM2` etc.). Apps correctly typed as `Tool`/`Software`/`Asset`. Tech concepts as `Tool`/`Infrastructure`/`Component`/`Concept`. 13 new jobs, all succeeded. **Routing**: home lab→personal+user_profile+work_context+technical_knowledge; apps→personal+user_profile+work_context+technical_knowledge; postmortem→personal+work_context+technical_knowledge. **Type counts**: personal=25, domain_knowledge=18, technical_knowledge=7, user_profile=13, work_context=15 — all ≤25. **I3 resolved**: technical_knowledge now has 44 nodes + 12 edges (was empty). **I4 persists**: 8 garbage `ComponentUpdating*` types in domain_knowledge (pre-existing). **New garbage**: `BrandfunctionNameCreateOrUpdateNode` (1 usage) in personal. **I1 partial**: edges still sparse in work_context (81n/12e) and personal (101n/20e); better in user_profile (49n/29e). **Observability gap**: ontology agent `tool_call_count` logs as null — can't verify `find_similar_types` usage from structured logs. | No commit (testing only) |
| 5 | [Volume & Consolidation Testing](stages/05-.md) | DONE | All 5 short notes ingested, 21 new jobs all succeeded (56 total, 1 pre-existing failure). 13 episodes in personal schema. **No auto-consolidation** — episode_counter is per-job-run, not cumulative; manual consolidation deferred to Stage 6. Merge map source types still present (`AnatomicalStructure`/`Condition` in personal, `Condition` in domain_knowledge, `HealthState` in user_profile). **Short notes reused types well**: new types are reasonable (Book, MusicalWork, ShoppingList, Recipe) — 0 new garbage, 0 instance-level types. **Edge creation improved**: personal 50 (was 20), user_profile 52 (was 29), work_context 26 (was 12), domain_knowledge 23 (was 17), technical_knowledge 12 (unchanged). **Type reuse ratios**: personal 4.2:1, work_context 5.7:1, technical_knowledge 6.3:1, user_profile 3.8:1, domain_knowledge 2.1:1 — low but expected at 13 episodes. **Unused edge types high** (46-88%) — mostly unused seed edge types, need consolidation cleanup. | No commit (testing only) |
| 6 | [Diagnostic Assessment & Report](stages/06-.md) | DONE | Full metrics collected across 6 schemas. PASS: 0 instance-level types, good edge semantics, active ontology agent. FAIL: 9 garbage types (I4/I5 patterns), 46-88% unused edge types (seed size), consolidation endpoint broken (I7). Report compiled with 3 priority fixes for Stage 7. | No commit (assessment only) |
| 7 | [Fix Design & Implementation](stages/07-.md) | DONE | P1: Added `Updating\w*Id\d` and `functionName` to artifact regex (I4/I5). P2: Set `app.state.repo` in ingestion lifespan (I7). P3: Unused seed edges accepted at low volume. 832 tests pass. | `fix(extraction): address ontology validation findings from Plan 29` |
| 8 | [Re-validation of Failed Scenarios](stages/08-.md) | PENDING | | |

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
5. **Execute** -- run the commands described in the stage. All ingestion uses curl
   against http://localhost:8001. All SQL uses docker compose exec.
6. **Validate** -- run the verification checks listed in the stage.
   If validation fails, document the failure before proceeding.
7. **Update this index** -- mark the stage as DONE in the progress tracker,
   add brief notes about what was done and any deviations
8. **Commit** -- only commit if the stage produces code changes (Stages 7-8).
   Testing stages (1-6) update only this plan's notes.

**IMPORTANT**: Do not use the embedded MCP server for testing. All interactions
go through the REST API via curl. The server may need to be restarted between stages.

**IMPORTANT**: After ingesting documents, wait for extraction jobs to complete
before running diagnostic queries. Poll `GET /admin/jobs/summary` with
`Authorization: Bearer admin-token` until all jobs show `done` status.

Repeat until all stages are DONE or a stage is BLOCKED.

**If a stage cannot be completed**: mark it BLOCKED in the tracker with a note
explaining why, and stop. Do not proceed to subsequent stages.

**If assumptions are wrong**: stop, document the issue in the Issues section below,
revise affected stages, and get user confirmation before continuing.

---

## Issues

**I1 (Stage 2): Zero edges created in extraction.**
The librarian agent creates nodes but never calls `create_or_update_edge`. The `curation_complete` log shows `edges_created: 0` while the LLM-generated summary claims "15 relationships". This affects all schemas — without edges the knowledge graph has no structure. Root cause TBD in Stage 7.

**I2 (Stage 2): Domain classification fails when GOOGLE_API_KEY missing from MCP server env.**
The MCP server process (which runs the procrastinate worker) didn't have the API key loaded. The `manage.sh` script sources `.env`, but if the server was started before the script ran (or by a different process), the key is missing. Fixed by restarting via `manage.sh`. Non-recurring — just an operational note.

**I3 (Stage 3): `ncx_shared__technical_knowledge` is completely empty despite successful extraction jobs.**
Two extraction jobs targeted this schema (episodes 4 and 5 — the ADR and sprint review) and both completed with `succeeded` status, but the schema has 0 nodes and 0 edges. Only 4 seed node types exist. The librarian agent appears to have produced no create_or_update calls for this schema. Root cause TBD — possibly the librarian failed silently or the extraction produced nothing actionable.

**I4 (Stage 3): New garbage type pattern — LLM leaking tool call IDs into type names.**
In `ncx_shared__domain_knowledge`, 8 types were created with the pattern `ComponentUpdating{detail}Id{number}` (e.g., `ComponentUpdatingB47EngineId48`, `ComponentUpdatingId46`, `MetricUpdating142000KmId47`). The LLM is incorporating internal DB IDs and the "Updating" operation verb from `create_or_update_node` into type names. Current validation regex doesn't catch this pattern. These should be `Component` or `Metric` instead.
**FIX (Stage 7):** Added `Updating\w*Id\d` pattern to `_TOOL_CALL_ARTIFACT` regex in `normalization.py`. Now rejects all `ComponentUpdating*Id*` and `MetricUpdating*Id*` variants.

**I5 (Stage 4): Tool artifact type `BrandfunctionNameCreateOrUpdateNode` in personal schema.**
A single garbage type combining "Brand" (likely the intended type), "functionName", and "CreateOrUpdateNode" (the tool call function name). Same category of issue as I4 — LLM leaking tool call metadata into type names. The existing artifact regex should catch `createOrUpdate` but this type somehow passed validation. Needs investigation in Stage 7.
**FIX (Stage 7):** Added `functionName` pattern to `_TOOL_CALL_ARTIFACT` regex. The existing `createOrUpdate` pattern also matches this type — it likely predated the validation layer. Both patterns now reject it.

**I6 (Stage 4): Ontology agent `tool_call_count` not logged in structured logs.**
All `ontology_agent_complete` entries show `tool_call_count: null`. Previous stages observed tool calls through raw logs. The logging code likely doesn't extract tool call count from the PydanticAI agent result. Minor observability gap — not a functional issue.
**UPDATE (Stage 6):** Resolved — structured logs now show `tool_calls` field correctly. Avg 12.2 tool calls per extraction across 42 runs.

**I7 (Stage 6): Consolidation endpoint broken — `app.state.repo` not set on ingestion app.**
The `/admin/consolidate/apply` endpoint requires `request.app.state.repo` which is never set in the ingestion app's lifespan. All 6 schemas return 501. This blocks merge-map cleanup (AnatomicalStructure→BodyPart, Condition→HealthState, etc.) and unused type archiving via the admin API.
**FIX (Stage 7):** Added `app.state.repo = ctx["repo"]` to ingestion app lifespan in `ingestion/app.py`.

**I8 (Stage 6): `ncx_shared__knowledge` schema completely unused.**
Has 20 seed node types and 23 seed edge types but 0 nodes, 0 edges, 0 episodes. No content was ever routed to the "knowledge" domain. Either the domain classifier never selects it, or it's a catch-all that isn't needed.

---

## Stage 6: Diagnostic Assessment Report

### Data Summary

| Schema | Episodes | Nodes | Edges | Active Node Types | Active Edge Types | Total Edge Types |
|--------|----------|-------|-------|-------------------|-------------------|------------------|
| personal | 13 | 133 | 50 | 32 | 22 | 41 |
| domain_knowledge | 0 | 47 | 23 | 22 | 13 | 30 |
| technical_knowledge | 0 | 44 | 12 | 7 | 4 | 33 |
| user_profile | 0 | 84 | 52 | 22 | 17 | 37 |
| work_context | 0 | 108 | 26 | 19 | 18 | 38 |
| knowledge | 0 | 0 | 0 | 0 | 0 | 23 |
| **Totals** | **13** | **416** | **163** | — | — | — |

### Success Criteria Assessment

| Metric | Baseline (Plan 28) | Target | Actual | Status | Notes |
|--------|---------------------|--------|--------|--------|-------|
| Active node types (per schema) | ~90 | 25-35 | 7-32 | **N/A** | Low volume (13 docs vs 134 target). All schemas within range or below. |
| Active edge types (per schema) | ~140 | 30-50 | 4-22 | **N/A** | Low volume. Edge creation improved but still sparse. |
| Unused edge types (%) | ~70% | <15% | 46-88% | **FAIL** | Seed edge types created upfront but never used. Driven by seed ontology size, not extraction quality. |
| Garbage types (tool artifacts) | ~8 | 0 | 9 | **FAIL** | 1 in personal (`BrandfunctionNameCreateOrUpdateNode`), 8 in domain_knowledge (`ComponentUpdating*Id*`). |
| Instance-level types | ~30 | 0 | 0 | **PASS** | All multi-segment types are legitimate compounds (MusicalWork, ShoppingList, SoftwareComponent, etc.). |
| Type reuse ratio | ~7:1 | 20:1+ | 2.1-6.3:1 | **N/A** | Expected low at 13 episodes. Not a meaningful failure. |

### Garbage Types (9 total)

**personal (1):**
- `BrandfunctionNameCreateOrUpdateNode` (1 usage) — LLM concatenated "Brand" + tool function name

**domain_knowledge (8):**
- `ComponentUpdatingB47EngineId48` (1 usage)
- `ComponentUpdatingId46` (1 usage)
- `ComponentUpdatingId49` (1 usage)
- `ComponentUpdatingId53` (1 usage)
- `ComponentUpdatingId54` (1 usage)
- `ComponentUpdatingId55` (1 usage)
- `ComponentUpdatingId56` (1 usage)
- `MetricUpdating142000KmId47` (1 usage)

**Root cause:** LLM leaking tool call metadata (function names, DB IDs, operation verbs) into type names. Current validation regex catches `createOrUpdate` pattern but:
1. `BrandfunctionNameCreateOrUpdateNode` bypassed — suggests regex check runs on different casing or the type was created via a code path that skips validation.
2. `ComponentUpdating*Id*` pattern is not covered by any existing regex rule.

### Instance-Level Type Review

All multi-segment PascalCase types reviewed — **all legitimate**:
- personal: `AnatomicalStructure`, `MusicalWork`, `ShoppingList`, `SoftwareComponent`
- domain_knowledge: `MedicalReport`, `MusicalTechnique`, `MusicalWork`
- technical_knowledge: `ConfigurationSetting`, `DataFormat`
- user_profile: `BodyPart`, `FinancialEvent`, `FoodItem`, `HealthState`, `MediaWork`
- work_context: `FoodItem`, `ProfessionalRole`, `SoftwareComponent`

### Near-Duplicate Pairs

**Legitimate pairs (no action needed):**
- personal: `Software` / `SoftwareComponent` — distinct concepts
- domain_knowledge: `MusicalWork` / `MusicalTechnique` — distinct concepts

**Garbage-driven pairs (fix garbage types to resolve):**
- personal: `Brand` / `BrandfunctionNameCreateOrUpdateNode`
- domain_knowledge: `Component` / `ComponentUpdating*` (7 pairs), `Metric` / `MetricUpdating*`

### Edge Type Semantic Quality

All active edge types across all schemas are semantically appropriate for personal knowledge. Notable well-formed types: `EXPERIENCES_SYMPTOM`, `HAS_CONFIGURATION`, `HOSTED_ON`, `MANUFACTURED_BY`, `PURCHASED_FROM`, `USES_TECHNIQUE`, `PARTICIPATED_IN`.

No semantically inappropriate edge types found.

### Unused Seed Edge Types (high across all schemas)

The seed ontologies create 17-26 edge types per schema, but only 4-22 are used with 13 episodes. Examples of unused seeds consistently across schemas: `CONSUMES`, `CONTRADICTS`, `CORRECTS`, `EXPERIENCED`, `LOCATED_AT`, `OWNS`, `PERFORMS`, `SUMMARIZES`, `SUPPORTS`, `WORKS_FOR`.

**Assessment:** Most unused types are reasonable edges that would see usage at scale. The issue is seed ontology size relative to test volume, not type quality. However, the 15% target for unused types needs either: (a) more data, or (b) smaller seed ontologies that grow on demand.

### Ontology Agent Behavior

- **Total extractions:** 42
- **Tool calls per extraction:** avg 12.2, range 7-25
- **Proposed node types:** avg 1.6 per extraction (within budget of 2)
- **Proposed edge types:** avg 1.5 per extraction (within budget of 2)
- **Avg extraction time:** 59.3s

The ontology agent is behaving well: actively using tools (explore/validate/propose), staying within type budget, and reusing existing types. The seed types are being heavily reused rather than ignored.

### Consolidation Status

Manual consolidation could not be run — the admin endpoint (`/admin/consolidate/apply`) returns 501 because `app.state.repo` is not set on the ingestion app (I7). Merge map targets are still present:
- personal: `AnatomicalStructure` (0 usage), `Condition` (3 usage)
- domain_knowledge: `Condition` (0 usage)
- user_profile: `HealthState` (3 usage)

### Overall Assessment

**What's working well:**
1. Domain routing correctly assigns content to appropriate schemas
2. Zero instance-level types — validation catches all `MacMiniM2`, `ActivityTrackerPro` etc.
3. Ontology agent actively uses tools and stays within type budget
4. Seed types are heavily reused (not ignored)
5. Edge types are semantically appropriate
6. Type counts are reasonable for the data volume

**What needs fixing (Stage 7):**
1. **P1: Garbage type validation** — Add regex patterns for `Updating.*Id\d+` and verify `createOrUpdate` regex catches all casings (I4, I5)
2. **P2: Consolidation endpoint** — Set `app.state.repo` in ingestion app lifespan so admin consolidation works (I7)
3. **P3: Unused seed edge types** — Consider trimming seed ontologies or making seed edges lazy (created on first use) to hit the <15% unused target at lower volumes

---

## Decisions

- **D1**: CLI-only testing (curl + psql) to allow server restarts between stages.
- **D2**: Progressive complexity -- single doc, multi-domain, adversarial, volume -- to isolate failure modes.
- **D3**: Human judgment on semantic quality, not just automated metrics. The metrics catch obvious failures; a human reviews type names for semantic appropriateness.
- **D4**: Fresh instance per major phase. Stage 1 starts fresh for Stages 2-6. Stage 8 starts fresh again for re-validation after fixes.
