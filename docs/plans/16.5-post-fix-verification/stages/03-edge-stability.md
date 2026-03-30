# Stage 3: Edge Type Stability

**Goal**: Verify that relationship types remain stable across multiple extractions (Plan 15 Issue #2: edge type instability).

**Dependencies**: Stage 2 (multiple extractions of same entities already occurred)

---

## What Plan 15 Found

> Same relationship gets 5+ types: IMPLEMENTS → HAS_DEADLINE → FORMER_MEMBER_OF → FOLLOWS → EXTRACTS_FROM.
> Each extraction randomly re-types edges. Makes relationship semantics meaningless.

## What Plan 16 Fixed

- Stage 2-3: Librarian uses `get_edges_between` tool to check existing edges before creating
- Stage 3: Tool prompt says "prefer updating edge types over creating duplicates"
- Stage 4: Adapter-level edge dedup catches type drift (merges into existing edge)

---

## Experiment Design

### Test 3A: Re-state known relationships with different framing

Store facts that describe the same relationships but with different wording,
which previously caused the LLM to generate different edge types:

```
remember(
  text="Jonas Berg works under Maya Chen's technical direction on the DataForge project. He is responsible for the stream processing layer of the platform.",
  importance=0.6
)
```

This describes Jonas→Maya (same as Stage 1's "reporting to") and Jonas→DataForge
(same as "backend engineer on Team Atlas" which builds DataForge).

**Verification:**
```
inspect_node(node_name="Jonas Berg", graph_name=<name>)
→ Record: ALL edge types connecting Jonas to Maya and DataForge
→ Expected: 1 edge to Maya (e.g., REPORTS_TO), not 2+ with different types
→ Expected: 1 edge to DataForge/Atlas (e.g., MEMBER_OF or WORKS_ON), not 2+ with different types
```

### Test 3B: Another relationship restatement

```
remember(
  text="Priya Sharma is building the anomaly detection module as part of DataForge. She collaborates closely with Jonas Berg on the streaming data interface between the ML pipeline and the ingestion layer.",
  importance=0.6
)
```

**Verification:**
```
inspect_node(node_name="Priya Sharma", graph_name=<name>)
→ Record: ALL edges from Priya
→ Expected: No duplicate relationship types for same entity pairs
→ Expected: 1 edge to DataForge, 1 edge to Team Atlas (or merged), 1 to Jonas

get edges between Priya and Jonas (via inspect_node)
→ Expected: At most 1 edge (COLLABORATES_WITH or similar)
```

### Test 3C: Check overall edge type count

```
discover_ontology(graph_name=<name>)
→ Record: Total number of distinct edge types
→ Expected: Reasonable count (10-20 types), not explosion (30+ types)
→ Compare: Plan 15 had runaway type creation

browse_nodes(graph_name=<name>, limit=40)
→ Cross-reference: count unique entity pairs and compare to total edges
```

---

## Verification Checklist

- [ ] **3A**: Jonas→Maya has 1 edge type (not 2+ different types)
- [ ] **3A**: Jonas→DataForge/Atlas has 1 edge type (not 2+ different types)
- [ ] **3B**: Priya's edges show no duplicate types for same target
- [ ] **3C**: Total distinct edge types is reasonable (≤25)
- [ ] No evidence of edge type "drift" — same relationship keeps same type across extractions

---

## Results

[Fill in during execution]

### Test 3A: Jonas Berg Edge Stability
- Edges to Maya Chen:
- Edges to DataForge/Atlas:
- **Verdict**: PASS / FAIL

### Test 3B: Priya Sharma Edge Stability
- Total edges:
- Duplicate type pairs:
- **Verdict**: PASS / FAIL

### Test 3C: Ontology Health
- Total distinct edge types:
- Total edges in graph:
- Edge type / entity pair ratio:
- **Verdict**: PASS / FAIL
