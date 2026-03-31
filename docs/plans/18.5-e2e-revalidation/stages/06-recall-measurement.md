# Stage 6: Recall Quality Measurement

**Goal**: Run all 9 recall queries from `resources/recall-queries.md`, record scores/ranks, and compute metrics M1--M4.
**Dependencies**: Stage 3 (Extraction Wait) must be DONE. Stages 4--5 can run before or after this stage.

---

## Steps

### Setup

1. **Read recall queries**
   - Read `resources/recall-queries.md` for the exact query text, expected results, and pass criteria

### Execute Queries

2. **Run Q1: Blocking concept**
   - `recall(query="What is blocking in entity resolution and how does the system implement it?", limit=10)`
   - Record for each result: position (1=highest score), name, score, activation_score, source_kind, item_type
   - Note whether blocking-related content appears in top 3
   - Record the #1 result name/id

3. **Run Q2: Architecture**
   - `recall(query="Describe the overall system architecture and Vertica design patterns", limit=10)`
   - Same recording as Q1
   - Note whether architecture content appears in top 3

4. **Run Q3: SQL injection (specific event)**
   - `recall(query="SQL injection vulnerability in normalization service", limit=10)`
   - Check if Episode 10 content or nodes mentioning SQL injection + IdentifierLinkNormalizationService appear in top 5
   - Record PASS or FAIL for M3

5. **Run Q4: Fingerprint collision (specific event)**
   - `recall(query="fingerprint hash collision birthday paradox 32-bit to 64-bit", limit=10)`
   - Check if Episode 15 content or nodes mentioning birthday paradox / 32-bit / fingerprint fix appear in top 5
   - Record PASS or FAIL for M3

6. **Run Q5: Korean character bug (specific event)**
   - `recall(query="Korean character crash UDX bug in name parsing", limit=10)`
   - Check if Episode 16 content or nodes mentioning Korean/hangul/CJK + ParseHumanName appear in top 5
   - Record PASS or FAIL for M3

7. **Run Q6: Team composition**
   - `recall(query="Who is on the DataWalk ER team and what are their roles?", limit=10)`
   - Check if team/person information appears in top 5

8. **Run Q7: Jonas role (temporal)**
   - `recall(query="What is Jonas Weber's current role and team assignment?", limit=10)`
   - Check if Episode 27 (security team transfer) ranks ABOVE Episode 2 (original backend role)
   - Record PASS or FAIL for M4

9. **Run Q8: Metaphone3 current strategy (temporal)**
   - `recall(query="What is the current Metaphone3 encoding strategy and code length?", limit=10)`
   - Check if Episode 26 (CORRECTION: hybrid approach) ranks above Episodes 18 and 20
   - This is the PRIMARY temporal test -- was 0% in baseline
   - Record PASS or FAIL for M4

10. **Run Q9: Metaphone3 evolution (temporal)**
    - `recall(query="How has the Metaphone3 decision evolved over time? What changed?", limit=10)`
    - Check if Episode 26 appears in results AND ranks above Episodes 18/20
    - Record PASS or FAIL for M4

### Compute Metrics

11. **Compute M1: Max Activation**
    - Scan all activation_score values across all 9 query results
    - M1 = maximum activation_score observed
    - Record:
      ```
      M1: Max activation after 9 queries
      Baseline: 0.91
      Target: <= 0.70
      Measured: [value]
      Verdict: PASS / FAIL
      ```

12. **Compute M2: Single-Episode Dominance**
    - List the #1 result for each query:
      ```
      | Query | #1 Result Name | Score |
      |-------|---------------|-------|
      | Q1 | ... | ... |
      | Q2 | ... | ... |
      | ... | ... | ... |
      | Q9 | ... | ... |
      ```
    - Count the maximum number of queries where the SAME item holds #1
    - Record:
      ```
      M2: Single-episode dominance
      Baseline: 8/9 (89%) -- Episode #24 dominated
      Target: <= 3/9 (33%)
      Measured: [N]/9 ([X]%)
      Most frequent #1: [name] appeared [N] times
      Verdict: PASS / FAIL
      ```

13. **Compute M3: Specific Event Recall**
    - Count passes from Q3, Q4, Q5:
      ```
      Q3 (SQL injection): PASS / FAIL
      Q4 (fingerprint collision): PASS / FAIL
      Q5 (Korean character bug): PASS / FAIL
      M3 = [count]/3
      ```
    - Record:
      ```
      M3: Specific event recall rate
      Baseline: 0% (0/3)
      Target: >= 66% (2/3)
      Measured: [count]/3 ([X]%)
      Verdict: PASS / FAIL
      ```

14. **Compute M4: Temporal Evolution Recall**
    - Count passes from Q7, Q8, Q9:
      ```
      Q7 (Jonas role): PASS / FAIL
      Q8 (Metaphone3 current): PASS / FAIL
      Q9 (Metaphone3 evolution): PASS / FAIL
      M4 = [count]/3
      ```
    - Record:
      ```
      M4: Temporal evolution recall rate
      Baseline: 33% (1/3)
      Target: >= 66% (2/3)
      Measured: [count]/3 ([X]%)
      Verdict: PASS / FAIL
      ```

---

## Important Notes

- Run queries **sequentially** (each recall increments access_count on returned items, affecting subsequent queries)
- The order matters for M1/M2 -- gravity well effect compounds over sequential queries
- Record **ALL** numeric values, not just pass/fail -- we need the raw data for the final report
- If a query returns zero results, record it as a separate finding (indicates embedding or indexing issue)
- **`activation_score` availability**: Phase 1 recall results (from `repo.recall()`) populate `activation_score`. Phase 2 search results (from `repo.search_nodes()`) may return `activation_score: null`. For M1, compute from results where `activation_score` is not null. If the most frequently returned node has null `activation_score`, use `inspect_node` on it to read `access_count` directly and compute activation manually via `sqrt(access_count)` as an approximation.
- Results have no `rank` field -- infer rank from position in the returned list (1 = highest score)
- For M4 temporal tests: "ranks above" means the newer item appears at a lower position number (1 = highest) than the older item

---

## Verification

- [ ] All 9 queries executed and results recorded
- [ ] M1 computed from activation scores
- [ ] M2 computed from #1 result tracking
- [ ] M3 computed from Q3/Q4/Q5 pass rates
- [ ] M4 computed from Q7/Q8/Q9 pass rates
- [ ] All raw data preserved for report generation

---

## Outputs

Record in the index.md progress tracker notes:
- "M1: [value] (target <= 0.70) -- PASS/FAIL"
- "M2: [N]/9 (target <= 3/9) -- PASS/FAIL"
- "M3: [N]/3 (target >= 2/3) -- PASS/FAIL"
- "M4: [N]/3 (target >= 2/3) -- PASS/FAIL"
