# NeoCortex E2E Memory Test Report

**Date**: 2026-03-30
**Scenario**: Multi-month work simulation on datawalk-entity-resolution project
**Agent**: alice (anonymous auth)
**Duration**: ~25 minutes (store + extraction + recall)

---

## Test Design

Simulated 3 months of daily work on the DataWalk Entity Resolution project:
- **Phase 1 (Jan 2026)**: 8 onboarding memories — project intro, team, domain concepts, architecture
- **Phase 2 (Feb 2026)**: 9 active development memories — blocking implementation, debugging, security bugs, performance profiling, chaos testing
- **Phase 3 (Mar 2026)**: 8 scaling/optimization memories — Metaphone3 switch, WNP optimization, batched normalization, encoding optimization, demo prep
- **Phase 4 (Evolution)**: 3 correction/update memories — decision reversal, team change, new discovery

**Total**: 28 episodes stored with varying importance (0.5-0.9)

---

## Storage Results

| Metric | Value |
|--------|-------|
| Episodes stored | 28 |
| Episodes consolidated (extracted) | 19/28 (68%) after ~15 min |
| Nodes created | 121 |
| Edges created | 45 |
| Node types | 42 (6 empty) |
| Edge types | 38 |
| Avg activation | 0.24 |

**Verdict**: Storage pipeline works reliably. All 28 episodes persisted immediately. Extraction pipeline processes episodes at ~1.3/minute (3-agent LLM pipeline).

---

## Finding 1: Domain Routing Completely Non-Functional

**Severity**: HIGH

All 28 episodes routed with `domain_count: 0`. The Gemini domain classifier returned empty `matched_domains` for every episode despite content containing obvious keywords matching seed domains:
- "architecture", "database", "Python", "API" -> should match `technical_knowledge`
- "project", "team", "sprint", "meeting" -> should match `work_context`
- "entity resolution", "blocking", "Fellegi-Sunter" -> should match `domain_knowledge`

**Result**: Zero shared domain graphs created. All knowledge stays in personal graph only. Multi-agent knowledge sharing is effectively disabled.

**Evidence**: `agent_actions.log` shows `"routed_to": [], "domain_count": 0` for all episodes.

**Root cause hypothesis**: The `AgentDomainClassifier` prompt may be too conservative ("strongly prefer existing domains") combined with the Gemini model not recognizing domain relevance at the confidence threshold (0.3). The seed domain descriptions may not be specific enough to trigger matches.

---

## Finding 2: Episode #24 "Gravity Well" Effect

**Severity**: MEDIUM

Episode #24 (Fellegi-Sunter gap analysis, importance=0.8) appeared as the #1 result in **8 out of 9 recall queries**, including completely unrelated queries like "SQL injection vulnerability" and "What bugs were found?".

**Root cause**: The ACT-R activation mechanism creates a positive feedback loop:
1. High importance (0.8) gives initial boost
2. Each recall query that returns it increments `access_count`
3. Higher activation -> higher score -> returned more often -> activation grows further

After 9 recall queries, Episode #24's activation_score climbed from 0.49 to 0.91 — nearly double.

**Impact**: Diverse recall is suppressed. Less-accessed but more relevant content (debugging sessions, security bugs) gets pushed down.

**Recommendation**: Consider activation dampening per-query or a diversity-aware reranking step.

---

## Finding 3: Specific Bug/Event Episodes Hard to Recall

**Severity**: MEDIUM

Several specific episodic memories were never surfaced in relevant queries:

| Episode | Content | Query That Should Find It | Found? |
|---------|---------|--------------------------|--------|
| #10 | SQL injection in IdentifierLinkNormalizationService | "SQL injection vulnerability" | NO |
| #15 | Fingerprint 32->64 bit collision fix (birthday paradox) | "fingerprint collision birthday paradox" | NO |
| #16 | Korean character UDX crashes | "bugs found during debugging" | NO |
| #26 | Metaphone3 hybrid decision (CORRECTION) | "current Metaphone3 strategy" | NO |

These episodes contain highly specific technical details that should be retrievable by targeted queries. The combination of:
- Low importance (0.6-0.7)
- Zero activation (never recalled before)
- Competition with high-activation general episodes
...makes them effectively invisible.

---

## Finding 4: Node Type Corruption

**Severity**: MEDIUM

The extraction pipeline produced a corrupted node type: `Constraint}OceanScience` (node: "Zero data movement"). This appears to be malformed JSON from the LLM output that wasn't caught by the normalization layer.

"OceanScience" has zero relevance to the entity resolution domain — it's pure hallucination.

**Additional type inconsistencies observed**:
- `Vulnerability` type with 0 nodes (created but never populated)
- `BacklogItem` type with 0 nodes
- `SystemLayer` type with 0 nodes

