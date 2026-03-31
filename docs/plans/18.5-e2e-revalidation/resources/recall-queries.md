# Recall Queries -- 9 Queries for E2E Re-Validation

Each query specifies the recall text, expected results, which metric it measures, and pass criteria.

---

## Query Categories

| Category | Queries | Original Baseline | Target | Metrics |
|----------|---------|-------------------|--------|---------|
| Domain concepts | Q1, Q2 | 100% pass | Maintain | M2 (diversity) |
| Specific events | Q3, Q4, Q5 | 0% pass (0/3) | >= 66% (2/3) | M3 (specific event recall) |
| People | Q6, Q7 | 75% pass | Maintain or improve | M2, M4 |
| Temporal evolution | Q8, Q9 | 33% pass (1/3) | >= 66% (2/3) | M4 (temporal recall) |

Additional measurement across ALL queries: M1 (max activation), M2 (single-episode dominance).

---

## Q1: Domain Concept -- Blocking

**Query**: `"What is blocking in entity resolution and how does the system implement it?"`
**Limit**: 10

**Expected in top 5**:
- Episode 6 (Blocking Strategy) or its extracted nodes
- Episode 9 (Blocking with IC Stop-Lists) or its extracted nodes

**Pass criteria**: At least one blocking-related result in top 3.

**Measures**: M2 (should NOT be dominated by Episode 24 / Fellegi-Sunter gap analysis)

---

## Q2: Domain Concept -- System Architecture

**Query**: `"Describe the overall system architecture and Vertica design patterns"`
**Limit**: 10

**Expected in top 5**:
- Episode 7 (Vertica Architecture) or its extracted nodes
- Episode 4 (Normalized Tables) or its extracted nodes

**Pass criteria**: At least one architecture-related result in top 3.

**Measures**: M2

---

## Q3: Specific Event -- SQL Injection

**Query**: `"SQL injection vulnerability in normalization service"`
**Limit**: 10

**Expected in top 5**:
- Episode 10 (SQL Injection in IdentifierLinkNormalizationService)

**Pass criteria**: Episode 10 content (or a node extracted from it mentioning SQL injection + IdentifierLinkNormalizationService) appears in top 5.

**Measures**: M3 (specific event recall -- this was 0% in baseline)

---

## Q4: Specific Event -- Fingerprint Collision

**Query**: `"fingerprint hash collision birthday paradox 32-bit to 64-bit"`
**Limit**: 10

**Expected in top 5**:
- Episode 15 (Fingerprint 32-to-64 Bit Collision Fix)

**Pass criteria**: Episode 15 content (or a node mentioning birthday paradox / 32-bit collision / fingerprint fix) appears in top 5.

**Measures**: M3

---

## Q5: Specific Event -- Korean Character Bug

**Query**: `"Korean character crash UDX bug in name parsing"`
**Limit**: 10

**Expected in top 5**:
- Episode 16 (Korean Character UDX Crash)

**Pass criteria**: Episode 16 content (or a node mentioning Korean/hangul/CJK + ParseHumanName + crash) appears in top 5.

**Measures**: M3

---

## Q6: People -- Team Composition

**Query**: `"Who is on the DataWalk ER team and what are their roles?"`
**Limit**: 10

**Expected in top 5**:
- Episode 2 (Team Composition) or person nodes extracted from it
- Episode 27 (Team Change) -- should also surface due to team topic

**Pass criteria**: At least one person-related result in top 5.

**Measures**: M2

---

## Q7: People -- Jonas Role (Temporal)

**Query**: `"What is Jonas Weber's current role and team assignment?"`
**Limit**: 10

**Expected top result**:
- Episode 27 (Team Change -- Jonas moved to Security team) should rank ABOVE
- Episode 2 (original Team Composition -- Jonas as backend engineer)

**Pass criteria**: The security team transfer (Episode 27 / its nodes) ranks above the original backend role (Episode 2 / its nodes).

**Measures**: M4 (temporal evolution -- correction should supersede original)

---

## Q8: Temporal Evolution -- Metaphone3 Current Strategy

**Query**: `"What is the current Metaphone3 encoding strategy and code length?"`
**Limit**: 10

**Expected ranking** (newest first):
1. Episode 26 (CORRECTION: hybrid 8-char Latin / 4-char non-Latin) -- MUST rank highest
2. Episode 20 (switch to 8-char) -- should rank below Episode 26
3. Episode 18 (4-char concerns) -- should rank lowest of the three

**Pass criteria**: Episode 26 (the CORRECTION) or its extracted nodes rank above Episodes 18 and 20.

**Measures**: M4 (temporal evolution -- this was the primary temporal test in the original E2E)

---

## Q9: Temporal Evolution -- Metaphone3 Decision History

**Query**: `"How has the Metaphone3 decision evolved over time? What changed?"`
**Limit**: 10

**Expected**: All three Metaphone3 episodes (18, 20, 26) should appear, with Episode 26 ranked highest.

**Pass criteria**: Episode 26 (or its nodes) appears in results AND ranks above at least one of Episodes 18/20.

**Measures**: M4

---

## Measurement Protocol

After running all 9 queries, compute:

### M1: Max Activation
- For each query result, record the `activation_score` of every returned item
- M1 = max(all activation_scores across all 9 queries)
- **Pass**: M1 <= 0.70

### M2: Single-Episode Dominance
- Record the name/id of the #1 result in each query
- Count the maximum number of queries where the same item is #1
- **Pass**: max_count <= 3 out of 9

### M3: Specific Event Recall
- Queries Q3, Q4, Q5
- Count how many pass their individual pass criteria
- **Pass**: >= 2 out of 3 pass

### M4: Temporal Evolution Recall
- Queries Q7, Q8, Q9
- Count how many pass their individual pass criteria (latest fact ranks above older)
- **Pass**: >= 2 out of 3 pass
