# Plan 17: Entity Normalization & Deduplication

**Date**: 2026-03-30
**Branch**: plan-17-entity-normalization
**Predecessors**: [Plan 16 — Graph Quality Fixes](../16-graph-quality-fixes/index.md), [Plan 16.5 — Post-Fix Verification](../16.5-post-fix-verification/index.md)
**Goal**: Achieve robust entity normalization and deduplication so that name variants, type drift, and edge type proliferation no longer cause duplicate nodes or graph fragmentation.

---

## Context

Plan 16 dramatically improved graph quality from 35% → 79% acceptable scenarios (0 fails).
Plan 16.5 verification identified 6 remaining gaps, 4 of which are normalization/dedup problems:

| # | Gap | Severity | Root Cause |
|---|-----|----------|------------|
| 1 | DataForge exists as 2 nodes (Tool + Project) | P2 | `_types_are_merge_safe("Tool","Project")` returns False — prefix heuristic doesn't cover sibling types |
| 2 | "Kafka" and "Apache Kafka" coexist | P3 | Only exact case-insensitive name match; no fuzzy/alias resolution |
| 3 | Precision correction (87→94.2%) not in node content | P2 | Librarian doesn't always propagate quantitative updates |
| 4 | Edge type proliferation (38 types / 69 edges) | P3 | No type name normalization; LLM creates free-form types |

### Current Dedup Stack (3 layers, each with gaps)

```
┌─────────────────────────────────────────────────────┐
│ Layer 1: LLM (Librarian Agent)                      │
│  ✓ Instructed to normalize & check existing nodes   │
│  ✗ find_node_by_name() is exact-match only          │
│  ✗ No fuzzy/semantic fallback for name variants     │
│  ✗ Quantitative corrections sometimes lost          │
├─────────────────────────────────────────────────────┤
│ Layer 2: Adapter (db/adapter.py)                    │
│  ✓ Name-primary dedup with Phase 1/2/3 logic       │
│  ✗ Phase 1 uses exact lower(name) only              │
│  ✗ _types_are_merge_safe uses prefix heuristic only │
│  ✗ No edge type normalization                       │
│  ✗ Trigram GIN index exists but is NEVER used       │
├─────────────────────────────────────────────────────┤
│ Layer 3: Database (SQL constraints)                 │
│  ✓ UNIQUE(source_id, target_id, type_id) on edges   │
│  ✗ No name uniqueness constraint on nodes           │
│  ✗ No alias/synonym table                           │
│  ✗ Edge type names stored as-is (no normalization)  │
└─────────────────────────────────────────────────────┘
```

### Key Technical Observations

1. **Trigram index already exists** (`idx_node_name_trgm` GIN) but is never used for dedup lookups — only for ad-hoc queries. This is the cheapest win.
2. **Edge types have a UNIQUE name constraint** in each schema, but no normalization happens before insertion. "RELATES_TO" vs "relates_to" would collide, but "RELATES_TO" vs "RelatesTo" would not.
3. **Type compatibility** uses a prefix heuristic (`e.startswith(r) or r.startswith(e)`) which misses sibling types like Tool/Project/Software that share a semantic domain but neither is a prefix of the other.
4. **Librarian has `search_existing_nodes()`** (semantic + full-text) but the prompt directs it to use `find_node_by_name()` first, which is exact-match. If the exact match fails, the librarian often creates a new node without falling back to semantic search.

---

## Strategy

**Approach**: Hybrid algorithmic + LLM. Add deterministic normalization where possible (names, types, edge types), leverage existing DB capabilities (trigram index), and enhance LLM tools for ambiguous cases.

### Phase A: Algorithmic Foundation (Stages 1–3)
Build the deterministic normalization layers that work without LLM involvement:
- Name canonicalization utility
- Fuzzy name matching via trigram similarity (using existing GIN index)
- Semantic type hierarchy replacing the prefix heuristic

### Phase B: Pipeline Integration (Stages 4–5)
Wire the normalization into extraction and persistence:
- Edge type normalization before storage
- Enhanced librarian tools with fuzzy search fallback and alias awareness

