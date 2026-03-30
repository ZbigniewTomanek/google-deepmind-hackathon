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

## Features

- **3-agent extraction pipeline** — Ontology, Extractor, and Librarian agents (Gemini) automatically enrich raw text into a structured knowledge graph via async background jobs (Procrastinate)
- **Hybrid recall** — weighted combination of pgvector cosine similarity, tsvector full-text search, recency decay, ACT-R activation, and node importance with automatic weight redistribution when signals are missing
- **Multi-graph isolation** — each agent gets private PostgreSQL schemas; shared schemas use Row-Level Security for cross-agent knowledge
- **Ingestion API** — FastAPI service (`:8001`) for bulk loading text, documents, events, audio, and video with automatic extraction
- **Domain routing** — automatic classification of memories into shared semantic domain graphs
- **Auth** — pluggable: `none` (dev), `dev_token` (multi-agent testing), `google_oauth` (production)
- **Developer TUI** — interactive terminal UI for testing remember/recall/discover
- **Structured logging** — rotating service logs + JSON audit trail for all tool invocations

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
| **Design Plans** | |
| [High-Level Plan](docs/plans/01-high-level-hackathon-plan.md) | Original vision, data model, memory types, heuristics roadmap |
| [PostgreSQL Storage](docs/plans/02-postgres-storage-layer.md) | Storage layer design |
| [MCP Server Scaffold](docs/plans/03-mcp-server-scaffold.md) | Server, tools, auth design |
| [Multi-Graph Schemas](docs/plans/04-multi-graph-schemas.md) | Schema isolation architecture |
| [Embeddings, Hybrid Recall, TUI](docs/plans/06-embeddings-hybrid-recall-tui.md) | Embedding service, hybrid scoring, developer TUI |
| [Extraction Pipeline Integration](docs/plans/07-extraction-pipeline-integration.md) | 3-agent pipeline integration |
| **Guides** | |
| [E2E Reproduction Guide](docs/e2e-reproduction.md) | Step-by-step instructions to reproduce full pipeline validation |
| **Validation Reports** | |
| [00 — Extraction Pipeline E2E](docs/reports/00-extraction-pipeline-e2e-validation.md) | Plan 07 validation: 258 nodes, 268 edges, 28 node types, 45 edge types (2026-03-27) |
| **Research** | |
| [Agent Memory Research](docs/research/01-agent-memory-research.md) | Survey of agent memory approaches |
| [Memory Systems Research](docs/research/02-memory-systems-research.md) | Deeper analysis of memory architectures |

## License

Apache 2.0
