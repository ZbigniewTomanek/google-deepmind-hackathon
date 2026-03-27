# NeoCortex: Agent Memory System

MCP server providing structured long-term memory for AI agents. Knowledge graph on PostgreSQL with semantic search (pgvector), full-text search (tsvector/BM25), and graph traversal — all behind 3 simple MCP tools.

```
                     +------------------+
                     |   AI Agents      |  (Pydantic AI + Gemini, Claude, etc.)
                     +--------+---------+
                              |  MCP protocol
                     +--------v---------+
                     |   FastMCP Server |
                     |  remember/recall |
                     |  /discover       |
                     +--------+---------+
                              |
              +-------+-------+-------+
              |               |       |
     +--------v------+ +-----v-----+ +------v--------+
     | GraphRouter   | | AuthLayer | | SchemaManager |
     | (heuristics)  | | (tokens)  | | (lifecycle)   |
     +-------+-------+ +-----+-----+ +------+--------+
             |                |              |
     +-------v----------------v--------------v--------+
     |              PostgreSQL 16                      |
     |  pgvector (semantic) + tsvector (BM25)          |
     |  multi-schema isolation + RLS                   |
     +--------------------------------------------------+
```

## MCP Tools

Agents see 3 tools. They never operate on the graph directly.

| Tool | Input | Description |
|------|-------|-------------|
| `remember` | `text`, `context?` | Store natural language content as an episode. Internal agents extract facts to the graph |
| `recall` | `query`, `limit?` | Hybrid search (semantic + lexical + graph) returns ranked results with provenance |
| `discover` | `query?` | Returns ontology — entity types, relationships, graph statistics |

## Quick Start

```bash
# Start PostgreSQL
docker compose up -d postgres

# Install deps
uv sync

# Run MCP server (mock DB, no Docker needed)
NEOCORTEX_MOCK_DB=true uv run python -m neocortex

# Run MCP server (with PostgreSQL)
NEOCORTEX_AUTH_MODE=dev_token \
NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
uv run python -m neocortex

# Run tests
uv run pytest tests/ -v

# Run TUI (connect to running MCP server)
uv run python -m neocortex.tui --url http://localhost:8000 --token dev-token-neocortex
```

## Implementation Status

All planned components are implemented and tested. The system is functional end-to-end.

### Core MCP Server — Complete

| Component | Status | Description |
|-----------|--------|-------------|
| FastMCP server | Done | Server factory with async lifespan, health endpoint |
| `remember` tool | Done | Stores episodes in agent's personal graph schema |
| `recall` tool | Done | Parallel fan-out across agent + shared schemas, hybrid ranking |
| `discover` tool | Done | Aggregates ontology and stats across accessible graphs |
| Tool I/O schemas | Done | Pydantic models for all tool inputs/outputs |

### PostgreSQL Storage Layer — Complete

| Component | Status | Description |
|-----------|--------|-------------|
| Docker Compose | Done | pgvector/pg16 image with auto-applied migrations |
| SQL migrations | Done | 6 init migrations + 1 template for dynamic schema provisioning |
| `PostgresService` | Done | asyncpg connection pool, health checks, migration runner |
| `GraphService` | Done | Full CRUD for node types, edge types, nodes, edges, episodes |
| Vector search | Done | pgvector cosine similarity (768-dim embeddings) |
| Full-text search | Done | tsvector + GIN index with ts_rank scoring |
| Graph-aware search | Done | Neighbor expansion via edge JOINs |

### Multi-Graph Architecture — Complete

| Component | Status | Description |
|-----------|--------|-------------|
| `SchemaManager` | Done | Create/drop/list isolated graph schemas from SQL template |
| `GraphRouter` | Done | Heuristic routing: store → personal, recall → fan-out, discover → aggregate |
| `GraphServiceAdapter` | Done | Protocol-based adapter with multi-schema async fan-out |
| `graph_registry` table | Done | Tracks all graphs in `public` schema |
| Schema-scoped connections | Done | `SET search_path` for isolation, `SET ROLE` for shared graphs |
| Auto-provisioning | Done | Personal graph created on first agent write; shared graph at startup |

### Authentication & Authorization — Complete

| Component | Status | Description |
|-----------|--------|-------------|
| Dev token auth | Done | Multi-token JSON file mapping tokens → agent IDs |
| Google OAuth | Done | FastMCP OAuthProxy integration |
| Row-Level Security | Done | RLS policies on shared graph schemas only |
| PG role mapping | Done | OAuth subject → PostgreSQL role with scoped connections |

### Embedding Service & Hybrid Recall — Complete

| Component | Status | Description |
|-----------|--------|-------------|
| `EmbeddingService` | Done | Gemini embedding wrapper (768-dim MRL, normalized), graceful `None` fallback when `GOOGLE_API_KEY` is unset |
| Hybrid recall scoring | Done | Weighted combination of vector similarity + text rank + recency decay with automatic weight redistribution |
| `scoring.py` | Done | Configurable weights (`recall_weight_vector`, `recall_weight_text`, `recall_weight_recency`) and recency half-life |
| Wired into `remember` | Done | Embeddings generated and stored on every `remember` call |
| Wired into `recall` | Done | Query embedding computed and passed to hybrid recall path |

### Developer TUI — Complete

| Component | Status | Description |
|-----------|--------|-------------|
| Textual app | Done | Three modes: Remember, Recall, Discover with keyboard shortcuts |
| MCP client | Done | `fastmcp.Client` with streamable-HTTP transport |
| CLI entry point | Done | `python -m neocortex.tui --url URL --token TOKEN` |

### Testing — Complete

