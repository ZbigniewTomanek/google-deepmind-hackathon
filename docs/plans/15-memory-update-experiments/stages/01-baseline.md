# Stage 1: Baseline — Remember & Recall

**Goal**: Verify the MCP server works on a fresh start and establish baseline behavior.

**Dependencies**: None (first stage, fresh server)

---

## Experiment Design

### 1.1 Store three simple facts
```
remember("Alice is a senior engineer on the billing team", importance=0.7)
remember("The ER engine uses Metaphone3 for phonetic blocking", importance=0.8)
remember("Sprint planning happens every Monday at 10am", importance=0.5)
```

### 1.2 Discover graph state
```
discover_graphs()
discover_ontology(graph_name=<personal_graph>)
```

**Expected**: Graph exists with nodes extracted from the three episodes.

### 1.3 Recall each fact
```
recall("Who is Alice and what team is she on?")
recall("What algorithm does the ER engine use for blocking?")
recall("When is sprint planning?")
```

**Expected**: Each query returns relevant results.

### 1.4 Cross-cutting recall
```
recall("Tell me about the team's engineering practices")
```

**Expected**: Returns multiple related results.

---

## Verification

- [ ] `discover_graphs` shows at least 1 graph with nodes > 0
- [ ] Each targeted recall returns the stored fact
- [ ] Cross-cutting recall returns multiple results

---

## Results

### 1.1 Remember results
[Log raw MCP responses here]

### 1.2 Graph state
[Log discover results here]

### 1.3 Targeted recall
[Log recall results here]

### 1.4 Cross-cutting recall
[Log recall results here]

### Analysis
[What worked? What was surprising?]
