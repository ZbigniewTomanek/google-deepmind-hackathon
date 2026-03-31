# Plan 19: Fix E2E Revalidation Failures

**Date**: 2026-03-31
**Branch**: `fix/plan-19-e2e-failures`
**Predecessors**: [Plan 18 -- Recall Quality Overhaul](../18-recall-quality-overhaul/index.md), [Plan 18.5 -- E2E Revalidation](../18.5-e2e-revalidation/index.md)
**Goal**: Fix the 3 FAIL metrics (M4, M5, M6) identified during Plan 18.5 E2E revalidation so that domain routing populates shared graphs, temporal corrections create SUPERSEDES/CORRECTS edges, and LLM reasoning never leaks into type names.

---

## Context

Plan 18.5 re-ran the 28-episode E2E memory test after Plan 18's 7-stage recall quality overhaul. Results: 3/6 hard metrics passed (M1 activation, M2 dominance, M3 specific events), but 3 failed:

| # | Metric | Baseline | Plan 18.5 Result | Target |
|---|--------|----------|-----------------|--------|
| M4 | Temporal evolution recall | 33% (1/3) | **0% (0/3) REGRESSION** | >= 66% |
| M5 | Domain routing success | 0% (0/28) | **0% (0/28) NO CHANGE** | >= 75% |
| M6 | Corrupted type names | 1+ | **4 WORSE** | 0 |

### Root Cause Analysis

**M5 (Domain Routing) -- Permission gap in `_ensure_schema()`**

Log evidence from March 31 is conclusive:
- `domain_classification_result`: `matched_count=1-3` for ALL 29 episodes (LLM classifier works)
- `domain_routing_completed`: `domain_count=0` for ALL episodes (routing blocked)

The classification succeeds but the permission check blocks extraction. Code path:

1. `services.py:114` provisions shared schemas at startup (e.g., `ncx_shared__technical_knowledge`)
2. `router.py:194` -- `_ensure_schema()` finds schema exists, returns **without granting permissions**
3. `router.py:122` -- `can_write_schema(agent_id, schema_name)` returns `False`
4. `router.py:124` -- silently skipped at DEBUG level (invisible in normal logs)

The `_ensure_schema` method only grants permissions in the CREATE path (line 205), never in the EXISTING path (line 194).

**M4 (Temporal Recall) -- Merge-by-name destroys correction signals**

When Episode 26 says "CORRECTION: hybrid approach replaces 8-char strategy", the extraction pipeline:
1. Extractor produces `ExtractedEntity(name="Metaphone3", type_name="Algorithm")`
2. Librarian calls `find_similar_nodes("Metaphone3")` -- finds existing node
3. Librarian calls `create_or_update_node("Metaphone3", ...)` -- **merges INTO existing**
4. Temporal signal lost -- old and new are now the same node; no SUPERSEDES edge

Root causes:
- `ExtractedEntity` schema has no field for temporal signals (`supersedes`, `corrects`)
- Librarian instructions (agents.py:312-320) are passive guidance, not enforced workflow
- `upsert_node()` (adapter.py:529-764) uses name-primary dedup that always merges
- Result: self-referential SUPERSEDES edge impossible (same node)

**M6 (Type Corruption) -- Regex too permissive, no length limit**

Four corrupted types found:
1. `DatasetNoteTheSearchResultsShowed...` (440+ chars) -- LLM reasoning leak
2. `EvidencedocumentOceanography` -- not PascalCase, irrelevant domain
3. `FeatureMergesWithEntityObjectId167` -- node ID embedded
4. `OperationbrCreateOrUpdate...` (300+ chars) -- tool-call reasoning leak

All pass `^[a-zA-Z][a-zA-Z0-9]*$` because there's no length limit, no uppercase-start requirement, and no Pydantic validators on `ProposedNodeType.name` or `ExtractedEntity.type_name`.

---

## Strategy

**Phase A -- Permission Fix (Stage 1)**: Fix `_ensure_schema()` to always grant permissions, add INFO-level logging for grant actions.

**Phase B -- Type Hardening (Stage 2)**: Add max-length, PascalCase word-count limit, uppercase-start regex, and Pydantic validators to catch LLM reasoning leaks before they reach the database.

**Phase C -- Temporal Extraction (Stages 3-4)**: Add temporal signal fields to the extraction schema, strengthen extractor and librarian prompts to detect and act on correction markers.

**Phase D -- Verification (Stage 5)**: Unit tests for all fixes.

**Phase E -- Integration Smoke Test (Stage 6)**: Store 3 targeted episodes via `remember`, verify domain routing populates shared graphs, correction creates SUPERSEDES edge, and type names are clean.

---

## Success Criteria

| # | Metric | Baseline (Plan 18.5) | Target | How Measured |
|---|--------|---------------------|--------|--------------|
| S1 | Domain routing permission grant | 0/28 | 28/28 | `domain_routing_completed` logs show `domain_count > 0` |
| S2 | Corrupted type names (syntactic) | 4 | ≤ 1 | `normalize_node_type()` rejects 3/4 corrupted inputs (length + word-count); 1 semantic issue addressed by prompt engineering |
| S3 | Type name max length + word count | No limit | 60 chars / 5 segments | New unit test + normalization code |
| S4 | Temporal correction edge creation | 0 CORRECTS, 1 SUPERSEDES | >= 1 CORRECTS per correction episode | Librarian creates edges when CORRECTION marker present |
| S5 | All existing tests pass | 45+ | 45+ | `uv run pytest tests/ -v` |

---

## Files That May Be Changed