| Area | Description |
|------|-------------|
| MCP tools | Tool execution, schema validation, server lifecycle |
| Storage | Graph CRUD, search, connection pooling, health checks |
| Multi-graph | Schema manager, router, adapter fan-out, isolation |
| Auth | Dev tokens, role mapping, RLS enforcement |
| Embeddings | Normalization, graceful fallback, mocked API, batch operations |
| Scoring | Recency decay, hybrid scoring, weight redistribution |
| E2E | MCP multi-agent (`scripts/e2e_mcp_test.py`), ingestion (`scripts/e2e_ingestion_test.py`), hybrid recall (`scripts/e2e_hybrid_recall_test.py`), embeddings (`scripts/e2e_embedding_test.py`) |

### Extraction Pipeline Integration — Complete

The 3-agent extraction pipeline is fully integrated into the MCP server hot path. Ingested text is automatically enriched into the knowledge graph via async background jobs.

| Component | Status | Description |
|-----------|--------|-------------|
| Procrastinate job queue | Done | PostgreSQL-native async job queue for background extraction |
| Extraction pipeline | Done | Ontology → Extractor → Librarian agents (Gemini 2.5 Flash) |
| `remember` integration | Done | `remember` stores episode + enqueues extraction job |
| Ingestion API integration | Done | `POST /ingest/text` stores episode + enqueues extraction job |
| Graph persistence | Done | Nodes with embeddings + edges upserted into agent's schema |
| Graph-aware recall | Done | Node search + configurable-depth edge traversal in `recall` results |
| Structured logging | Done | `setup_logging()` with rotating service logs + JSON audit trail (`log/agent_actions.log`) |
| E2E validation | Done | [Validation report](docs/reports/00-extraction-pipeline-e2e-validation.md) — 258 nodes, 268 edges from 10-episode medical corpus |

### Ingestion API — Complete

| Component | Status | Description |
|-----------|--------|-------------|
| FastAPI app | Done | Bulk-ingestion REST API on port 8001 |
| `POST /ingest/text` | Done | Store text episodes with automatic extraction |
| `POST /ingest/document` | Done | Document ingestion endpoint |
| `POST /ingest/events` | Done | Event batch ingestion endpoint |
| Seed corpus CLI | Done | `python -m neocortex.extraction.cli --ingest-corpus` for medical domain data |

### POC: Pydantic AI Agent Pipeline — Complete (Integrated)

Standalone proof-of-concept in `src/pydantic_agents_playground/`. The pipeline has been ported and integrated into the MCP server (see Extraction Pipeline Integration above).

| Agent | Role |
|-------|------|
| Ontology Agent | Proposes conservative schema extensions for new content |
| Extraction Agent | Extracts facts aligned to current ontology |
| Librarian Agent | Deduplicates, normalizes, and persists to storage |

```bash
# Offline (no API key)
uv run python -m pydantic_agents_playground --use-test-model --reset-db --run-demo

# Live with Gemini
GOOGLE_API_KEY=your_key uv run python -m pydantic_agents_playground --reset-db --run-demo
```

## Roadmap

| Item | Status | Description |
|------|--------|-------------|
| Advanced heuristics | Planned | Spreading activation, episodic consolidation, forgetting curve |
| Cross-agent knowledge transfer | Planned | Promote private nodes to shared graph with approval flow |

## Tech Stack

| Component | Technology |
|-----------|------------|
| LLM | Gemini (via Pydantic AI) |
| Embeddings | Gemini embedding model (768 dims) |
| Database | PostgreSQL 16 + pgvector + tsvector |
| MCP Server | FastMCP (Python) |
| Agent Framework | Pydantic AI |
| Data Access | asyncpg |
| Auth | FastMCP OAuthProxy + dev tokens |
| TUI | Textual + Click |
| Language | Python 3.13 |

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | System design, data model, multi-graph isolation, search capabilities |
| [Development Guide](docs/development.md) | Setup, configuration, running, testing, project layout |
| **Plans** | |
| [High-Level Plan](docs/plans/01-high-level-hackathon-plan.md) | Vision, data model, memory types, heuristics roadmap |
| [PostgreSQL Storage](docs/plans/02-postgres-storage-layer.md) | Storage layer implementation plan (all stages done) |
| [MCP Server Scaffold](docs/plans/03-mcp-server-scaffold.md) | Server, tools, auth implementation plan (all stages done) |
| [Multi-Graph Schemas](docs/plans/04-multi-graph-schemas.md) | Schema isolation architecture plan (all stages done) |
| [Embeddings, Hybrid Recall, TUI](docs/plans/06-embeddings-hybrid-recall-tui.md) | Embedding service, hybrid scoring, developer TUI (all stages done) |
| [Extraction Pipeline Integration](docs/plans/07-extraction-pipeline-integration.md) | 3-agent pipeline wired into MCP server (all stages done) |
| [Pydantic AI POC](docs/plans/00-pydantic-ai-bmw-ontology-demo.md) | Agent pipeline proof-of-concept plan (all stages done) |
| **Guides** | |
| [E2E Reproduction Guide](docs/e2e-reproduction.md) | Step-by-step instructions to reproduce full pipeline validation |
| **Validation Reports** | |
| [00 — Extraction Pipeline E2E](docs/reports/00-extraction-pipeline-e2e-validation.md) | Plan 07 validation: 258 nodes, 268 edges, 28 node types, 45 edge types (2026-03-27) |
| **Research** | |
| [Agent Memory Research](docs/research/01-agent-memory-research.md) | Survey of agent memory approaches |
| [Memory Systems Research](docs/research/02-memory-systems-research.md) | Deeper analysis of memory architectures |

## License

Apache 2.0
