# Plan: Graph Quality Fixes — Tool-Equipped Librarian

**Date**: 2026-03-30
**Branch**: graph-quality-fixes
**Predecessors**: [15-memory-update-experiments](../15-memory-update-experiments/index.md) (empirical validation)
**Goal**: Make NeoCortex actually usable for knowledge evolution by giving the librarian agent tools to query and curate the knowledge graph, replacing the current blind-persist pipeline.

---

## Context

Plan 15 found that NeoCortex gets *worse* at accuracy as more facts are stored.
The root cause is architectural: the librarian agent is a passive normalizer
that produces a static payload blindly persisted via UPSERT. It cannot:
- **See** what already exists in the graph
- **Decide** whether new knowledge adds, updates, or contradicts existing facts
- **Act** on those decisions (update content, merge duplicates, archive stale facts)

The telegram bot's consolidation system — the reference implementation — solves this
with LLM-driven comparison against current state, producing explicit ADD/UPDATE/REMOVE
deltas. NeoCortex needs the same capability, but integrated into the extraction pipeline
rather than as a separate batch process.

### The Fundamental Design Shift

```
CURRENT (broken):
  extractor → librarian(flat name list) → LibrarianPayload → _persist_payload(blind UPSERT)

PROPOSED (working):
  extractor → librarian(retrieval tools + mutation tools) → curated graph state
               ↑ searches for existing entities          ↑ creates/updates/archives directly
               ↑ inspects neighborhoods                  ↑ merges duplicates
               ↑ checks edge conflicts                   ↑ removes stale edges
```

The librarian becomes the **graph's curator** — it receives extracted knowledge,
retrieves relevant subgraphs, and uses tools to reconcile incoming knowledge
with existing state. This replaces `_persist_payload()` with intelligent,
tool-driven persistence.

### Why This Approach Over Batch Consolidation

The telegram bot runs consolidation as a separate batch process (every 2 days).
We integrate curation into the extraction pipeline instead because:
1. **Immediate consistency** — no 2-day window of stale data
2. **Simpler architecture** — no separate scheduler/job for consolidation
3. **Natural context** — the librarian already has the new episode + extracted entities
4. **Incremental cost** — curates per-episode, not full-graph review

A batch consolidation cycle could be added later for periodic full-graph cleanup,
but the per-episode curation handles the critical path.

### Issues from Plan 15

| # | Issue | Root Cause | How This Plan Fixes It |
|---|-------|-----------|----------------------|
| 1 | Content never updates | COALESCE keeps old; librarian drops descriptions | Stage 1: SQL fix. Stage 3: librarian updates content via tool |
| 2 | Edge type instability | Blind UPSERT creates new edge per type change | Stage 3: librarian checks existing edges before creating |
| 3 | Node type drift | Agents see only type names, not entity→type mappings | Stage 2: retrieval tools show existing entity types |
| 4 | Edge weight creep | Linear +0.05/recall, no continuous decay | Stage 5: bounded reinforcement + micro-decay |
| 5 | Duplicate nodes | UPSERT key (name, type_id) creates dupes on type drift | Stage 3: librarian searches by name first. Stage 4: adapter safety net |
| 6 | Unbounded context | `list_all_node_names()` no LIMIT, breaks at 50K nodes | Stage 2: replaced by bounded retrieval tools |

---

## Strategy

**Phase A: Quick Win** (Stage 1)
Fix the COALESCE bug independently — small change, immediate value.

**Phase B: Tool-Equipped Librarian** (Stages 2-3)
The core architectural change. Stage 2 adds read-only retrieval tools so the librarian
can see the graph. Stage 3 adds mutation tools so it can curate the graph, and rewires
the pipeline to use tool-driven persistence instead of `_persist_payload()`.

**Phase C: Defense in Depth** (Stage 4)
Adapter-level safety nets for when the LLM makes mistakes despite having tools.
Name-primary node dedup, source-target edge dedup. These are fallbacks, not primary fixes.

**Phase D: Scoring** (Stage 5)
Fix edge weight creep independently.

---

## Success Criteria

