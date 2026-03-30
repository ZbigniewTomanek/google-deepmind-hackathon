# Stage 2: Content Updates

**Goal**: Verify that node content actually updates when new information supersedes old (Plan 15 Issue #1: content never updates).

**Dependencies**: Stage 1 (baseline knowledge in graph)

---

## What Plan 15 Found

> Alice stays on "billing team" despite 2 updates saying "auth team".
> Root cause: COALESCE(NULL, old_content) preserves stale values;
> librarian doesn't provide descriptions for existing entities.

## What Plan 16 Fixed

- Stage 1: Librarian prompt now requires descriptions for ALL entities
- Stage 1: Pipeline fallback uses extractor description if librarian returns null
- Stage 3: Tool-driven curation with `create_or_update_node` always provides content

---

## Experiment Design

### Test 2A: Team change (direct parallel to Plan 15's Alice test)

```
remember(
  text="Maya Chen has been promoted from tech lead to Engineering Director of Team Atlas as of March 25, 2026. She now oversees 3 teams including Atlas, Beacon, and Compass. Her distributed systems background is key to the new platform strategy.",
  importance=0.9
)
```

**Verification:**
```
inspect_node(node_name="Maya Chen", graph_name=<name>)
→ Expected: Content mentions "Engineering Director" (not just "tech lead")
→ Expected: Single node (no duplicate "Maya Chen")

browse_nodes(graph_name=<name>, type_name="Person", limit=10)
→ Expected: Exactly 1 "Maya Chen" node

recall(query="What is Maya Chen's current role?", limit=5)
→ Expected: Top result mentions "Engineering Director", not "tech lead" only
```

### Test 2B: Technology change

```
remember(
  text="Team Atlas decided to migrate DataForge from Kafka to Apache Pulsar for stream ingestion. The decision was made on March 20, 2026, driven by Pulsar's native multi-tenancy support and better message replay capabilities. Kafka is being phased out by April 30.",
  importance=0.8
)
```

**Verification:**
```
inspect_node(node_name="DataForge", graph_name=<name>)
→ Expected: Content reflects Pulsar migration (not only Kafka)

recall(query="What streaming technology does DataForge use?", limit=5)
→ Expected: Top results mention Pulsar as current, Kafka as legacy/phased out

inspect_node(node_name="Apache Pulsar", graph_name=<name>)
→ Expected: Node exists with content about multi-tenancy, message replay
```

### Test 2C: Deadline update

```
remember(
  text="The DataForge launch date has been pushed from June 15 to August 1, 2026 due to the Kafka-to-Pulsar migration. The team needs extra time for performance benchmarking on the new stack.",
  importance=0.7
)
```

**Verification:**
```
recall(query="When is DataForge launching?", limit=5)
→ Expected: Top result mentions August 1, not June 15 as current

inspect_node(node_name="DataForge", graph_name=<name>)
→ Expected: Content reflects August 1 date
```

---

## Verification Checklist

- [ ] **2A**: Maya Chen content shows "Engineering Director" (not stale "tech lead" only)
- [ ] **2A**: Exactly 1 "Maya Chen" node (no duplicates from re-extraction)
- [ ] **2B**: DataForge content reflects Pulsar migration
- [ ] **2B**: Apache Pulsar node exists in graph
- [ ] **2B**: Recall for streaming tech returns Pulsar, not just Kafka
- [ ] **2C**: Launch date recall returns August 1 (not June 15) as current
- [ ] No stale content persisting after updates (core Plan 15 Issue #1 fix)

---

## Results

[Fill in during execution]

### Test 2A: Maya Chen Role Update
- Node count for "Maya Chen":
- Content after update:
- Recall ranking:
- **Verdict**: PASS / FAIL

### Test 2B: Kafka → Pulsar Migration
- DataForge content:
- Pulsar node exists:
- Recall ranking:
- **Verdict**: PASS / FAIL

### Test 2C: Deadline Shift
- Recall result:
- DataForge content:
- **Verdict**: PASS / FAIL
