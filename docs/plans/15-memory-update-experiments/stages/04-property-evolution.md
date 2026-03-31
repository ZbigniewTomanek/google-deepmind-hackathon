# Stage 4: Entity Property Evolution

**Goal**: Test how node properties accumulate or replace over multiple updates to the same entity.

**Dependencies**: Stage 3

---

## Experiment Design

### 4.1 Build up entity properties incrementally
```
remember("The WNP pruning algorithm achieved 63% pair reduction at 1M entities in Plan 36c", importance=0.7)
remember("WNP pruning hurt recall by -3.72 percentage points in Plan 36c", importance=0.7)
remember("In Plan 36d, WNP pruning improved to only -1.96pp recall loss because coarse-only matches were removed", importance=0.8)
```

### 4.2 Inspect the WNP node
```
recall("WNP pruning performance")
inspect_node(node_name="WNP", graph_name=<personal_graph>)
```
If WNP doesn't exist as a node, try:
```
browse_nodes(graph_name=<personal_graph>)
```

**Key questions**:
- Did all 3 memories merge into one "WNP" node?
- Were properties accumulated (all 3 data points present)?
- Or did later properties overwrite earlier ones?
- What does the content field contain?

### 4.3 Test conflicting properties on same entity
```
remember("The blocking pipeline has 4 stages: normalization, feature extraction, blocking, scoring", importance=0.6)
remember("The blocking pipeline has been extended to 6 stages: normalization, feature extraction, blocking, pruning, scoring, evaluation", importance=0.7)
```

### 4.4 Recall pipeline structure
```
recall("How many stages does the blocking pipeline have?")
inspect_node(node_name="blocking pipeline", graph_name=<personal_graph>)
```

**Key question**: Is "4 stages" or "6 stages" in the node? Both? Neither?

---

## Verification

- [ ] Property accumulation behavior documented
- [ ] Property conflict behavior documented
- [ ] Content field update behavior documented
- [ ] Node structure after multiple updates documented

---

## Results

### 4.1-4.2 WNP property accumulation
[Log results]

### 4.3-4.4 Conflicting properties
[Log results]

### Analysis
[Characterize property evolution model: accumulative? last-write-wins? merge?]
