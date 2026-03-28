# Report 01 — Full E2E Knowledge Engine Validation

> **Date:** 2026-03-28  |  **Agent:** alice  |  **Status:** PASS (with issues)
> **Plan:** [12-manual-e2e-test](../plans/12-manual-e2e-test.md)

## What Was Tested

Full pipeline: multi-format ingestion (audio, video, document, text) → extraction → domain routing → shared graphs → recall with cognitive scoring → ontology evolution. 12 content items ingested from 3 sources (media fixtures, ER pipeline docs, Obsidian daily notes).

**Final state:** 742 nodes, 544 edges, 43 episodes, 150 node types, 188 edge types, 5 graphs.

---

## Issues Requiring Redesign

### 1. Seed domain schemas not provisioned

**Severity:** High — domain routing silently drops all classified content.

Seed migration writes 4 rows to `ontology_domains` with `schema_name` values (`ncx_shared__user_profile`, etc.) but never creates the corresponding PG schemas in `graph_registry`. No permissions are granted either. The `_ensure_schema` code path that auto-creates schemas is bypassed because `domain.schema_name` is already set (from the seed), so it returns early without checking if the schema actually exists.

Domain routing completes with `routed_to=[]` and logs success — no error, no warning.

### 2. Ontology contamination in shared graphs

**Severity:** Medium — extraction quality degrades as graphs grow.

When mixed-domain content is extracted into the same shared schema, the ontology agent reuses existing types from unrelated domains:

| Entity | Expected Type | Actual Type | Schema |
|--------|--------------|-------------|--------|
| Creatine | Supplement | ProbabilisticModel / AlgorithmLogic | personal / user_profile |
| Gabapentin | ChemicalSubstance | Batch | technical_knowledge |
| Serotonin | Neurotransmitter | DatabaseSystem | technical_knowledge |
| Tomasz Rozgalka | Person | Action | personal |
| SSRIs | DrugClass | TextEncoding / Vehicle | technical_knowledge |

Root cause: the ontology agent is given the existing type list and force-fits new entities. No domain context is passed to the extraction prompt.

### 3. Discover tool returns too much data

**Severity:** Medium — wastes agent context window, prevents iterative exploration.

A single `discover()` call returned ~4000 tokens: 150 node types + 188 edge types, each with full descriptions. The response is a flat dump with no per-graph breakdown. An LLM agent cannot:
- See which types belong to which graph
- Get a compact overview first, then drill down
- Understand the graph topology without reading hundreds of lines

Needed: compact overview (names + counts only, skip empty types, per-graph stats), with optional drill-down.

### 4. Edge extraction references missing nodes

**Severity:** Low — individual edges silently dropped.

3 `edge_skipped_missing_node` warnings during video extraction. The extraction LLM proposes edges to nodes it mentions in reasoning but doesn't include in the node list.

### 5. Content-type detection for media uploads

**Severity:** Low — UX friction, not a bug.

`curl -F "file=@path"` sends `application/octet-stream`. The 415 error message lists accepted types but doesn't suggest the fix (`type=audio/mpeg` in the form field). Easy to add.

---

## Observations Worth Preserving

- **Cross-source recall works**: daily notes mentioning WNP co-activate with ER pipeline docs about blocking. Spreading activation reinforced WNP node from 0.47→0.66 across multiple recalls.
- **Domain routing is additive and functional** (once schemas exist): content correctly classified to user_profile, technical_knowledge, work_context, domain_knowledge.
- **Extraction throughput**: ~15-20s per episode + ~2s for domain classification. Domain routing can multiply jobs (1 episode → 3-4 extraction jobs). 12 items took ~10 min total.
- **Hebbian edge weights accumulate fast**: observed up to 2.0 ceiling. Lazy decay (10% probability) may be insufficient for frequently accessed subgraphs.
