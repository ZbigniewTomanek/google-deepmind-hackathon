# How It Works

NeoCortex exposes 3 MCP tools to AI agents: `remember`, `recall`, and `discover`. Behind those tools, a multi-agent extraction pipeline and cognitive scoring system turn raw text into a structured, self-organizing knowledge graph.

## The 3 Tools

| Tool | What it does |
|------|-------------|
| `remember(text, context?, target_graph?, importance?)` | Stores text as an episode. Extraction pipeline runs asynchronously to enrich the graph. |
| `recall(query, limit?)` | Hybrid search across episodes and graph nodes. Returns ranked results with graph context. |
| `discover_graphs()` / `discover_ontology(graph)` / `inspect_node(name)` | Navigate the knowledge graph: list graphs, browse ontology, inspect nodes and neighborhoods. |

Agents never touch the graph directly. They remember and recall in natural language.

## From Text to Knowledge Graph

When you call `remember("The team decided to use Kafka instead of RabbitMQ for partition ordering guarantees")`, this happens:

```
1. Episode stored immediately (searchable via recall right away)
2. Embedding computed (768-dim Gemini vector)
3. Extraction job enqueued (async, doesn't block the agent)
4. Domain routing job enqueued (classifies into shared domain graphs)
```

The extraction pipeline then processes the episode in the background:

### Stage 1: Ontology Agent

Analyzes the text against the existing ontology and proposes new entity/relationship types if needed. For example, it might propose `Technology` and `Decision` node types, and a `CHOSEN_OVER` edge type.

The key insight: **ontologies are not pre-designed** — they emerge organically as new information arrives. The agent strongly prefers reusing existing types over creating new ones, keeping the schema coherent.

### Stage 2: Extractor Agent

Extracts structured facts aligned to the (now updated) ontology:
- **Entities**: `Kafka` (Technology), `RabbitMQ` (Technology), `partition ordering` (Concept)
- **Relations**: `Kafka CHOSEN_OVER RabbitMQ`, `Kafka PROVIDES partition ordering`
- **Properties**: importance scores, descriptive attributes

The extractor can also mark entities as **superseding** older ones — corrections and updates don't overwrite, they create a versioned chain.

### Stage 3: Librarian Agent

The final curator. It deduplicates entities (is "Apache Kafka" the same as "Kafka"?), normalizes names, merges properties, and persists everything to the graph using a set of curation tools:

- `create_node` / `update_node` / `archive_node`
- `create_edge` / `remove_edge`

The Librarian has read access to existing graph state, so it makes informed decisions about merging vs. creating new entities.

### Result

A structured knowledge graph that grows with every `remember` call. No manual schema design. No ETL pipeline to maintain.

## How Recall Works

`recall("Why did we choose Kafka?")` triggers a multi-phase scoring pipeline:

### Phase 1: Candidate retrieval

Searches across episodes and graph nodes using two complementary methods:
- **Semantic search** — pgvector cosine similarity against the query embedding
- **Full-text search** — PostgreSQL tsvector/BM25 keyword matching

### Phase 2: Hybrid scoring

Each candidate receives a weighted score from 5 signals:

| Signal | What it measures | Default weight |
|--------|-----------------|----------------|
| Vector similarity | Semantic closeness to the query | 0.30 |
| Text rank | Keyword relevance (BM25) | 0.20 |
| Recency | How recent the memory is (exponential decay, 7-day half-life) | 0.15 |
| ACT-R activation | Access frequency and recency combined — frequently recalled memories stay accessible, unused ones fade | 0.20 |
| Importance | User-provided hints (0.0-1.0) set via the `importance` parameter | 0.15 |

**Graceful degradation**: When a signal is unavailable (no embedding, no text match, new node with no access history), its weight is redistributed proportionally to the remaining signals. The system never fails — it just uses what's available.

All weights are configurable via environment variables (`NEOCORTEX_RECALL_WEIGHT_*`).

### Phase 3: Graph traversal + spreading activation

Top-scoring nodes seed a graph traversal (configurable depth, default 2 hops). Energy propagates from matched nodes through edges, decaying with distance:

```
Kafka (matched, energy=1.0)
  ─CHOSEN_OVER→ RabbitMQ (energy=0.6)
  ─PROVIDES→ partition ordering (energy=0.6)
    ─ENABLES→ event streaming (energy=0.36)
```

Indirectly related knowledge gets a scoring bonus even if it didn't match the query directly.

### Phase 4: Reinforcement + maintenance

After returning results, recall performs maintenance:
- **Edge reinforcement**: Traversed edges get a weight increase (Hebbian learning — "neurons that fire together wire together")
- **Edge decay**: Non-traversed recent edges get a micro-decay (stochastic, 25% of calls)
- **Soft forgetting**: Low-activation, low-importance nodes are soft-deleted (5% of calls)

This creates a self-maintaining graph where useful knowledge strengthens and irrelevant knowledge naturally fades.

### Phase 5: Diversity reranking

[Maximal Marginal Relevance (MMR)](https://en.wikipedia.org/wiki/Maximal_marginal_relevance) reranks the final results to balance relevance with diversity — you get the most relevant results without redundant near-duplicates.

## How Updates Work

NeoCortex uses a **supersession model** rather than overwrites:

- When new information contradicts old information, the Extractor marks the new entity with a `CORRECTS` or `SUPERSEDES` temporal signal
- The old entity is penalized in scoring (multiplied by `recall_superseded_penalty`)
- The new entity is boosted (multiplied by `recall_superseding_boost`)
- Both remain in the graph — you can trace the history of a fact

This means recall naturally returns the most current version of a fact while preserving the full history.

## ACT-R Activation Model

The activation scoring is based on [ACT-R](https://en.wikipedia.org/wiki/ACT-R), a cognitive architecture from psychology:

```
Activation = ln(n^a + 1) - d * ln(T + 1)
```

Where:
- `n` = number of times the memory has been accessed
- `a` = dampening exponent (0.5 by default — square root dampening prevents runaway activation)
- `d` = decay rate (0.5 by default)
- `T` = hours since last access

This models biological memory: recently and frequently accessed memories are easy to retrieve. Unused memories decay but never fully disappear (they can be revived by access).
