# Stage 5: Weight Management

**Goal**: Verify that edge weights stay bounded after repeated recalls (Plan 15 Issue #4: weight creep).

**Dependencies**: Stage 4 (graph has enough entities and edges for meaningful weight analysis)

---

## What Plan 15 Found

> Weights climbed from 1.0 → 1.75+ in just a few days.
> Linear +0.05/recall with no continuous decay.
> Frequently-accessed subgraphs dominate scoring regardless of query relevance.

## What Plan 16 Fixed

- Stage 5: Logarithmic diminishing returns: `delta / (1.0 + (weight - 1.0) * 5.0)`
- Stage 5: Micro-decay (25% probability, 0.998x on recent non-traversed edges)
- Stage 5: Stale-edge decay (25% probability, 48h window, 0.95x)
- Stage 5: Ceiling of 1.5

---

## Experiment Design

### Test 5A: Baseline edge weights

Before repeated recalls, snapshot current edge weights:

```
inspect_node(node_name="Maya Chen", graph_name=<name>)
→ Record: all edge weights in Maya's neighborhood

inspect_node(node_name="DataForge", graph_name=<name>)
→ Record: all edge weights in DataForge's neighborhood
```

### Test 5B: Repeated recalls (10x)

Run the same query 10 times to trigger reinforcement:

```
recall(query="Tell me about Maya Chen and her role on Team Atlas", limit=5)
→ Run this 10 times
→ Record: scores from first, 5th, and 10th recall
```

### Test 5C: Post-recall weight check

```
inspect_node(node_name="Maya Chen", graph_name=<name>)
→ Record: all edge weights after 10 recalls
→ Compare to Test 5A baseline
→ Expected: Max weight ≤ 1.5 (ceiling)
→ Expected: Diminishing increments (not linear +0.05 each time)

inspect_node(node_name="DataForge", graph_name=<name>)
→ Record: edge weights (DataForge is in Maya's neighborhood, should see some reinforcement)
```

### Test 5D: Non-traversed edge decay check

Run a query on a DIFFERENT topic to trigger micro-decay on Maya's edges:

```
recall(query="What CI/CD tools does Leo Park use?", limit=5)
→ Run 5 times

inspect_node(node_name="Maya Chen", graph_name=<name>)
→ Record: edge weights — should show slight decay from micro-decay (probabilistic)
→ At minimum: weights should NOT have increased
```

---

## Verification Checklist

- [ ] **5A**: Baseline weights recorded
- [ ] **5B**: 10 recalls completed, scores show diminishing returns
- [ ] **5C**: Max edge weight ≤ 1.5 after 10 recalls
- [ ] **5C**: Weight increases diminish (not constant +0.05)
- [ ] **5D**: Non-traversed edges did not increase (may have slightly decayed)
- [ ] No edge weight exceeds 1.5 ceiling anywhere in the graph

---

## Results

[Fill in during execution]

### Test 5A: Baseline Weights
| Edge (source → target) | Type | Weight |
|------------------------|------|--------|

### Test 5B: Recall Score Progression
| Recall # | Top Score | Notes |
|----------|-----------|-------|
| 1 | | |
| 5 | | |
| 10 | | |

### Test 5C: Post-Recall Weights
| Edge (source → target) | Baseline | After 10x | Delta | ≤1.5? |
|------------------------|----------|-----------|-------|-------|

### Test 5D: Micro-Decay Check
| Edge | Before Leo queries | After 5x Leo queries | Changed? |
|------|--------------------|---------------------|----------|

**Max weight observed anywhere**:
**Verdict**: PASS / FAIL
