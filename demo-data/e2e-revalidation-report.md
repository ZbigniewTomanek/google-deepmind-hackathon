# NeoCortex E2E Re-Validation Report

**Date**: 2026-03-31
**Predecessor**: Plan 18 (Recall Quality Overhaul) -- 7 stages implemented
**Scenario**: 28-episode DataWalk ER project simulation (same scenario as original E2E)
**Agent**: alice (dev_token auth)
**Overall Verdict**: FAIL (3/6 hard metrics met)

---

## Summary Table

| # | Metric | Baseline | Target | Measured | Verdict |
|---|--------|----------|--------|----------|---------|
| M1 | Max activation (9 queries) | 0.91 | <= 0.70 | 0.666 | PASS |
| M2 | Single-episode dominance | 8/9 (89%) | <= 3/9 (33%) | 1/9 (11%) | PASS |
| M3 | Specific event recall | 0% (0/3) | >= 66% (2/3) | 67% (2/3) | PASS |
| M4 | Temporal evolution recall | 33% (1/3) | >= 66% (2/3) | 0% (0/3) | FAIL |
| M5 | Domain routing | 0% (0/28) | >= 75% (21/28) | 0% (0/28) | FAIL |
| M6 | Corrupted type names | 1+ | 0 | 4 | FAIL |
| M7 | Type consistency | Multiple dupes | Improved | ~5 dupes (SAME) | -- |

---

## Graph Statistics

| Metric | Original E2E | Re-Validation |
|--------|-------------|---------------|
| Episodes stored | 28 | 28 (+1 smoke test) |
| Episodes consolidated | 19/28 (68%) | 27/29 (93%) |
| Nodes created | 121 | 206 |
| Edges created | 45 | 33 |
| Node types (total / empty) | 42 / 6 | 38 / 0 |
| Edge types (total) | 38 | 60 |
| Edge types (with instances) | -- | 15 |
| SUPERSEDES edges | 0 | 1 |
| CORRECTS edges | 0 | 0 |
| Avg activation | 0.24 | 0.0 (cold start) |

---

## Detailed Query Results

### Q1: Blocking Concept
Query: `"What is blocking in entity resolution and how does the system implement it?"`

| Rank | Name | Score | Type | Source |
|------|------|-------|------|--------|
| 1 | Blocking Stage | 0.808 | Operation | node |
| 2 | Union Blocking | 0.799 | Algorithm | node |
| 3 | Blocking | 0.751 | Operation | node |
| 4 | Blocking | 0.713 | Methodology | node |
| 5 | Current Implementation | 0.698 | SoftwareSystem | node |

**Verdict**: PASS -- blocking-related content in top 3.

### Q2: Architecture
Query: `"Describe the overall system architecture and Vertica design patterns"`

| Rank | Name | Score | Type | Source |
|------|------|-------|------|--------|
| 1 | DataWalk Entity Resolution | 0.683 | SoftwareSystem | node |
| 2 | ROS Container | 0.682 | DataStructure | node |
| 3 | Hybrid Architecture | 0.623 | Architecture | node |
| 4 | SQL | 0.606 | SoftwareSystem | node |
| 5 | MPP database | 0.592 | Architecture | node |

**Verdict**: PASS -- architecture content in top 3.

### Q3: SQL Injection (Specific Event)
Query: `"SQL injection vulnerability in normalization service"`

| Rank | Name | Score | Type | Source |
|------|------|-------|------|--------|
| 1 | Fingerprint computation queries | 0.628 | Query | node |
| 2 | ParsePhoneNumber | 0.608 | Algorithm | node |
| 3 | Normalization Pipeline | 0.598 | Architecture | node |
| 4 | Queries | 0.598 | Query | node |
| 5 | ParseHumanName UDX | 0.538 | SoftwareSystem | node |

**Verdict**: FAIL -- no SQL injection content in top 10. Episode 10 content completely absent.

### Q4: Fingerprint Collision (Specific Event)
Query: `"fingerprint hash collision birthday paradox 32-bit to 64-bit"`

| Rank | Name | Score | Type | Source |
|------|------|-------|------|--------|
| 1 | 64-bit HASH | 0.848 | Algorithm | node |
| 2 | 32-Bit Hash Collision Bug | 0.789 | Bug | node |
| 3 | Probabilistic Analysis | 0.745 | Methodology | node |
| 4 | Composite Fingerprinting | 0.745 | Methodology | node |
| 5 | Exact Duplicate Deduplication | 0.735 | Methodology | node |

