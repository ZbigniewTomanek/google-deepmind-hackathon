# Stage 2: Fact Updates

**Goal**: Test what happens when a previously stored fact changes.

**Dependencies**: Stage 1 (graph has baseline facts)

---

## Experiment Design

### 2.1 Update Alice's team
```
remember("Alice has moved from the billing team to the auth team as tech lead", importance=0.8)
```

### 2.2 Recall Alice
```
recall("What team does Alice work on?")
recall("Alice")
```

**Expected behavior options**:
- A) Returns only new fact (ideal — system understood the update)
- B) Returns both old and new (system sees them as separate memories)
- C) Returns old fact only (system failed to capture update)

### 2.3 Check graph structure
```
discover_ontology(graph_name=<personal_graph>)
browse_nodes(graph_name=<personal_graph>, type_name="Person")
inspect_node(node_name="Alice", graph_name=<personal_graph>)
```

**Key questions**:
- Is there 1 Alice node or 2?
- If 1: were properties merged? Which content was kept?
- What edges exist? (billing AND auth? or just auth?)
- Are both episodes visible?

### 2.4 Update ER engine fact
```
remember("The ER engine switched from 4-char to 8-char Metaphone3 precision for better blocking selectivity", importance=0.9)
```

### 2.5 Recall ER fact
```
recall("What precision does the ER engine use for Metaphone3?")
```

**Key question**: Does recall return the old 4-char info, the new 8-char info, or both?

---

## Verification

- [ ] Alice node count documented (1 vs 2)
- [ ] Edge behavior documented (additive vs replacement)
- [ ] Content/property merge behavior documented
- [ ] Recall ranking of old vs new facts documented

---

## Results

### 2.1 Update remember
[Log raw response]

### 2.2 Alice recall
[Log raw responses — note which facts appear and in what order]

### 2.3 Graph inspection
[Log node/edge structure — this is the critical data]

### 2.4-2.5 ER engine update
[Log results]

### Analysis
[Characterize the update model: append? merge? replace?]