### Phase C: Validation (Stage 6)
Replay Plan 15's 14 scenarios and verify improvement.

---

## Success Criteria

| Metric | Baseline (Plan 16.5) | Target | Rationale |
|--------|---------------------|--------|-----------|
| Acceptable scenarios | 11/14 (79%) | ≥13/14 (93%) | Fix remaining P2 normalization gaps |
| Fail count | 0/14 | 0/14 | No regressions |
| Node dedup ratio (Person entities) | 1:1 perfect | 1:1 perfect | Maintain |
| Node dedup ratio (Software entities) | 2 nodes for DataForge | 1 node | Type hierarchy merge |
| Name variant dedup | "Kafka" ≠ "Apache Kafka" | Merged or aliased | Fuzzy matching |
| Edge type count | 38 types / 69 edges | ≤20 types / ~70 edges | Normalization + reuse |
| Max edge weight | 1.339 | ≤1.5 | No regression from changes |

---

## Files That May Be Changed

### New Files
- `src/neocortex/normalization.py` — Name & type normalization utilities
- `migrations/init/009_node_alias.sql` — Alias table migration
- `tests/unit/test_normalization.py` — Unit tests for normalization
- `tests/mcp/test_fuzzy_dedup.py` — Integration tests for fuzzy dedup

### Modified Files (Core)
- `src/neocortex/db/adapter.py` — Fuzzy lookup in upsert_node, edge type normalization
- `src/neocortex/db/mock.py` — Mirror changes for InMemoryRepository
- `src/neocortex/db/protocol.py` — Add fuzzy search & alias protocol methods
- `src/neocortex/extraction/agents.py` — Enhanced librarian tools & prompts
- `migrations/templates/graph_schema.sql` — Add alias table to template

### Modified Files (Test)
- `tests/mcp/test_dedup_safety.py` — Expand type hierarchy tests

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [Name Canonicalization Utility](stages/01-name-canonicalization.md) | DONE | 4 functions, 38 tests all passing | |
| 2 | [Fuzzy Name Matching & Alias Table](stages/02-fuzzy-matching.md) | DONE | Migration, protocol, adapter (Phase 1.5), mock, 17 tests passing. names_are_similar tightened to require 2+ word overlap to prevent false positives. | |
| 3 | [Semantic Type Hierarchy](stages/03-type-hierarchy.md) | DONE | 8 merge-safe groups, 4 homonym pairs, _TYPE_TO_GROUP O(1) lookup, prefix fallback retained, 25 new tests + DataForge scenario test | |
| 4 | [Edge Type Normalization](stages/04-edge-type-normalization.md) | DONE | Edge/node type normalization in adapter + mock, similarity dedup in adapter, 10 new tests passing | |
| 5 | [Enhanced Librarian Dedup Tools](stages/05-librarian-tools.md) | DONE | find_similar_nodes tool (exact→alias→fuzzy→semantic chain), updated prompt with quantitative update rules, deprecated find_node_by_name, auto-alias registration in create_or_update_node, 10 Stage 5 tests + schema_manager test fix | |
| 6 | [E2E Validation](stages/06-validation.md) | DONE | 13/14 Acceptable, 1 Partial, 0 Fail (93%). S07 + S08 improved. Target met. | |

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

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Use trigram similarity (pg_trgm) for fuzzy matching instead of embedding similarity | Trigram index already exists, sub-millisecond, deterministic. Embedding similarity better for semantic equivalence but adds latency and non-determinism. Use trigram first, embedding as fallback in librarian tools. |
| D2 | Alias table rather than name rewriting | Preserving original names maintains audit trail. Aliases are additive — never lose information. Canonical name stays on the node; aliases point to it. |
| D3 | Configurable type groups rather than LLM-based type merging | Type merging must be deterministic and fast (called on every upsert). LLM calls would add latency and non-determinism to the hot path. Configurable groups can be extended per-domain. |
| D4 | Normalize edge types to SCREAMING_SNAKE before storage | Convention already exists in ontology agent prompt. Enforcing it algorithmically prevents "RELATES_TO" vs "RelatesTo" vs "relates_to" proliferation. |
