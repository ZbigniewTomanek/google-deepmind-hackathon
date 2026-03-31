# Stage 7: Report Generation

**Goal**: Compile all measurements from Stages 4--6 into a structured comparison report saved to `demo-data/e2e-revalidation-report.md`.
**Dependencies**: Stages 4, 5, and 6 must all be DONE

---

## Steps

1. **Gather all measurements**
   - M1 (max activation) from Stage 6
   - M2 (single-episode dominance) from Stage 6
   - M3 (specific event recall) from Stage 6
   - M4 (temporal evolution recall) from Stage 6
   - M5 (domain routing) from Stage 4
   - M6 (corrupted types) from Stage 5
   - M7 (type consistency) from Stage 5
   - Graph statistics from Stages 3 and 5
   - Raw query data from Stage 6

2. **Write the report**
   - Create `demo-data/e2e-revalidation-report.md` with the structure below
   - Include all numeric measurements, comparisons to baseline, and verdicts

3. **Determine overall verdict**
   - PASS = M1 through M6 all meet targets (M7 is qualitative, not a hard gate)
   - PARTIAL = 5-6 metrics meet targets
   - FAIL = fewer than 5 metrics meet targets

---

## Report Structure

```markdown
# NeoCortex E2E Re-Validation Report

**Date**: 2026-03-31
**Predecessor**: Plan 18 (Recall Quality Overhaul) -- 7 stages implemented
**Scenario**: 28-episode DataWalk ER project simulation (same scenario as original E2E)
**Agent**: [agent_id]
**Overall Verdict**: PASS / PARTIAL / FAIL

---

## Summary Table

| # | Metric | Baseline | Target | Measured | Verdict |
|---|--------|----------|--------|----------|---------|
| M1 | Max activation (9 queries) | 0.91 | <= 0.70 | ... | ... |
| M2 | Single-episode dominance | 8/9 (89%) | <= 3/9 (33%) | ... | ... |
| M3 | Specific event recall | 0% (0/3) | >= 66% (2/3) | ... | ... |
| M4 | Temporal evolution recall | 33% (1/3) | >= 66% (2/3) | ... | ... |
| M5 | Domain routing | 0% (0/28) | >= 75% (21/28) | ... | ... |
| M6 | Corrupted type names | 1+ | 0 | ... | ... |
| M7 | Type consistency | Multiple dupes | Improved | ... | ... |

---

## Graph Statistics

| Metric | Original E2E | Re-Validation |
|--------|-------------|---------------|
| Episodes stored | 28 | 28 |
| Episodes consolidated | 19/28 (68%) | .../28 (...%) |
| Nodes created | 121 | ... |
| Edges created | 45 | ... |
| Node types (total / empty) | 42 / 6 | ... / ... |
| Edge types | 38 | ... |
| SUPERSEDES edges | 0 | ... |
| CORRECTS edges | 0 | ... |

---

## Detailed Query Results

### Q1: Blocking Concept
[Top 5 results table with rank, name, score, type, source_kind]

### Q2: Architecture
[Same format]

... [all 9 queries] ...

---

## M1: Activation Analysis

[Track of activation scores across queries, identify highest]

---

## M2: Dominance Analysis

[Table of #1 results per query, frequency count]

---

## M3: Specific Event Recall Detail

| Query | Target Episode | Found? | Rank | Notes |
|-------|---------------|--------|------|-------|
| Q3 (SQL injection) | Ep 10 | ... | ... | ... |
| Q4 (Fingerprint fix) | Ep 15 | ... | ... | ... |
| Q5 (Korean crash) | Ep 16 | ... | ... | ... |

---

## M4: Temporal Evolution Detail

| Query | Expected Ranking | Actual Ranking | Pass? |
|-------|-----------------|----------------|-------|
| Q7 (Jonas role) | Ep27 > Ep2 | ... | ... |
| Q8 (Metaphone3 current) | Ep26 > Ep20 > Ep18 | ... | ... |
| Q9 (Metaphone3 evolution) | Ep26 above Ep18/20 | ... | ... |

---

## M5: Domain Routing Detail

[Which shared graphs exist, their sizes, routing distribution]

---

## M6 & M7: Type Quality Detail

[Corrupted types found, semantic duplicate analysis]

---

## Findings & Observations

### What Improved
[List specific improvements vs original E2E]

### What Didn't Improve
[List metrics that didn't meet targets]

### New Issues Discovered
[Any new problems not present in original E2E]

### Recommendations
[If any metrics fail, suggest next steps]
```

---

## Verification

- [ ] Report written to `demo-data/e2e-revalidation-report.md`
- [ ] All 7 metrics included with baseline/target/measured/verdict
- [ ] Graph statistics comparison table complete
- [ ] All 9 query results included with raw data
- [ ] Overall verdict determined
- [ ] Index.md updated with final status

---

## Outputs

Record in the index.md progress tracker notes:
- "Report: demo-data/e2e-revalidation-report.md"
- "Overall verdict: PASS/PARTIAL/FAIL -- [N]/7 metrics met"
