# Stage 6: Complex Knowledge Evolution

**Goal**: Simulate 2 weeks of realistic knowledge evolution with corrections, reversals, and accumulation. Holistic test that all Plan 16 fixes work together under realistic conditions.

**Dependencies**: Stage 5 (weight management verified; graph is mature)

---

## Experiment Design

### Round 1: Strategic reversal

```
remember(
  text="After benchmarking Apache Pulsar for 2 weeks, Team Atlas decided to revert back to Apache Kafka. Pulsar's multi-tenancy was not worth the operational complexity increase. The migration is cancelled as of March 28, 2026. DataForge will continue using Kafka for stream ingestion.",
  importance=0.9
)
```

**Verification:**
```
recall(query="What streaming platform does DataForge use?", limit=5)
→ Expected: Top result clearly states Kafka (reverted from Pulsar)
→ Expected: Pulsar context available but marked as evaluated-and-rejected

inspect_node(node_name="DataForge", graph_name=<name>)
→ Expected: Content reflects Kafka as current, not Pulsar
```

### Round 2: Team restructuring

```
remember(
  text="Jonas Berg left Team Atlas on March 27, 2026 to join the Security team as a senior engineer. His replacement on Atlas is Sarah Kim, a backend engineer who previously worked on the Payments team. Sarah Kim will take over the stream processing layer from Jonas.",
  importance=0.8
)
```

**Verification:**
```
recall(query="Who works on the stream processing layer of DataForge?", limit=5)
→ Expected: Sarah Kim mentioned as current, Jonas as previous

inspect_node(node_name="Jonas Berg", graph_name=<name>)
→ Expected: Content updated to reflect Security team move

browse_nodes(graph_name=<name>, type_name="Person", limit=15)
→ Expected: Sarah Kim appears as new node; Jonas Berg still exists (1 node)
```

### Round 3: Experimental results correction

```
remember(
  text="Priya Sharma's anomaly detection model achieved 94.2% precision on the production dataset, correcting the earlier estimate of 87% from the staging environment. The model uses an ensemble of isolation forests and autoencoders. Latency is 12ms per inference at p99.",
  importance=0.8
)
```

**Verification:**
```
recall(query="How accurate is the anomaly detection model?", limit=5)
→ Expected: 94.2% precision (production), context about staging being lower

inspect_node(node_name="Priya Sharma", graph_name=<name>)
→ Expected: Content reflects latest model performance
```

### Round 4: Architecture evolution

```
remember(
  text="Team Atlas added Apache Flink as a second processing engine alongside Kafka Streams. Flink handles the complex event processing (CEP) workloads while Kafka Streams handles simple transformations. Leo Park configured both to run on the same Kubernetes cluster. The total DataForge architecture is now: Kafka (ingestion) → Flink + Kafka Streams (processing) → PostgreSQL + Redis (storage/cache).",
  importance=0.8
)
```

**Verification:**
```
recall(query="What is DataForge's full architecture?", limit=5)
→ Expected: Complete stack mentioned (Kafka, Flink, Kafka Streams, PG, Redis)
→ Expected: No mention of Pulsar as current

discover_ontology(graph_name=<name>)
→ Record: total node types and edge types
→ Expected: Types still reasonable (not exploding)

browse_nodes(graph_name=<name>, limit=50)
→ Record: total node count, look for duplicates
```

---

## Verification Checklist

- [ ] **Round 1**: Kafka reversion reflected in recall and node content
- [ ] **Round 1**: Pulsar not presented as current technology
- [ ] **Round 2**: Sarah Kim exists; Jonas Berg updated (not duplicated)
- [ ] **Round 2**: Stream processing recall returns Sarah (current), not just Jonas
- [ ] **Round 3**: 94.2% precision in recall (not stale 87%)
- [ ] **Round 4**: Full architecture recalled correctly
- [ ] **Overall**: No duplicate nodes created during this stage
- [ ] **Overall**: Edge types remain stable (no explosion)

---

## Results

[Fill in during execution]

### Round 1: Kafka Reversion
- Recall top result:
- DataForge content:
- **Verdict**: PASS / FAIL

### Round 2: Team Change
- Jonas Berg content updated:
- Sarah Kim node created:
- Stream processing recall:
- **Verdict**: PASS / FAIL

### Round 3: Precision Correction
- Recall result:
- **Verdict**: PASS / FAIL

### Round 4: Architecture Evolution
- Full stack in recall:
- Node count:
- Edge type count:
- Duplicates found:
- **Verdict**: PASS / FAIL
