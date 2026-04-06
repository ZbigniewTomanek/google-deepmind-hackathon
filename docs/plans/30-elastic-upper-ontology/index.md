# Plan 30: Elastic Upper Ontology

| Field          | Value                                                   |
| -------------- | ------------------------------------------------------- |
| Date           | 2026-04-06                                              |
| Branch         | `elastic-upper-ontology`                                |
| Predecessors   | Plan 11 (upper ontology routing), Plan 17 (entity normalization), Plan 28 (ontology alignment), Plan 29 (ontology validation) |
| Goal           | Make the upper ontology (semantic domain layer) elastic: new domains and sub-domains emerge organically from incoming knowledge, following OWL/upper-ontology methodology, instead of staying rigidly locked to 4 hardcoded seed domains |

---

## Context

### Problem Statement

After Plans 28/29, the **per-domain type ontology** is healthy — the extraction
pipeline produces clean, validated, deduplicated types. But the **upper ontology**
(the domain layer that routes knowledge to shared graphs) is frozen. The system
has exactly 4 seed domains (`user_profile`, `technical_knowledge`, `work_context`,
`domain_knowledge`) and never creates new ones, even when novel content arrives.

Content about cinema, literature, music, history, or philosophy all gets dumped
into `domain_knowledge` — a catch-all bucket that prevents domain specialization.

### Root Cause Analysis

| # | Root Cause | Severity | Evidence |
|---|-----------|----------|----------|
| 1 | **Classifier prompt is too conservative** | Critical | Says "CONSERVATIVE: strongly prefer existing domains" and provides no examples of how to output a ProposedDomain. The LLM almost never fills the optional field. |
| 2 | **`domain_knowledge` is a catch-all sink** | Critical | Keyword fallback defaults to `domain_knowledge`. Any unclassified content goes here instead of triggering domain creation. |
| 3 | **No domain hierarchy** | High | Flat list of 4 domains. No sub-domains, no parent-child relationships. OWL's `rdfs:subClassOf` has no equivalent. Novel content that is adjacent to an existing domain (e.g., "sports" near "user_profile") has no way to specialize. |
| 4 | **New domains get zero guidance** | High | `DOMAIN_SEEDS` is hardcoded for 4 domains. A newly provisioned domain starts with an empty type vocabulary — the ontology agent has no recommendations. |
| 5 | **No taxonomy maintenance process** | Medium | No mechanism to review domain utilization, split overstuffed domains, merge sparse ones, or refine domain descriptions. The taxonomy is write-once. |
| 6 | **No cross-domain type alignment** | Low | Same concept (e.g., `Person`, `Location`) exists independently in every domain schema. No shared upper types or equivalence tracking. |

### OWL / Upper Ontology Methodology

This plan borrows from established upper ontology practice (SUMO, DOLCE, BFO):

- **Taxonomic hierarchy**: Domains form a tree via `is_subdomain_of`. Top-level
  domains are broad categories; sub-domains specialize. E.g., `arts_and_culture`
  → `cinema`, `literature`, `music`.
- **Open-world assumption**: The taxonomy is never "complete" — new domains can
  always be proposed when knowledge doesn't fit existing structure.
- **Subsumption-based routing**: Content is classified at the most specific
  applicable level. A sub-domain inherits its parent's context.
- **Separate maintenance**: Taxonomy evolution is a distinct concern from
  per-episode extraction. A steward process reviews and restructures periodically.

---

## Strategy

**Approach: Hierarchical domains + adaptive classifier + taxonomy steward.**

### Phase A: Baseline (Stages 1–2)
Establish quantitative baselines using a diverse test corpus on a fresh
installation. Measure: domain routing distribution, catch-all absorption rate,
novel-domain creation rate (expected: 0%), type growth patterns.

### Phase B: Implementation (Stages 3–6)
1. Add hierarchical domain schema (parent_id, depth, path)
2. Overhaul the classifier to propose sub-domains and show the domain tree
3. Auto-generate seed ontologies for newly created domains
4. Build a taxonomy steward CLI for periodic domain health review

### Phase C: Validation (Stage 7)
Re-run the identical corpus from Phase A against the improved system. Compare
metrics head-to-head.

---

## Success Criteria

