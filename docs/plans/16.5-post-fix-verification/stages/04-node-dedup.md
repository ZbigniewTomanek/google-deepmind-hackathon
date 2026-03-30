# Stage 4: Node Dedup & Type Drift

**Goal**: Verify that the same entity isn't duplicated as multiple nodes when extraction assigns different types (Plan 15 Issue #3 & #5).

**Dependencies**: Stage 3 (entities have been extracted multiple times by now)

---

## What Plan 15 Found

> "WNP Pruning Algorithm" existed as 2 nodes (id=53 and id=56) because extracted
> with different type_ids. UPSERT key was (name, type_id), so type change = new node.
> Same entity: Person → Algorithm → Metric → Document → Fact across runs.

## What Plan 16 Fixed

- Stage 3: Librarian uses `find_node_by_name` to check for existing node before creating
- Stage 4: Adapter name-primary dedup: looks up by name first, then checks `_types_are_merge_safe()`
- Stage 4: Homonym detection: Drug/Neurotransmitter, Person/Organization kept separate

---

## Experiment Design

### Test 4A: Count key entities — should be exactly 1 per real-world entity

By this point, Maya Chen has been mentioned in Stages 1, 2, 3 — extracted at least 4 times.
Jonas Berg: Stages 1, 3. Priya Sharma: Stages 1, 3. DataForge: Stages 1, 2, 3.

```
browse_nodes(graph_name=<name>, limit=50)
→ Count: How many nodes named "Maya Chen" (or close variants)?
→ Count: How many nodes named "Jonas Berg"?
→ Count: How many nodes named "Priya Sharma"?
→ Count: How many nodes named "DataForge"?
→ Count: How many nodes named "Team Atlas"?
→ Expected: Exactly 1 of each
```

### Test 4B: Provoke type drift with ambiguous entity

Store a fact where an entity could reasonably be typed differently:

```
remember(
  text="DataForge is being evaluated for SOC 2 compliance certification. The DataForge platform scored 87/100 on the preliminary security audit conducted by ExternalAudit Corp on March 15, 2026.",
  importance=0.7
)
```

"DataForge" was previously typed as Software/Platform. This context might cause
the LLM to re-type it as "Product" or "Service". Should still merge into existing node.

**Verification:**
```
browse_nodes(graph_name=<name>, limit=50)
→ Count "DataForge" nodes: should still be 1
→ If 2+: type drift bug is NOT fixed

inspect_node(node_name="DataForge", graph_name=<name>)
→ Content should include both pipeline info AND compliance info
→ Type should be consistent (whatever was first assigned)
```

### Test 4C: Legitimate homonym — should NOT merge

```
remember(
  text="Atlas is also the name of our company's internal documentation wiki. Atlas Wiki was launched in 2024 and hosts all engineering specs. It should not be confused with Team Atlas, the data pipeline team.",
  importance=0.5
)
```

**Verification:**
```
browse_nodes(graph_name=<name>, limit=50)
→ Look for: "Team Atlas" and "Atlas" / "Atlas Wiki"
→ Expected: These should be SEPARATE nodes (different entities)
→ If merged: false positive — homonym detection failed
```

---

## Verification Checklist

- [ ] **4A**: Exactly 1 "Maya Chen" node (despite 4+ extractions)
- [ ] **4A**: Exactly 1 "Jonas Berg" node
- [ ] **4A**: Exactly 1 "Priya Sharma" node
- [ ] **4A**: Exactly 1 "DataForge" node
- [ ] **4A**: Exactly 1 "Team Atlas" node
- [ ] **4B**: DataForge still 1 node after compliance context (type drift handled)
- [ ] **4B**: DataForge content includes both pipeline and compliance info
- [ ] **4C**: Atlas Wiki and Team Atlas are separate nodes (homonym preserved)

---

## Results

[Fill in during execution]

### Test 4A: Entity Uniqueness Audit
| Entity | Expected | Actual Count | Verdict |
|--------|----------|-------------|---------|
| Maya Chen | 1 | | |
| Jonas Berg | 1 | | |
| Priya Sharma | 1 | | |
| DataForge | 1 | | |
| Team Atlas | 1 | | |

### Test 4B: Type Drift Provocation
- DataForge node count after compliance fact:
- Content includes compliance info:
- **Verdict**: PASS / FAIL

### Test 4C: Homonym Preservation
- "Team Atlas" separate from "Atlas Wiki":
- **Verdict**: PASS / FAIL
