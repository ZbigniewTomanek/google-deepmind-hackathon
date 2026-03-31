# Stage 6: Temporal & Importance Effects

**Goal**: Test whether recency, importance, and access frequency affect recall ranking as expected by the scoring model.

**Dependencies**: Stage 5 (graph has diverse facts at different ages/importance levels)

---

## Experiment Design

### 6.1 Check scoring behavior across accumulated data
By this stage, the graph has facts stored at different times with different importance levels.

```
recall("engineering team information", limit=20)
```

**Observe**: Are results ordered by recency? Importance? Semantic relevance? A mix?

### 6.2 Test importance effect
```
remember("CRITICAL: Production database credentials must be rotated before April 5, 2026", importance=1.0)
remember("The office coffee machine is on the 3rd floor", importance=0.1)
```

```
recall("important upcoming deadlines")
recall("office information")
```

**Key question**: Does importance=1.0 fact dominate general queries?

### 6.3 Test access frequency (activation)
Recall the same fact 5 times to boost its access_count:
```
recall("WNP pruning")  # x5
```

Then recall a broader query:
```
recall("ER engine optimization techniques")
```

**Key question**: Does the repeatedly-accessed WNP fact rank higher than equally-relevant but less-accessed facts?

### 6.4 Inspect scoring details
```
discover_ontology(graph_name=<personal_graph>)
browse_nodes(graph_name=<personal_graph>)
```

**Document**: Total node count, edge count, episode count at this point.

---

## Verification

- [ ] Scoring factors (recency, importance, activation) effects documented
- [ ] High-importance facts appear in relevant queries
- [ ] Access frequency impact on ranking documented
- [ ] Full graph statistics captured

---

## Results

### 6.1 Mixed recall
[Log results — note ordering]

### 6.2 Importance test
[Log results]

### 6.3 Activation test
[Log results — compare WNP ranking before/after repeated access]

### 6.4 Graph statistics
[Log full graph state]

### Analysis
[How well does the hybrid scoring model work in practice?]