| Metric | Baseline (Plan 15) | Target | Rationale |
|--------|---------------------|--------|-----------|
| Node content after update | Stale (keeps first value) | Reflects latest knowledge | Core correctness |
| Duplicate nodes per entity | 2+ (type mismatch) | 1 per entity | Graph integrity |
| Edge type consistency | 5 types for same relationship | 1 stable type | Relationship semantics |
| Librarian graph awareness | None (flat name list) | Retrieves relevant subgraphs | Informed decisions |
| Librarian mutation capability | None (produces static payload) | Creates/updates/archives via tools | Active curation |
| Context scalability | Breaks at 50K nodes | Bounded (tool-based retrieval) | Large graph support |
| Edge weight after 20 recalls | 1.75+ | ≤1.3 | Scoring fairness |
| Plan 15 scenarios acceptable | 5/14 (35%) | ≥11/14 (79%) | Overall quality gate |

---

## Files That May Be Changed

### Extraction pipeline (core changes)
- `src/neocortex/extraction/agents.py` — librarian agent: new deps, tools, prompt
- `src/neocortex/extraction/schemas.py` — new output models (CurationSummary)
- `src/neocortex/extraction/pipeline.py` — rewire pipeline, remove `_persist_payload`

### Database layer
- `src/neocortex/db/adapter.py` — content update fix, node/edge dedup safety nets, new query methods
- `src/neocortex/db/mock.py` — mirror changes
- `src/neocortex/db/protocol.py` — new methods for librarian tools
- `src/neocortex/graph_service.py` — content update fix

### Scoring & recall
- `src/neocortex/scoring.py` — spreading activation weight handling
- `src/neocortex/tools/recall.py` — decay parameters
- `src/neocortex/mcp_settings.py` — settings defaults

### Tests
- `tests/` — new tests for each stage

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [Fix Node Content Updates](stages/01-content-updates.md) | PENDING | P0: COALESCE SQL fix + prompt | |
| 2 | [Librarian Retrieval Tools](stages/02-librarian-retrieval.md) | PENDING | P0: Read-only graph query tools via @agent.tool | |
| 3 | [Librarian Mutation Tools & Pipeline Redesign](stages/03-librarian-mutation.md) | PENDING | P0: Write tools + replace _persist_payload | |
| 4 | [Adapter Safety Nets](stages/04-adapter-safety.md) | PENDING | P1: Defense-in-depth dedup at DB layer | |
| 5 | [Fix Edge Weight Management](stages/05-weight-management.md) | PENDING | P2: Bounded reinforcement + continuous decay | |

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

**Parallelism**: Stages 1 and 5 are independent of the core pipeline work.
Stages 2 and 3 are sequential (read tools before write tools).
Stage 4 can run after Stage 3.

**If a stage cannot be completed**: mark it BLOCKED in the tracker with a note
explaining why, and stop. Do not proceed to subsequent stages.

**If assumptions are wrong**: stop, document the issue in the Issues section below,
revise affected stages, and get user confirmation before continuing.

---

## Issues

1. **Pre-existing: Unbounded context to librarian** — `list_all_node_names()` at `pipeline.py:124` passes ALL node names with no LIMIT. Breaks at ~50K nodes. Stage 2 replaces this with bounded tool-based retrieval.

---

## Decisions

1. **Tool-driven persistence over static payloads** — The librarian executes graph mutations via PydanticAI `@agent.tool` decorators rather than producing a payload for blind persistence. This gives the LLM full agency to curate the graph intelligently.

2. **Per-episode curation over batch consolidation** — Curation happens at extraction time (every episode) rather than as a separate scheduled batch process. Gives immediate consistency without additional infrastructure. Batch consolidation can be added later as a complement.

3. **Defense in depth** — Stage 4 adds adapter-level dedup safety nets even though the tool-equipped librarian should handle dedup. LLMs make mistakes; the database layer should catch what the agent misses.

4. **Retrieval tools replace context injection** — Instead of pre-loading all node names into the prompt (unbounded, breaks at scale), the librarian uses `@agent.tool` to search the graph on demand. Only relevant subgraphs enter the context.
