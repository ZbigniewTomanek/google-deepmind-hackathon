# Architecture

## System Overview

NeoCortex is structured as a layered system: MCP tools at the top provide a simple agent-facing API, while a bulk ingestion REST API provides a secondary data-loading path. Both share the same PostgreSQL backend for storage, search, and isolation.

```
                     +------------------+
                     |   AI Agents      |  (Pydantic AI + Gemini, Claude, etc.)
                     +--------+---------+
                              |  MCP protocol (SSE / streamable-http)
                     +--------v---------+       +------------------------+
                     |   FastMCP Server |       |  Ingestion API (:8001) |
                     |  remember/recall |       |  POST /ingest/text     |
                     |  /discover       |       |  POST /ingest/document |
                     |  :8000           |       |  POST /ingest/events   |
                     +--------+---------+       +----------+-------------+
                              |                            |
                              +------- shared stack -------+
                              |                            |
              +-------+-------+-------+-------+            |
              |               |               |            |
     +--------v------+  +----v------+  +------v--------+  |
     | GraphRouter   |  | AuthLayer |  | SchemaManager |  |
     | (heuristics)  |  | (tokens)  |  | (lifecycle)   |  |
     +--------+------+  +----+------+  +------+--------+  |
              |               |               |            |
     +--------v---------------v---------------v------+-----+
     |              PostgreSQL 16                     |
     |  pgvector (semantic) + tsvector (BM25)         |
     |  multi-schema isolation + RLS                  |
     +------------------------------------------------+
```

Both services use `create_services()` from `services.py` for initialization, sharing the same `MemoryRepository` protocol. The ingestion API stores raw episodes and enqueues extraction jobs for automatic knowledge graph enrichment.

A **Developer TUI** (`python -m neocortex.tui`) provides an interactive terminal interface for testing. It connects to the MCP server via `fastmcp.Client` with streamable-HTTP transport and supports all three tools (remember, recall, discover).

## MCP Tools

Agents interact with 3 high-level tools. They never operate on the graph directly.

| Tool | Input | Description |
|------|-------|-------------|
| `remember` | `text`, `context?` | Store natural language content as an episode. Internal agents asynchronously extract facts to the knowledge graph |
| `recall` | `query`, `limit?` | Hybrid search (semantic + lexical + graph) returns ranked results with provenance |
| `discover` | `query?` | Returns ontology — entity types, relationship types, graph stats. Optionally filtered |

## Ingestion API

A standalone FastAPI application for bulk data loading. Uses the same auth (bearer tokens) and storage (`MemoryRepository`) as the MCP server.

| Endpoint | Input | Description |
|----------|-------|-------------|
| `POST /ingest/text` | JSON `{text, metadata?}` | Store a text string as a single episode |
| `POST /ingest/document` | Multipart file upload | Store file content as a single episode. Accepted types: `text/plain`, `application/json`, `text/markdown`, `text/csv`. Max 10 MB |
| `POST /ingest/events` | JSON `{events[], metadata?}` | Store each event as a separate episode |

All endpoints return `IngestionResult {status, episodes_created, message}`. Processing is handled by an `IngestionProcessor` protocol — currently `StubProcessor` (raw storage), designed to be replaced by an extraction pipeline.

## Data Model

Knowledge graph represented via normalized relational tables in PostgreSQL.

### Core Tables (per graph schema)

| Table | Purpose |
|-------|---------|
| `node_type` | Ontology: what types of entities exist (e.g., Person, Concept, Document) |
| `edge_type` | Ontology: what types of relationships exist (e.g., MENTIONS, CAUSED_BY) |
| `node` | Entities/memories with content, JSONB properties, 768-dim embedding, and auto-generated tsvector |
| `edge` | Relationships between nodes with type, weight, and properties |
| `episode` | Episodic memory log (append-only, per agent) |

### Search Capabilities

| Type | Mechanism |
|------|-----------|
| Semantic | pgvector cosine similarity on `node.embedding` (768 dimensions) |
| Lexical | tsvector + GIN index for full-text search (BM25-like ranking) |
| Graph traversal | JOINs on `edge` table with neighbor expansion |
| Hybrid recall | Weighted combination: `0.4 * vector_sim + 0.35 * ts_rank + 0.25 * recency_decay` (configurable, auto-redistributes when signals are missing) |

