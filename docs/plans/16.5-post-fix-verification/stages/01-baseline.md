# Stage 1: Baseline — Fresh Graph

**Goal**: Establish initial knowledge about the Atlas team and verify basic remember/recall/discover works.

**Dependencies**: None (first stage, clean server)

---

## Experiment Design

Store 4 facts about the Atlas team that set up data for all subsequent stages.
These facts deliberately include entity types and relationships that will be
tested for stability in later stages.

### Step 1: Verify clean state

```
discover_graphs()
→ Expected: empty list or no graph for this agent
```

### Step 2: Store initial facts

Store these 4 episodes in sequence, waiting briefly between each:

**Fact 1** (team structure):
```
remember(
  text="Maya Chen is the tech lead of Team Atlas. She has 8 years of experience in distributed systems. The team is building DataForge, a real-time data pipeline platform.",
  importance=0.8
)
```

**Fact 2** (team members):
```
remember(
  text="Jonas Berg is a backend engineer on Team Atlas, reporting to Maya Chen. He specializes in Kafka and stream processing. Priya Sharma is the ML engineer on Team Atlas, focusing on anomaly detection models.",
  importance=0.7
)
```

**Fact 3** (architecture):
```
remember(
  text="DataForge uses Apache Kafka for stream ingestion, PostgreSQL for metadata, and Redis for caching. The team decided to use Kubernetes for orchestration after evaluating Nomad and ECS. Target launch date is June 15, 2026.",
  importance=0.8
)
```

**Fact 4** (current work):
```
remember(
  text="Leo Park joined Team Atlas as DevOps engineer on March 1, 2026. He is setting up the CI/CD pipeline using GitHub Actions. The team uses a monorepo structure with Bazel for builds.",
  importance=0.6
)
```

### Step 3: Verify recall works

```
recall(query="Who is on Team Atlas and what do they do?", limit=10)
→ Expected: Results mentioning Maya, Jonas, Priya, Leo with their roles
```

### Step 4: Discover graph structure

```
discover_graphs()
→ Expected: One graph with nodes and edges created from the 4 episodes

discover_ontology(graph_name=<from above>)
→ Expected: Node types (Person, Team, Software/Technology, etc.) and edge types

browse_nodes(graph_name=<from above>, limit=30)
→ Expected: Nodes for Maya, Jonas, Priya, Leo, Team Atlas, DataForge, Kafka, etc.
```

### Step 5: Inspect key entities

```
inspect_node(node_name="Maya Chen", graph_name=<name>)
→ Expected: Content mentions "tech lead", "8 years", "distributed systems"
→ Record: edges, types, neighbor count

inspect_node(node_name="DataForge", graph_name=<name>)
→ Expected: Content mentions "real-time data pipeline platform"
→ Record: edges, types, connected technologies
```

---

## Verification Checklist

- [ ] `discover_graphs()` shows a graph with >0 nodes and edges
- [ ] `recall()` returns results mentioning all 4 team members
- [ ] Key nodes exist: Maya Chen, Jonas Berg, Priya Sharma, Leo Park, DataForge, Team Atlas
- [ ] Node content is populated (not null/empty)
- [ ] Edge types are reasonable (MEMBER_OF, WORKS_ON, USES, etc.)
- [ ] No obvious duplicates in browse_nodes output

---

## Results

[Fill in during execution — raw MCP output + observations]

### Graph Stats
- Graphs:
- Nodes:
- Edges:
- Episodes:

### Node Inventory
| Node Name | Type | Content Summary | Edges |
|-----------|------|-----------------|-------|

### Observations
