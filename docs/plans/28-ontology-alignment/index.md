# Plan 28: Ontology Alignment

| Field          | Value                                                   |
| -------------- | ------------------------------------------------------- |
| Date           | 2026-04-03                                              |
| Branch         | `ontology-alignment`                                    |
| Predecessors   | Plan 07 (extraction pipeline), Plan 11 (upper ontology), Plan 17 (entity normalization), Plan 25 (extraction performance) |
| Goal           | Fix ontology quality: eliminate hallucinated types, reduce type proliferation, and make the extraction pipeline produce semantically meaningful graphs from heterogeneous personal knowledge |

---

## Context

### Problem Statement

After bulk-ingesting ~134 Obsidian vault documents (weekly notes, health protocols,
car knowledge, personal notes, work context) into NeoCortex, the extracted knowledge
graph has **correct entity content** but a **broken semantic layer**. The ontology
agent (Gemini 3 Flash, low thinking) produces types and relations that are
syntactically valid but semantically nonsensical.

### Observed Symptoms (anonymized samples)

**1. Tool-call artifact leakage** (CRITICAL)
Types like `ActivityfunctiondefaultApicreateOrUpdateNodecontent`,
`MentalstatecalldefaultApicreateOrUpdateEdgeedgeType` -- the LLM's internal
function-call syntax bleeds through as node/edge type names. These pass format
validation (PascalCase) but are garbage.

**2. Instance-level types** (HIGH)
Types that describe specific instances, not reusable categories:
- `DishGreg` (should be `Dish`), `AssetSnowboardguards` (should be `Asset`)
- `DreamAiPresentation`, `LocationSalCapeVerde`, `DeviceMacMiniServer`
- `InsightEngineKnock`, `InsightSubstanceOverstimulation`

**3. Redundant/overlapping types** (MEDIUM)
- `AnatomicalLocation` / `AnatomicalStructure` / `BodyPart` (should be one type)
- `HealthState` / `Symptom` / `Condition` (overlapping semantics)
- `Architecture` / `ArchitectureConcept` / `ArchitecturePattern` / `TechnicalArchitecture`
- `Activity` / `HealthActivity` / `SportActivity`

**4. Semantically inappropriate types for personal knowledge** (HIGH)
Edge types like `AVOIDS`, `BENCHMARKED_BY`, `CONCEALS`, `BYPASSES_COMPONENT`,
`ASSUMES_CONTROL_DURING`, `MEASURED_IN_SAMPLE` used for personal life facts.
Node types like `Bot` for a supplement, `Account` for a person.

**5. Massive type proliferation with low utilization**
- Personal graph: 1116 nodes across 100+ node types (many with count=1)
- `user_profile`: 535 nodes, ~80 node types, ~200 edge types (most with 0 edges)
- `domain_knowledge`: 707 nodes, ~100 node types, ~150 edge types
- The majority of edge types have **zero** edges -- proposed but never used

### Root Cause Analysis

| # | Root Cause                           | Severity | Evidence |
|---|--------------------------------------|----------|----------|
| 1 | **No semantic validation of types**  | Critical | Only format (PascalCase/SCREAMING_SNAKE) and length are checked. `BusinessActivityCode`, `BYPASSES_COMPONENT` pass validation for personal notes. |
| 2 | **Tool-call reasoning leakage**      | Critical | Gemini Flash with low thinking emits internal function-call fragments that pass the 5-word/60-char filter. |
| 3 | **Sparse seed ontology**             | High     | 6 node types + 12 edge types is too few. First documents create a chaotic ontology that compounds. |
| 4 | **Weak domain hints**                | High     | "Domain Knowledge: General facts, concepts, trends" provides zero type-level constraint. No per-domain type guidance. |
| 5 | **Gemini Flash + low thinking**      | Medium   | Ontology design requires semantic judgment. Flash with low effort produces creative but wrong type names. |
| 6 | **No type consolidation**            | Medium   | `cleanup_empty_types` only deletes types with 0 nodes after 5 min. Redundant types with 1-2 nodes persist forever. |
| 7 | **Instance names leaking into types**| Medium   | Ontology agent sometimes concatenates an entity name with its type (e.g., `Dish` + `Greg` -> `DishGreg`). |

### Quantitative Baselines

| Metric                        | Current Value | Target |
|-------------------------------|---------------|--------|
| Node types per graph (avg)    | ~90           | 25-35  |
| Edge types per graph (avg)    | ~140          | 30-50  |
| Edge types with 0 usage (%)   | ~70%          | <15%   |
| Garbage types (tool artifacts)| ~8 across all | 0      |
| Instance-level types          | ~30 across all| 0      |
| Type reuse ratio (nodes/types)| ~7:1          | 20:1+  |