## Embedding Service

`EmbeddingService` (`embedding_service.py`) generates 768-dimensional normalized embeddings via the Gemini API. It is instantiated in `create_services()` and available to tools via `ctx.lifespan_context["embeddings"]`.

| Aspect | Detail |
|--------|--------|
| Model | Configurable via `NEOCORTEX_EMBEDDING_MODEL` (default: `gemini-embedding-001`) |
| Dimensions | 768 (MRL truncation from 3072, 75% storage savings) |
| Normalization | L2 normalization after truncation per Gemini best practices |
| Fallback | When `GOOGLE_API_KEY` is unset, `embed()` returns `None`; recall degrades to text-only |
| Integration | `remember` generates and stores embedding per episode; `recall` embeds the query for hybrid scoring |

## Hybrid Recall Scoring

`scoring.py` implements the scoring pipeline used by `recall`. Each result receives a weighted combination of up to three signals:

| Signal | Source | Weight (default) |
|--------|--------|-------------------|
| Vector similarity | `1 - (embedding <=> query_embedding)` via pgvector | 0.40 |
| Text rank | `ts_rank(tsv, plainto_tsquery())` via tsvector | 0.35 |
| Recency | Exponential decay: `2^(-hours_ago / half_life)`, half-life = 7 days | 0.25 |

When a signal is unavailable (e.g., no embedding exists for a result, or episodes lack tsvector), its weight is **redistributed proportionally** to the remaining signals. This means the system degrades gracefully: text-only when no embeddings exist, vector+recency for episodes (which lack tsvector), and so on.

All weights and the recency half-life are configurable via `NEOCORTEX_RECALL_WEIGHT_*` environment variables.

## Multi-Graph Architecture

Each agent gets isolated PostgreSQL schemas for their data. A shared schema enables cross-agent knowledge.

### Schema Naming

```
ncx_{agent_id}__{purpose}       -- per-agent graphs (double underscore separator)
ncx_shared__{purpose}           -- shared graphs

Examples:
  ncx_alice__personal
  ncx_alice__research
  ncx_shared__knowledge
```

### Key Components

| Component | Role |
|-----------|------|
| `SchemaManager` | Creates, drops, lists graph schemas. Provisions tables from a SQL template. Auto-creates default personal graph per agent |
| `GraphRouter` | Heuristic layer that decides which schema(s) to target for each operation. Store → personal graph. Recall → fan-out across personal + shared. Discover → aggregate all accessible |
| `GraphServiceAdapter` | Implements `MemoryRepository` protocol using router-driven multi-schema queries with async fan-out |
| `graph_registry` | Table in `public` schema tracking all created graphs |

### Isolation Model

| Schema Type | RLS | Role Scoping | Use Case |
|-------------|-----|-------------|----------|
| Per-agent (`ncx_alice__personal`) | No | search_path only | Private agent memory |
| Shared (`ncx_shared__knowledge`) | Yes | search_path + SET ROLE | Cross-agent knowledge base |

## Authentication

Three auth modes, configurable via `NEOCORTEX_AUTH_MODE`:

| Mode | Description |
|------|-------------|
| `none` | No authentication (development) |
| `dev_token` | Bearer tokens mapped to agent IDs via `dev_tokens.json` |
| `google_oauth` | Google OAuth via FastMCP OAuthProxy |

## Extraction Pipeline

The 3-agent extraction pipeline runs behind `remember` and ingestion, automatically enriching raw text into the knowledge graph via async background jobs:

```
Episode (raw text)
    │
    ▼
Ontology Agent → proposes schema extensions
    │
    ▼
Extraction Agent → extracts facts aligned to ontology
    │
    ▼
Librarian Agent → deduplicates, normalizes, persists
```

The pipeline runs against PostgreSQL via the Procrastinate job queue. A standalone playground (`src/pydantic_agents_playground/`) provides an isolated SQLite-based version for experimentation.
