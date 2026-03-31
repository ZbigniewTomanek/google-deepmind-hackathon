# Plan 18: Recall Quality Overhaul

**Date**: 2026-03-31
**Branch**: `recall-quality-overhaul`
**Predecessors**: [Plan 08 — Cognitive Heuristics](../08-cognitive-heuristics.md), [Plan 17 — Entity Normalization](../17-entity-normalization/index.md)
**Goal**: Fix 6 recall quality bugs found in E2E testing — eliminate gravity wells, restore domain routing, add temporal awareness, and harden the extraction pipeline.

---

## Context

An extensive E2E validation ([`demo-data/e2e-memory-test-report.md`](../../demo-data/e2e-memory-test-report.md)) simulated 3 months of daily work (28 episodes, 121 nodes, 45 edges) on a software project. The test revealed systemic quality issues:

| Finding | Severity | Core Issue |
|---------|----------|-----------|
| F1: Domain routing dead | HIGH | `list_domains()` returns `[]` in job context → classifier always returns 0 matches |
| F2: Episode #24 gravity well | MEDIUM | ACT-R activation feedback loop: high access → higher score → more access |
| F3: Specific events invisible | MEDIUM | Low-importance + zero-activation episodes drowned by dominant nodes |
| F4: Node type corruption | MEDIUM | `normalize_node_type` accepts `}`, `{` — malformed LLM JSON passes through |
| F5: Cross-extraction dedup failure | MEDIUM | Same entity typed differently across runs → semantic duplicates |
| F6: No temporal awareness | HIGH | Corrections don't supersede old facts; recency uses `created_at` not `updated_at` |

**Key measurements from E2E:**
- Episode #24 appeared as #1 result in 8/9 queries (including unrelated ones)
- Its activation climbed from 0.49 → 0.91 over 9 queries
- 0% recall rate for specific events (bugs, debugging sessions)
- 33% recall rate for temporal evolution queries (decision reversals)
- Domain routing: 0/28 episodes classified (`domain_count: 0` for all)

**Scoring formula** (5 signals, `scoring.py:50-80`):
```
score = w_vec × vector_sim + w_text × text_rank + w_rec × recency + w_act × activation + w_imp × importance
```
Current weights: vector=0.3, text=0.2, recency=0.1, activation=0.25, importance=0.15

**ACT-R activation** (`scoring.py:27-47`):
```
B_i = ln(access_count + 1) − 0.5 × ln(hours_since + 1)
activation = sigmoid(B_i)
```
Problem: `ln(access_count + 1)` grows without bound, and each recall increments `access_count`.

---

## Strategy

**Phase A — Scoring Fixes (Stages 1–3)**: Address gravity wells and temporal blindness in the retrieval scoring pipeline. This is the highest-priority work because it affects every recall query.

- Stage 1: Cap activation growth & add sublinear dampening
- Stage 2: Add Maximal Marginal Relevance (MMR) diversity reranking
- Stage 3: Temporal recency bias — use `updated_at`, boost recently-corrected content

**Phase B — Domain Routing (Stage 4)**: Fix the domain classifier so shared-graph routing actually functions.

- Stage 4: Fix empty domains bug, add validation & fallback

**Phase C — Extraction Quality (Stages 5–7)**: Harden the extraction pipeline against type corruption, improve cross-extraction consistency, and enable temporal relationships.

- Stage 5: Type name validation in normalization layer
- Stage 6: Fact supersession — seed temporal edge types, detect corrections in extraction
- Stage 7: Cross-extraction type consistency — improve ontology agent type reuse

Stages within each phase are sequential. Phases A, B, and C are independent of each other.

---

## Success Criteria

| Metric | Baseline (E2E) | Target | Rationale |
|--------|----------------|--------|-----------|
| Max activation after 9 queries | 0.91 | ≤ 0.70 | Dampening prevents runaway |
| Queries where single episode is #1 | 8/9 (89%) | ≤ 3/9 (33%) | Diversity reranking breaks monopoly |
| Specific event recall rate | 0% (0/3 queries) | ≥ 66% (2/3) | Low-importance events retrievable |
| Temporal evolution recall rate | 33% (1/3) | ≥ 66% (2/3) | Corrections surface over old facts |
| Domain routing success rate | 0% (0/28) | ≥ 75% (21/28) | Most episodes classify to ≥1 domain |
| Corrupted type names stored | 1+ | 0 | Validation rejects invalid chars |
| Unit test coverage for scoring | existing | +15 tests | New scoring paths covered |