---

## Finding 5: Cross-Extraction Deduplication Weakness

**Severity**: MEDIUM

Same real-world entities typed differently across extraction runs:

| Entity Name | Types Assigned | Notes |
|-------------|---------------|-------|
| "252 Million Entities" | Concept, Dataset, Metric | 3 different types for same thing |
| "Blocking" | Methodology, ProcessStage | Same concept, different classification |
| "Metaphone3" | Methodology, Tool | Same technology, inconsistent typing |
| "Vertica 24.x" | DataStore, Tool | Same technology |

The dedup key is `(name, type_id)` which is correct by design (prevents false merges of homonyms like "Serotonin" as Neurotransmitter vs Drug). But the ontology agent assigns inconsistent types to the same entity across episodes, bypassing dedup and creating semantic duplicates.

**Impact**: Graph fragmentation — the same entity appears as multiple disconnected nodes, splitting its edge relationships.

---

## Finding 6: No Temporal Awareness for Evolving Facts

**Severity**: HIGH

The system has no mechanism to handle fact evolution over time. When tested with:
1. Feb 28: "4-char Metaphone3 creates too many pairs" (concern raised)
2. Mar 5: "Switching to 8-char Metaphone3" (decision made)
3. Mar 30: "CORRECTION — hybrid approach: 8-char for Latin, 4-char for non-Latin" (decision reversed)

Recall for "current Metaphone3 strategy" returned the **original February nodes** about 4-char codes, not the March 30 correction. The correction episode had:
- Zero activation (just stored, never previously recalled)
- Competing with well-established nodes that have been recalled multiple times

There's no temporal ordering, supersession mechanism, or "latest version" concept. An agent relying on this memory would get **stale/wrong information**.

The ontology has `REVERSES_DECISION` and `DEFERRED_TO` edge types (created but 0 edges) — the extraction pipeline creates the *types* for temporal relationships but doesn't populate them.

---

## Finding 7: Edge Reinforcement Working Correctly

**Severity**: POSITIVE

Hebbian edge reinforcement is functioning as designed:
- Edges traversed during recall gain weight (observed weights increasing from 1.0 to 1.12+)
- Spreading activation bonus provides meaningful graph context in results
- Graph neighborhoods are returned with each node result

The cognitive heuristics (ACT-R base-level + spreading activation + Hebbian reinforcement) produce coherent behavior for **well-connected, frequently-accessed knowledge**. The issue is with infrequently-accessed or recently-added knowledge.

---

## Finding 8: Episode vs Node Recall Balance

**Severity**: LOW

Of the 9 recall queries:
- Queries about specific events/dates -> episodes ranked higher (correct)
- Queries about concepts/architecture -> nodes ranked higher (correct)
- The hybrid scoring appropriately blends both sources

However, when an episode hasn't been consolidated into nodes yet, it can only be found via embedding similarity and ILIKE text match — no graph traversal bonus. This creates a gap for recently stored memories.

---

## Recall Quality Summary

| Recall Pattern | Queries | Pass Rate | Notes |
|---------------|---------|-----------|-------|
| Domain concepts (blocking, architecture) | 2 | **100%** | Graph nodes + spreading activation excellent |
| Specific events (debugging sessions, bugs) | 3 | **0%** | Specific events invisible behind dominant episodes |
| People queries | 2 | **75%** | Team info found but sometimes outranked by noise |
| Temporal evolution (decision reversals) | 3 | **33%** | Latest corrections not surfaced; old facts dominate |
| Cross-domain (security + normalization) | 1 | **0%** | Too specific, drowned by generic high-activation results |

---

## Recommendations

### Critical
1. **Fix domain classifier**: Either lower the confidence threshold, improve seed domain descriptions, or add fallback keyword matching (the MockDomainClassifier works but the AgentDomainClassifier does not)
2. **Add temporal recency bias**: New episodes should get a short-lived boost to ensure corrections/updates surface in the first few queries
3. **Implement fact supersession**: When an episode contains "CORRECTION", "UPDATE", "REVERSAL" signals, create `REVERSES_DECISION` edges and boost the newer episode in scoring

### Important
4. **Activation dampening**: Cap per-query activation increment or add diversity reranking to prevent gravity wells
5. **Type consistency**: The ontology agent should receive a list of existing types (not just names) with descriptions, forcing it to reuse them rather than inventing near-duplicates
6. **Type name validation**: Reject type names containing `}`, `{`, or other JSON-invalid characters in the normalization layer

### Nice-to-Have
7. **Lazy merge of semantic duplicates**: Periodically scan for nodes with same name but different types, propose merges when types are semantically equivalent
8. **Episode consolidation priority**: Prioritize extraction of high-importance episodes to ensure critical memories are graph-connected faster