---

## Strategy

**Approach: Layered defense -- validate harder, seed better, prompt smarter, model stronger.**

The fix targets three layers of the extraction pipeline, ordered by impact and
implementation simplicity:

**Phase A (Stages 1-2): Foundation** -- Fix validation gaps and seed a meaningful ontology
- Stage 1: Harden type name validation to catch garbage (tool artifacts, instance-level names)
- Stage 2: Replace the 6-type seed with domain-specific ontology templates (25-35 types per domain)

**Phase B (Stages 3-4): Intelligence** -- Make the ontology agent smarter
- Stage 3: Overhaul ontology agent prompts with domain-specific guidance, negative examples, type budget
- Stage 4: Use a stronger model for the ontology agent (Sonnet or configurable)

**Phase C (Stages 5-6): Cleanup** -- Consolidate existing damage and prevent recurrence
- Stage 5: Add a post-extraction type consolidation pass (merge near-duplicates, archive unused)
- Stage 6: Add a migration/script to clean up the current graph's broken types

### Trade-offs

**Why not a fixed vocabulary?** Too restrictive -- personal knowledge is diverse. We need
guided creativity, not a straitjacket. The seed ontology + validation layer provides
enough guardrails while allowing organic growth.

**Why not an agentic reviewer?** Cost/latency. Adding a 4th agent doubles extraction
time. Instead, we use heuristic validation (cheap, fast) for the common cases and
improve prompts for the nuanced cases. Can add later if insufficient.

**Why upgrade the model only for ontology?** Ontology design is the bottleneck --
it requires semantic judgment that Flash with low thinking handles poorly. Extraction
and curation work fine with Flash since they operate within the ontology's constraints.

---

## Success Criteria

| Metric | Baseline | Target | Rationale |
|--------|----------|--------|-----------|
| Node types per graph (avg) | ~90 | 25-35 | A personal knowledge graph should be expressible in <35 types |
| Edge types per graph (avg) | ~140 | 30-50 | Most relations cluster into 30-40 meaningful patterns |
| Edge types with 0 usage (%) | ~70% | <15% | Proposed-but-unused types indicate hallucination |
| Garbage types (tool artifacts) | ~8 | 0 | Zero tolerance for leaked function call syntax |
| Instance-level types | ~30 | 0 | Every type must be reusable across entities |
| Type reuse ratio (nodes/types) | ~7:1 | 20:1+ | Higher reuse = more consistent ontology |

---

## Files That May Be Changed

### Validation (Stage 1)
- `src/neocortex/normalization.py` -- Enhanced type name validation heuristics
- `tests/test_normalization.py` -- New test cases for garbage detection

### Seed Ontology (Stage 2)
- `migrations/graph/003_seed_ontology.sql` -- Expanded base seed
- `src/neocortex/domains/models.py` -- Per-domain type templates (added to SEED_DOMAINS)

### Prompts (Stage 3)
- `src/neocortex/extraction/agents.py` -- Ontology agent prompt overhaul

### Model Config (Stage 4)
- `src/neocortex/mcp_settings.py` -- Separate ontology model setting
- `src/neocortex/extraction/pipeline.py` -- Model routing for ontology agent

### Consolidation (Stage 5)
- `src/neocortex/extraction/type_consolidation.py` -- New: type merge/archive logic
- `src/neocortex/extraction/pipeline.py` -- Hook consolidation after extraction

### Cleanup (Stage 6)
- `scripts/cleanup_ontology.py` -- One-shot migration for existing graphs

---

## Progress Tracker

| # | Stage | Status | Notes | Commit |
|---|-------|--------|-------|--------|
| 1 | [Type Validation Hardening](stages/01-.md) | PENDING | | |
| 2 | [Domain-Specific Seed Ontologies](stages/02-.md) | PENDING | | |
| 3 | [Ontology Agent Prompt Overhaul](stages/03-.md) | PENDING | | |
| 4 | [Model Upgrade for Ontology Agent](stages/04-.md) | PENDING | | |
| 5 | [Post-Extraction Type Consolidation](stages/05-.md) | PENDING | | |
| 6 | [Graph Cleanup Migration](stages/06-.md) | PENDING | | |

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

*(To be filled during execution)*

---

## Decisions

- **D1**: No fixed vocabulary -- use seed ontology + validation + better prompts to allow organic growth with guardrails.
- **D2**: Model upgrade only for ontology agent -- extraction and curation work fine with Flash.
- **D3**: Cleanup as last stage -- fix the pipeline first, then repair existing damage.
