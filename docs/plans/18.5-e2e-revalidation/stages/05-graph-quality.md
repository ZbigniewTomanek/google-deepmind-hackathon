# Stage 5: Graph Quality Inspection

**Goal**: Validate type name integrity (M6) and cross-extraction type consistency (M7) in the extracted graph.
**Dependencies**: Stage 3 (Extraction Wait) must be DONE

---

## Steps

### Part A: Type Name Corruption Check (M6)

1. **Discover ontology**
   - Call `discover_ontology(graph_name=<personal_graph>)` to list all node types and edge types
   - Record the complete type lists

2. **Scan for corrupted types**
   - Check every node type name for:
     - Contains `}` or `{` (JSON corruption artifacts)
     - Contains special characters other than letters and digits
     - Doesn't match PascalCase pattern (`^[A-Z][a-zA-Z0-9]*$`)
     - Looks like hallucinated nonsense (e.g., "OceanScience" in an ER context)
   - Check every edge type name for:
     - Contains `}` or `{`
     - Doesn't match SCREAMING_SNAKE pattern (`^[A-Z][A-Z0-9_]*[A-Z0-9]$`)
   - Record any violations found

3. **Measure M6**
   ```
   M6: Corrupted type names
   Baseline: 1+ (original had "Constraint}OceanScience")
   Target: 0
   Measured: [count]
   Verdict: PASS / FAIL
   ```

4. **Check for empty types**
   - Note any node types or edge types with 0 instances
   - The original E2E had: Vulnerability (0), BacklogItem (0), SystemLayer (0)
   - Plan 18 Stage 7 added `cleanup_empty_types` -- expect fewer empty types

### Part B: Cross-Extraction Type Consistency (M7)

5. **Browse nodes to find potential duplicates**
   - Call `browse_nodes(graph_name=<personal_graph>)` to see all node instances
   - Look for the same real-world entity appearing with different types:
     - "Metaphone3" -- should consistently be Tool (not also Methodology)
     - "Blocking" -- should consistently be one type (not both Methodology AND ProcessStage)
     - "Vertica" -- should consistently be one type (not both DataStore AND Tool)
     - "Fellegi-Sunter" -- should consistently be one type
   - The expanded merge-safe groups in Plan 18 Stage 7 should allow merging:
     - Tool/Technology/Framework/Library/Software
     - Methodology/Method/Approach/Strategy/Technique/ProcessStage
     - Dataset/Data/DataSource/DataStore

6. **Count semantic duplicates**
   - For each entity that appears with multiple types, check if those types are in the same merge-safe group
   - If same group: the dedup should have merged them (if not, it's a regression)
   - If different groups: this is expected (e.g., "Python" as Language vs Tool)
   - Record findings:
     ```
     | Entity | Types Assigned | Same Merge Group? | Merged? |
     |--------|---------------|-------------------|---------|
     | ... | ... | ... | ... |
     ```

7. **Measure M7**
   ```
   M7: Cross-extraction type consistency
   Baseline: Multiple duplicates (Metaphone3 as Methodology+Tool, Blocking as Methodology+ProcessStage, etc.)
   Target: Fewer semantic duplicates than baseline
   Measured: [count] entities with multiple types
   Verdict: IMPROVED / SAME / WORSE
   ```

### Part C: Overall Graph Quality Statistics

8. **Record graph structure summary**
   ```
   | Metric | Original E2E | Current |
   |--------|-------------|---------|
   | Node types (total) | 42 | ... |
   | Node types (empty) | 6 | ... |
   | Edge types (total) | 38 | ... |
   | Avg activation | 0.24 | ... |
   | SUPERSEDES edges | 0 | ... |
   | CORRECTS edges | 0 | ... |
   ```

9. **Check temporal edge types**
   - Verify SUPERSEDES and CORRECTS edge types exist in the ontology
   - Check if any edges of these types were actually created
   - If yes, inspect which nodes they connect (should link Episode 26's nodes to Episodes 18/20's nodes)
   - Call `inspect_node` on Metaphone3-related nodes to see their edge neighborhoods

---

## Verification

- [ ] All node and edge types scanned for corruption
- [ ] M6 measured and verdict recorded
- [ ] Semantic duplicate analysis completed
- [ ] M7 measured and verdict recorded
- [ ] SUPERSEDES/CORRECTS edge types checked
- [ ] Graph quality summary table filled

---

## Outputs

Record in the index.md progress tracker notes:
- "M6: [count] corrupted types -- PASS/FAIL"
- "M7: [count] semantic duplicates -- IMPROVED/SAME/WORSE"
- "[N] SUPERSEDES edges, [M] CORRECTS edges found"