| Metric | Baseline (expected) | Target |
|--------|---------------------|--------|
| Novel-domain creation rate | 0% (all novel content → domain_knowledge) | ≥50% of novel-domain texts trigger new domain/sub-domain creation |
| Catch-all absorption rate | 100% of unmatched content → domain_knowledge | <30% — most content finds a specific domain |
| Domain count after corpus | 4 (unchanged) | 6–10 (organic growth) |
| Hierarchy depth | 1 (flat) | 2–3 levels |
| New domain seed quality | N/A (no new domains) | New domains get ≥5 recommended node types + ≥5 edge types |
| Taxonomy steward coverage | N/A | Steward can report health metrics for all domains |

---

## Files That May Be Changed

### New Files
- `migrations/public/012_domain_hierarchy.sql` — parent_id, depth, path columns
- `src/neocortex/domains/seed_generator.py` — dynamic seed generation for new domains
- `src/neocortex/domains/steward.py` — taxonomy health review and restructuring
- `scripts/taxonomy_steward.sh` — CLI wrapper for steward process

### Modified Files
- `src/neocortex/domains/models.py` — SemanticDomain gains parent_id, depth, path, children
- `src/neocortex/domains/protocol.py` — new methods: get_domain_tree, get_domain_children, move_domain
- `src/neocortex/domains/pg_service.py` — hierarchy-aware queries
- `src/neocortex/domains/memory_service.py` — in-memory hierarchy support
- `src/neocortex/domains/classifier.py` — rewritten prompt with tree display + proposal examples
- `src/neocortex/domains/router.py` — hierarchy-aware provisioning, parent context inheritance
- `src/neocortex/domains/ontology_seeds.py` — lookup by slug chain, fallback to parent seeds
- `src/neocortex/extraction/pipeline.py` — pass parent seed context for new domains
- `tests/test_domain_classifier.py` — updated for hierarchical proposals
- `tests/test_domain_router.py` — updated for sub-domain provisioning

---

## Progress Tracker

| # | Stage | Status | Commit | Notes |
|---|-------|--------|--------|-------|
| 1 | [Test Corpus & Diagnostic Queries](stages/01-.md) | DONE | 4a2d236 | Resources created |
| 2 | [Baseline Experiment](stages/02-.md) | PENDING | — | Run corpus, capture metrics |
| 3 | [Domain Hierarchy Schema](stages/03-.md) | PENDING | — | DB migration + model changes |
| 4 | [Hierarchical Domain Classifier](stages/04-.md) | PENDING | — | Prompt rewrite + tree display |
| 5 | [Dynamic Seed Generation](stages/05-.md) | PENDING | — | Auto-seed new domains |
| 6 | [Taxonomy Steward CLI](stages/06-.md) | PENDING | — | Health metrics + restructuring |
| 7 | [Re-validation](stages/07-.md) | PENDING | — | Compare against baseline |

---

## Execution Protocol

You are an autonomous agent executing this plan stage by stage.

**Before each stage**: Read the stage file. Check dependencies (previous stages
marked DONE). Read all files listed in the stage's "Files" section before making
changes.

**During each stage**: Follow steps in order. Run verification commands. If a
step fails, diagnose and fix before proceeding. Log any issues in the Issues
section below.

**After each stage**: Run the verification checklist. Create a single commit
with the message from the stage file. Update this index (mark stage DONE, add
commit hash). Move to the next stage.

**If blocked**: Log the blocker in Issues. Skip to the next unblocked stage if
possible. Do not proceed past a blocking dependency.

---

## Issues

| # | Stage | Severity | Description | Resolution |
|---|-------|----------|-------------|------------|

---

## Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Hierarchical domains (not flat tags) | OWL methodology — subsumption gives routing precision and inheritance. Tags would require ad-hoc overlap resolution. |
| D2 | Separate steward process (not inline) | Taxonomy maintenance is a different concern than per-episode extraction. Inline decisions during classification would add latency and token cost to every ingestion. |
| D3 | Parent seed inheritance | New sub-domains inherit their parent's seed ontology as a starting point, then specialize. Avoids cold-start with empty vocabulary. |
| D4 | LLM-assisted seed generation | Static seed dictionaries don't scale. Use a cheap LLM call to generate domain-appropriate type recommendations from the domain description + parent context. |