**Verdict**: PASS -- fingerprint collision content dominates top 5.

### Q5: Korean Character Bug (Specific Event)
Query: `"Korean character crash UDX bug in name parsing"`

| Rank | Name | Score | Type | Source |
|------|------|-------|------|--------|
| 1 | ParseHumanName UDX Crash Bug | 0.749 | Bug | node |
| 2 | Pre-processing step | 0.687 | Operation | node |
| 3 | ParseHumanName UDX | 0.650 | SoftwareSystem | node |
| 4 | Vertica-Functions-Datawalk-Library.Jar | 0.625 | SoftwareSystem | node |
| 5 | Phonetic_Family_Name | 0.620 | Feature | node |

**Verdict**: PASS -- Korean bug content dominates all 10 results.

### Q6: Team Composition
Query: `"Who is on the DataWalk ER team and what are their roles?"`

| Rank | Name | Score | Type | Source |
|------|------|-------|------|--------|
| 1 | Poetry | 0.740 | SoftwareSystem | node |
| 2 | DataWalk ER team | 0.716 | Organization | node |
| 3 | Sarah Kim | 0.623 | Person | node |
| 4 | Backend Engineer | 0.620 | Role | node |
| 5 | Tomek Zbigniew | 0.617 | Person | node |

**Verdict**: PASS -- team and person content in top 5. (Note: Poetry at #1 is unexpected.)

### Q7: Jonas Role (Temporal)
Query: `"What is Jonas Weber's current role and team assignment?"`

| Rank | Name | Score | Type | Source |
|------|------|-------|------|--------|
| 1 | Episode #3 (original team) | 0.797 | Episode | episode |
| 2 | Backend Engineer | 0.600 | Role | node |
| 3 | DataWalk ER team | 0.589 | Organization | node |
| 6 | Episode #28 (security transfer) | 0.322 | Episode | episode |

**Verdict**: FAIL -- Episode #28 (current: security team) ranks far below Episode #3 (old: backend engineer). Score gap: 0.797 vs 0.322. Temporal ordering completely inverted.

### Q8: Metaphone3 Current Strategy (Temporal)
Query: `"What is the current Metaphone3 encoding strategy and code length?"`

| Rank | Name | Score | Type | Source |
|------|------|-------|------|--------|
| 1 | Metaphone3 | 0.857 | Algorithm | node |
| 2 | Accuracy | 0.804 | Metric | node |
| 3 | Soundex | 0.769 | Algorithm | node |
| 4 | Reference corpus | 0.755 | -- | node |
| 5 | Pair explosion | 0.691 | Issue | node |

**Verdict**: FAIL -- Episode 26 (CORRECTION: hybrid approach) absent from all 10 results. Only Episode 18 content (4-char concerns) surfaces via the Metaphone3 node.

### Q9: Metaphone3 Evolution (Temporal)
Query: `"How has the Metaphone3 decision evolved over time? What changed?"`

| Rank | Name | Score | Type | Source |
|------|------|-------|------|--------|
| 1 | Accuracy | 0.735 | Metric | node |
| 2 | Reference corpus | 0.692 | -- | node |
| 3 | Metaphone3 | 0.593 | Algorithm | node |
| 4 | 32-Bit Hash Collision Bug | 0.559 | Bug | node |
| 5 | Fingerprint computation queries | 0.534 | Query | node |

**Verdict**: FAIL -- Neither Episode 26 (hybrid correction) nor Episode 20 (switch to 8-char) appear in results at all. Only Episode 18 content surfaces indirectly through the Metaphone3 node.

---

## M1: Activation Analysis

Max activation scores by query:

| Query | Max Activation | Node |
|-------|---------------|------|
| Q1 | 0.471 | Current Implementation |
| Q2 | 0.450 | Dual-Projection Strategy |
| Q3 | 0.666 | Union Blocking |
| Q4 | 0.666 | Fingerprint computation queries |
| Q5 | 0.461 | ParseHumanName UDX Crash Bug |
| Q6 | 0.444 | DataWalk ER team |
| Q7 | 0.666 | DataWalk ER team |
| Q8 | 0.462 | Metaphone3 |
| Q9 | 0.665 | 32-Bit Hash Collision Bug |

**M1 = 0.666** (PASS, target <= 0.70)

The gravity well effect from Plan 18's original E2E (activation 0.91) is eliminated. The scoring weight redistribution and activation decay are working as intended.

---

## M2: Dominance Analysis

| Query | #1 Result | Score |
|-------|-----------|-------|
| Q1 | Blocking Stage | 0.808 |
| Q2 | DataWalk Entity Resolution | 0.683 |
| Q3 | Fingerprint computation queries | 0.628 |
| Q4 | 64-bit HASH | 0.848 |
| Q5 | ParseHumanName UDX Crash Bug | 0.749 |
| Q6 | Poetry | 0.740 |
| Q7 | Episode #3 | 0.797 |
| Q8 | Metaphone3 | 0.857 |
| Q9 | Accuracy | 0.735 |

**Max same #1 = 1/9** (all unique). PASS (target <= 3/9).

The episode #24 dominance problem from the original E2E is completely resolved. No single node or episode dominates across queries.

---

## M3: Specific Event Recall Detail

| Query | Target Episode | Found? | Rank | Notes |
|-------|---------------|--------|------|-------|
| Q3 (SQL injection) | Ep 10 | NO | -- | Not in top 10. No SQL injection nodes extracted or retrievable. |
| Q4 (Fingerprint fix) | Ep 15 | YES | #1 | Excellent -- 64-bit HASH node at 0.848, strong graph context. |
| Q5 (Korean crash) | Ep 16 | YES | #1 | Excellent -- dedicated Bug node at 0.749, rich extraction. |

**M3 = 2/3 (67%)** -- PASS (target >= 66%)

Improvement from 0/3 baseline. Q3 failure suggests the SQL injection episode may not have been successfully extracted into retrievable nodes, or the security-related vocabulary doesn't overlap sufficiently with the extracted node content.

---

## M4: Temporal Evolution Detail

| Query | Expected Ranking | Actual Ranking | Pass? |
|-------|-----------------|----------------|-------|
| Q7 (Jonas role) | Ep27 > Ep2 | Ep3 (#1, 0.797) >> Ep28 (#6, 0.322) | FAIL |
| Q8 (Metaphone3 current) | Ep26 > Ep20 > Ep18 | Only Ep18 content surfaces; Ep26/Ep20 absent | FAIL |
| Q9 (Metaphone3 evolution) | Ep26 above Ep18/20 | Only Ep18 content surfaces; Ep26/Ep20 absent | FAIL |

**M4 = 0/3 (0%)** -- FAIL (target >= 66%)

This is a **regression** from the baseline (1/3 = 33%). Analysis:

1. **Jonas role (Q7)**: The original Episode #3 has much higher text relevance for "Jonas Weber" than Episode #28. The recency boost and fact supersession mechanisms are insufficient to overcome the large semantic similarity gap. No SUPERSEDES/CORRECTS edges were created between team composition nodes.

2. **Metaphone3 (Q8, Q9)**: Episode 26 (CORRECTION) content was consolidated into the existing Metaphone3 node rather than creating a new superseding node. The single Metaphone3 node (id 289) contains only Episode 18 content (4-char concerns). Episodes 20 and 26 appear to have been merged INTO existing nodes, losing the temporal correction signal. The 1 SUPERSEDES edge (Metaphone3 -> Soundex) is between algorithms, not between decision versions.

**Root cause**: The extraction pipeline merges correction episodes into existing nodes rather than creating new nodes with SUPERSEDES/CORRECTS edges. The temporal signal is absorbed and lost during consolidation.

---

## M5: Domain Routing Detail

Four semantic domains defined:
- `ncx_shared__user_profile` -- 0 nodes, 0 edges, 0 episodes
- `ncx_shared__technical_knowledge` -- 0 nodes, 0 edges, 0 episodes
- `ncx_shared__work_context` -- 0 nodes, 0 edges, 0 episodes
- `ncx_shared__domain_knowledge` -- 0 nodes, 0 edges, 0 episodes

**M5 = 0/28 (0%)** -- FAIL (target >= 75%)

Shared schemas were provisioned (ontology types exist) but no episodes were routed to any domain. The domain classifier either didn't execute, didn't classify any episodes, or the write-to-shared-graph pipeline didn't complete. Same result as original baseline.

---

## M6 & M7: Type Quality Detail

### M6: Corrupted Type Names (4 found -- FAIL)

| # | Type Name | Issue | Count |
|---|-----------|-------|-------|
| 1 | `DatasetNoteTheSearchResultsShowed...` (440+ chars) | LLM reasoning chain leaked into type name | 1 |
| 2 | `EvidencedocumentOceanography` | Lowercase 'd' (not PascalCase); "Oceanography" irrelevant to ER domain | 2 |
| 3 | `FeatureMergesWithEntityObjectId167` | Node ID embedded in type name | 1 |
| 4 | `OperationbrCreateOrUpdate...` (300+ chars) | LLM tool-call reasoning leaked into type name | 1 |

The type name validation from Plan 18 Stage 5 (regex rejection) does not appear to be catching these. Types #1 and #4 are massive strings that contain the LLM's internal planning/reasoning, suggesting the extraction agent's output parsing fails to isolate the type name field from surrounding reasoning text.

### M7: Cross-Extraction Type Consistency (~5 duplicates -- SAME)

| Entity | Types Assigned | Same Merge Group? | Merged? |
|--------|---------------|-------------------|---------|
| Blocking | Methodology (175) + Operation (307) | No | No |
| Exact Duplicate Deduplication | Methodology (256) + Operation (221) | No | No |
| ANALYZE_STATISTICS | Algorithm (187) + Operation (252) | No | No |
| ParseHumanName / ParseHumanName UDX | Algorithm (169) + SoftwareSystem (266) | No | No |
| IC computation / IC computation formula | Algorithm (302) + Algorithm (305) | Same type | Not merged |

**Positive**: Metaphone3 is consistently typed as `Algorithm` only (was Methodology+Tool in baseline).
**Negative**: Operation type creates new cross-type duplicates with Methodology and Algorithm.

---

## Findings & Observations

### What Improved
- **M1 (activation control)**: Max activation dropped from 0.91 to 0.666. Gravity well eliminated.
- **M2 (dominance)**: Episode #24 no longer dominates. All 9 queries have unique #1 results (was 8/9 same).
- **M3 (specific events)**: Improved from 0/3 to 2/3. Korean bug and fingerprint collision recalled well.
- **Extraction rate**: 93% consolidation (27/29) vs 68% (19/28). Significantly more episodes processed.
- **Node count**: 206 nodes (vs 121) -- richer, more granular graph.
- **Empty types**: 0 (vs 6) -- all extracted types have instances.
- **SUPERSEDES edges**: 1 created (vs 0) -- mechanism exists, just underused.

### What Didn't Improve
- **M4 (temporal recall)**: Regressed from 1/3 to 0/3. Corrections are absorbed into existing nodes rather than creating superseding nodes.
- **M5 (domain routing)**: Still 0%. Shared schemas are provisioned but never populated.
- **M6 (type corruption)**: Worse than baseline (4 corrupted vs 1+). LLM reasoning leaks are a new class of corruption not seen before.

### New Issues Discovered
1. **Recall tool bug**: `embedding::float[]` cast failed on pgvector type. Required hotfix (`NULL::float[]`) to unblock measurements. The `embedding_vec` field in recall results was non-functional.
2. **LLM reasoning leaks**: Two type names contain hundreds of characters of the extraction agent's internal reasoning/planning text. This is a new failure mode.
3. **Operation type proliferation**: The extraction pipeline creates `Operation` nodes that duplicate `Methodology` and `Algorithm` nodes, creating new cross-type inconsistencies.
4. **SQL injection episode invisible**: Episode 10 (SQL injection vulnerability) was not extractable or retrievable via any recall query, despite being stored and consolidated.

### Recommendations

1. **Temporal recall (M4)**: The extraction pipeline needs explicit logic to detect CORRECTION/UPDATE markers in episodes and create new nodes with SUPERSEDES/CORRECTS edges rather than merging into existing nodes. The current merge-on-name behavior destroys temporal signals.

2. **Domain routing (M5)**: Investigate why the domain classifier doesn't fire during extraction jobs. Check if the classifier agent is being invoked, whether it returns results, and whether the write-permission flow to shared schemas works end-to-end.

3. **Type corruption (M6)**: Add output sanitization to the extraction agents -- strip any text that doesn't match `^[A-Z][a-zA-Z0-9]*$` (nodes) or `^[A-Z][A-Z0-9_]+$` (edges) before writing to the graph. Consider a maximum type name length (e.g., 50 chars).

4. **Recall bug**: Fix the `embedding::float[]` cast properly (use `REPLACE(REPLACE(embedding::text, '[', '{'), ']', '}')::float[]` or a helper function) to restore MMR reranking capability.

5. **SQL injection recall (Q3)**: Investigate why Episode 10 content doesn't surface. Check if the episode was successfully extracted and what nodes were created from it. The security/vulnerability vocabulary may not overlap with the extracted node content.
