# Plan: Memory Update Semantics — Empirical Validation

**Date**: 2026-03-30
**Branch**: memory-updates
**Predecessors**: [Research: 02-memory-systems-research](../../research/02-memory-systems-research.md)
**Goal**: Empirically test whether NeoCortex handles knowledge updates well enough for real personal/team usage, document gaps, and compare against a working consolidation system.

---

## Context

NeoCortex is being prepared for real-world usage where knowledge *evolves*: facts change,
decisions get revised, people move teams, deadlines shift, experimental results supersede
prior assumptions. The current architecture has two layers:

1. **Episodes** — append-only raw memories (never merged/deduplicated)
2. **Extracted graph** — nodes UPSERT by `(name, type)`, edges by `(source, target, type)`

The extraction pipeline uses a 3-agent system (ontology → extractor → librarian) that
deduplicates at extraction time. But there is:
- **No explicit contradiction handling** (no CONTRADICTS edge type)
- **No consolidation process** (unlike the telegram bot's LLM-driven delta reconciliation)
- **No temporal versioning** of node content/properties
- **Properties shallow-merge** — new keys override old, no history
- **Content uses COALESCE** — keeps old value if new is null (may not update)

### Reference systems

**Telegram bot** (`memory_consolidation_task.py`) — a working system that:
- Runs scheduled LLM-driven consolidation (every 2 days)
- Generates structured diffs: ADD/UPDATE/REMOVE against current persistent state
- Tracks `first_seen/last_seen` dates and `active/archived/deprecated` status lifecycle
- Uses deterministic SHA1 IDs for cross-run deduplication

**Research doc** (`02-memory-systems-research.md`) recommends:
- CONTRADICTS edge type for conflict resolution
- LLM-driven consolidation during idle states (Zettelkasten pattern)
- Ebbinghaus decay curves for selective forgetting
- Intelligent pruning of redundant episodes

### Real-world use case

Plan `36d-precision-first-blocking` (ER engine) demonstrates the knowledge complexity
that memory must support: evolving experimental results across scale tiers, configuration
changes, strategic decisions that supersede prior ones, cross-plan context spanning months.

---

## Strategy

**Phase A: Functional Experiments** (Stages 1-4)
Test basic update mechanics through MCP: store, recall, update, observe.
Each stage builds on prior knowledge in the graph.

**Phase B: Realistic Workload** (Stages 5-6)
Simulate real ER domain knowledge accumulation and evolution.
Test whether the system supports the kind of work in Plan 36d.

**Phase C: Gap Analysis** (Stage 7)
Compare observed behavior against telegram bot and research recommendations.
Document what works, what's missing, and what to build next.

---

## Success Criteria

| Metric | Baseline | Target | Rationale |
|--------|----------|--------|-----------|
| Basic fact recall | Unknown | Correct results for simple queries | System must work at all |
| Updated fact recall | Unknown | Returns latest info, not stale | Critical for real usage |
| Contradiction handling | Unknown | Document actual behavior | Need to know the gap |
| Domain knowledge queries | Unknown | Useful answers from accumulated context | The real use case |
| Gap documentation | None | Comprehensive comparison doc | Informs roadmap |

---

## Files That May Be Changed

### Plan outputs (documentation only — no code changes)
- `docs/plans/15-memory-update-experiments/` — this plan + results
- `docs/plans/15-memory-update-experiments/resources/` — experiment logs

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [Baseline: Remember & Recall](stages/01-baseline.md) | DONE | 3 episodes → 32 nodes, 23 edges. Recall works. CONTRADICTS/SUPERSEDES types created proactively but unused. | |
| 2 | [Fact Updates](stages/02-fact-updates.md) | DONE | 1 Alice node (dedup works). 4 edges (additive). Content NOT updated (COALESCE keeps old). Episodes save the day via recency. | |
| 3 | [Contradictions & Corrections](stages/03-contradictions.md) | DONE | Both old+new always coexist. Score gaps tiny (0.754 vs 0.742). "CORRECTION:" framing helps via keyword match. No semantic contradiction handling. | |
| 4 | [Entity Property Evolution](stages/04-property-evolution.md) | DONE | Episodes preserve all data points (good). Edge types drift chaotically across extraction runs (bad). Duplicate WNP nodes due to type mismatch. | |
| 5 | [Domain Knowledge Accumulation](stages/05-domain-knowledge.md) | DONE | Complex queries work well — rich recall with graph context. UPDATE episode ranked #8/10 (buried by activation). Graph context is the real value. | |
| 6 | [Temporal & Importance Effects](stages/06-temporal-importance.md) | DONE | Activation measurable (+0.006/recall). Edge weight creep to 1.75+. importance=1.0 still beaten by high-activation episodes. Final: 57 nodes, 52 edges, 25 episodes. | |
| 7 | [Gap Analysis & Recommendations](stages/07-gap-analysis.md) | DONE | 5/14 acceptable, 6/14 partial, 3/14 failed. Key gaps: no consolidation cycle, content never updates, edge type instability, no staleness signals. | |

Statuses: `PENDING` -> `IN_PROGRESS` -> `DONE` | `BLOCKED` | `SKIPPED`

---

## Execution Protocol

This plan is **experiment-driven**, not code-change-driven. Each stage:

1. **Read the stage file** for the experiment design
2. **Execute MCP tool calls** (remember, recall, discover) as specified
3. **Log raw results** in the stage file's Results section
4. **Analyze** — compare actual vs expected behavior
5. **Update this index** — mark stage DONE with key findings in Notes
6. **No commits per stage** — this is a research plan; commit the full results at the end

The MCP server should be running fresh (empty graph) at Stage 1 start.

---

## Issues

1. **Node content never updates** — COALESCE(new, old) keeps old value. Alice still says "billing team" after 2 updates saying "auth team". Root cause needs investigation (adapter.py upsert_node logic).
2. **Edge type instability** — Extraction LLM changes edge types every run. Same edge gets re-typed randomly (IMPLEMENTS → HAS_DEADLINE → FORMER_MEMBER_OF → FOLLOWS). Makes relationship semantics meaningless.
3. **Node type drift** — Same problem as edges. Metaphone3: Person → Algorithm → Metric → Document → Fact across runs.
4. **Edge weight creep** — Spreading activation adds +0.05/recall. Weights reach 1.75+ after many recalls. Frequently-accessed subgraphs dominate regardless of query.
5. **Duplicate nodes from type mismatch** — "WNP Pruning Algorithm" exists as 2 nodes (id=53 and id=56) because extracted with different type_ids.

---

## Decisions

1. **Consolidation cycle is the #1 priority** — Following the telegram bot pattern (LLM-driven delta reconciliation against current state). Without this, knowledge evolution is broken.
2. **Content updates are a quick win** — Likely a small code change in adapter.py. Should be the first fix.
3. **Type stability requires extraction pipeline changes** — Feed current schema to extraction LLM as context to constrain outputs.
4. **The episode layer is the safety net** — Despite graph quality issues, episode-based recall works because episodes preserve raw text and benefit from recency. The system is more robust than the graph alone would suggest.