---

## Files That May Be Changed

### Scoring & Recall
- `src/neocortex/scoring.py` — Activation dampening, MMR reranking, temporal recency
- `src/neocortex/mcp_settings.py` — New settings: activation cap, MMR lambda, recency mode
- `src/neocortex/tools/recall.py` — Integrate MMR postprocessor
- `src/neocortex/db/adapter.py` — Include `updated_at` in recall queries, per-query access increment cap

### Domain Routing
- `src/neocortex/domains/router.py` — Validate non-empty domains, add fallback
- `src/neocortex/domains/classifier.py` — Log warning on empty domains, keyword fallback
- `src/neocortex/ingestion/episode_processor.py` — Ensure domains seeded before routing

### Extraction & Normalization
- `src/neocortex/normalization.py` — Character validation regex
- `src/neocortex/extraction/agents.py` — Correction detection prompts, type reuse guidance
- `src/neocortex/extraction/pipeline.py` — Pass entity-type mapping to ontology agent
- `migrations/init/004_seed_ontology.sql` — Add temporal edge types (SUPERSEDES, CORRECTS)

### Tests
- `tests/test_scoring.py` — Dampening, MMR, temporal bias
- `tests/test_normalization.py` — Invalid character rejection
- `tests/test_domain_classifier.py` — Empty domains handling
- `tests/test_domain_router.py` — Fallback routing

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [Activation Dampening](stages/01-activation-dampening.md) | PENDING | | |
| 2 | [MMR Diversity Reranking](stages/02-mmr-diversity-reranking.md) | PENDING | | |
| 3 | [Temporal Recency Bias](stages/03-temporal-recency-bias.md) | PENDING | | |
| 4 | [Domain Classifier Fix](stages/04-domain-classifier-fix.md) | PENDING | | |
| 5 | [Type Name Validation](stages/05-type-name-validation.md) | PENDING | | |
| 6 | [Fact Supersession](stages/06-fact-supersession.md) | PENDING | | |
| 7 | [Type Consistency](stages/07-type-consistency.md) | PENDING | | |

Statuses: `PENDING` -> `IN_PROGRESS` -> `DONE` | `BLOCKED` | `SKIPPED`

---

## Execution Protocol

To execute this plan, follow this loop for each stage:

1. **Read the progress tracker** above and find the first stage that is not DONE
2. **Read the stage file** — follow the link in the tracker to the stage's .md file
3. **Read resources** — if the stage references shared resources,
   find them in the `resources/` directory
4. **Clarify ambiguities** — if anything is unclear or multiple approaches exist,
   ask the user before implementing. Do not guess.
5. **Implement** — execute the steps described in the stage
6. **Validate** — run the verification checks listed in the stage.
   If validation fails, fix the issue before proceeding. Do not skip verification.
7. **Update this index** — mark the stage as DONE in the progress tracker,
   add brief notes about what was done and any deviations
8. **Commit** — create an atomic commit with the message specified in the stage.
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

- **D1**: Chose sublinear dampening (`access_count^0.5`) over hard cap because it preserves the cognitive plausibility of ACT-R while preventing runaway growth. A hard cap creates a cliff; sublinear dampening is a smooth ceiling.
- **D2**: MMR (Maximal Marginal Relevance) chosen over simple deduplication because it balances relevance with diversity — a well-studied IR technique. Lambda parameter gives a tuning knob.
- **D3**: Recency will use `max(created_at, updated_at)` rather than only `updated_at`, so newly-created nodes still get a recency boost. This handles both "new knowledge" and "corrected knowledge" cases.
- **D4**: Domain classifier fix uses a dual approach — fix the root cause (empty domains list) AND add keyword fallback as defense-in-depth, since the LLM classifier may still be too conservative.