### Domain Routing (Bug 1: M5)
- `src/neocortex/domains/router.py` -- `_ensure_schema()` permission grant + `__personal__` sentinel
- `src/neocortex/jobs/tasks.py` -- `__personal__` sentinel handling for source_schema
- `src/neocortex/schema_manager.py` -- `node_alias` added to shared schema GRANT
- `src/neocortex/db/roles.py` -- `ensure_pg_role()` accepts Pool|Connection to prevent deadlock
- `src/neocortex/db/scoped.py` -- passes connection (not pool) to `ensure_pg_role`

### Type Validation (Bug 3: M6)
- `src/neocortex/normalization.py` -- Regex fix, max length, uppercase start
- `src/neocortex/extraction/schemas.py` -- Pydantic field validators on type names

### Temporal Extraction (Bug 2: M4)
- `src/neocortex/extraction/schemas.py` -- `supersedes` field on ExtractedEntity
- `src/neocortex/extraction/agents.py` -- Extractor and librarian prompt strengthening
- `src/neocortex/extraction/pipeline.py` -- Post-curation temporal signal check

### Tests
- `tests/unit/test_normalization.py` -- New test cases for corrupted inputs
- `tests/unit/test_domain_routing.py` -- Permission grant test
- `tests/unit/test_extraction_schemas.py` -- Validator tests (new file if needed)

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [Permission Fix](stages/01-permission-fix.md) | DONE | grant() in _ensure_schema existing path + WARNING log level | `fix(routing): grant write permissions` |
| 2 | [Type Name Hardening](stages/02-type-hardening.md) | DONE | 60-char max, 5-segment max, ^[A-Z] regex, Pydantic validators on schemas | `fix(normalization): add length, word-count, uppercase` |
| 3 | [Temporal Schema Extension](stages/03-temporal-schema.md) | DONE | `supersedes` + `temporal_signal` on ExtractedEntity, temporal desc on ExtractedRelation | `feat(extraction): add temporal signal fields` |
| 4 | [Temporal Prompt Strengthening](stages/04-temporal-prompts.md) | DONE | Extractor: temporal detection section with CORRECTS/SUPERSEDES signals + versioned naming. Librarian: MANDATORY temporal workflow replacing passive guidance; context injection surfaces supersedes fields. | `feat(extraction): enforce temporal correction detection` |
| 5 | [Unit Tests](stages/05-unit-tests.md) | DONE | 67 new/modified tests: normalization length/segment rejection, Pydantic validators, domain routing permission grants, temporal fields | `test(plan-19): add unit tests` |
| 6 | [Integration Smoke Test](stages/06-smoke-test.md) | DONE | 3/4 checks pass: domain routing PASS (3 shared graphs populated), type names PASS (0 corrupted), stability PASS. Temporal edges PARTIAL (versioned names created, edges not). | `docs(plan-19): record integration smoke test results` |
| 7 | [Temporal Edge Reinforcement](stages/07-temporal-edge-reinforcement.md) | PENDING | Few-shot examples in librarian prompt, fix contradictory rules, imperative context injection, post-curation fallback | |

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

### Issue 1: `source_schema` sentinel mismatch (found 2026-03-31)

Domain router passes `source_schema=None` to the extract_episode task to mean
"read episodes from personal graph". But the task code can't distinguish `None`
(personal graph) from not-provided (default to target_schema) because
procrastinate serializes both as `null`. Shared-graph extraction read from the
empty shared schema and found no episodes.

**Fix**: String sentinel `"__personal__"` at the router→task boundary.
**Files**: `src/neocortex/domains/router.py`, `src/neocortex/jobs/tasks.py`

### Issue 2: Connection pool deadlock under concurrent tool calls (found 2026-03-31)

`graph_scoped_connection()` acquires a PG connection, then calls
`ensure_pg_role(pool, ...)` which acquires **another** from the same pool.
The librarian agent runs tool calls concurrently (pydantic_ai). With pool
max=10, 10 concurrent tool calls each holding 1 connection and needing 1
more → deadlock.

**Fix**: `ensure_pg_role()` now accepts Pool|Connection; `graph_scoped_connection`
passes the already-held connection.
**Files**: `src/neocortex/db/roles.py`, `src/neocortex/db/scoped.py`

### Issue 3: Missing `node_alias` GRANT in shared schema RLS block (found 2026-03-31)

`_build_rls_block()` grants DML permissions on `node`, `edge`, `episode` but
omits `node_alias` (added in migration 009). Agent roles get
`InsufficientPrivilegeError` when the librarian tries to resolve aliases
during shared-graph extraction.

**Fix**: Added `node_alias` to the GRANT statement.
**File**: `src/neocortex/schema_manager.py`
**Note**: Existing shared schemas need manual GRANT or DB reset.

---

## Decisions

1. **Permission fix approach**: Grant permissions in `_ensure_schema()` on the existing-schema path rather than in services.py startup. Reason: services.py doesn't know which agents will use the system; the router knows the requesting agent.

2. **Type length limit = 60 chars, word limit = 5 segments**: The longest legitimate PascalCase type name in the current graph is ~30 chars / 3-4 segments. 60 chars / 5 segments provides headroom while rejecting 300-440 char LLM leaks and multi-word reasoning contamination (e.g., `FeatureMergesWithEntityObjectId167` = 7 segments). One corrupted type (`EvidencedocumentOceanography`, 29 chars, 2 segments) is a semantic issue not catchable by syntactic rules — addressed by prompt engineering.

3. **Temporal signals via extraction metadata**: Rather than trying to detect corrections post-hoc in the librarian, we add `supersedes` and `temporal_signal` fields to `ExtractedEntity` so the extractor can mark them at extraction time. The librarian then has structured data to act on, not just prompt guidance.
