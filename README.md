# NeoCortex

Long-term memory for AI agents. MCP server that turns conversations into a self-organizing knowledge graph on PostgreSQL.

3 tools. No graph queries. Just `remember`, `recall`, `discover`.

## Why NeoCortex?

Most agent memory is either flat files (fragile, size-limited) or vector stores (no relational reasoning, no forgetting, no schema evolution). NeoCortex is different:

- **Self-organizing knowledge graph** — a 3-agent extraction pipeline (Ontology, Extractor, Librarian) autonomously builds and maintains a structured graph from raw text. No manual schema design.
- **Cognitive scoring** — recall uses 5 signals: vector similarity, full-text search, recency decay, ACT-R activation (biological forgetting curves), and node importance. Weights redistribute gracefully when signals are missing.
- **Graph-native retrieval** — spreading activation propagates energy through edges, surfacing indirectly related knowledge. Hebbian reinforcement strengthens frequently co-activated paths.
- **PostgreSQL-native** — pgvector + tsvector + RLS in one system. No external graph database.

Unlike Mem0 (vector store with graph addon), Zep/Graphiti (conversation-focused temporal graphs), or Letta (OS-inspired paging) — NeoCortex builds a real knowledge graph autonomously and retrieves from it using cognitive science principles.

## Architecture

```
                     +------------------+
                     |   AI Agents      |  (Claude Code, Pydantic AI, etc.)
                     +--------+---------+
                              |  MCP protocol
                     +--------v---------+       +------------------------+
                     |   MCP Server     |       |  Ingestion API (:8001) |
                     |  remember/recall |       |  text/docs/audio/video |
                     |  /discover :8000 |       +----------+-------------+
                     +--------+---------+                  |
                              |                            |
              +-------+-------+-------+                    |
              |               |       |                    |
     +--------v------+ +-----v-----+ +------v--------+    |
     | GraphRouter   | | AuthLayer | | SchemaManager |    |
     | (heuristics)  | | (tokens)  | | (lifecycle)   |    |
     +-------+-------+ +-----+-----+ +------+--------+    |
             |                |              |             |
     +-------v----------------v--------------v-------+-----+
     |              PostgreSQL 16                     |
     |  pgvector (semantic) + tsvector (BM25)         |
     |  multi-schema isolation + RLS                  |
     +-------------------------------------------------+
```

See [How it Works](docs/how-it-works.md) for the full explanation of the extraction pipeline and recall scoring.

## MCP Tools

| Tool | Input | Description |
|------|-------|-------------|
| `remember` | `text`, `context?`, `importance?` | Store content as an episode. Extraction pipeline enriches the graph asynchronously. |
| `recall` | `query`, `limit?` | Hybrid search (semantic + lexical + graph traversal) with cognitive scoring. |
| `discover` | varies | Navigate the graph: list graphs, browse ontology, inspect nodes and neighborhoods. |

## Quick Start

```bash
# No Docker needed — try with in-memory mock
uv sync
NEOCORTEX_MOCK_DB=true uv run python -m neocortex

# With PostgreSQL (full features)
docker compose up -d postgres
NEOCORTEX_AUTH_MODE=dev_token \
NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
uv run python -m neocortex

# Developer TUI
uv run python -m neocortex.tui --url http://localhost:8000 --token tui-dev

# Tests
uv run pytest tests/ -v
```

Full setup guide: [Configuration](docs/configuration.md)

## Key Features

- **3-agent extraction pipeline** — Ontology, Extractor, Librarian agents turn raw text into structured knowledge ([how it works](docs/how-it-works.md))
- **Hybrid recall with cognitive scoring** — 5 signals, ACT-R activation, spreading activation, Hebbian reinforcement ([details](docs/how-it-works.md#how-recall-works))
- **Multi-agent isolation** — per-agent PostgreSQL schemas + shared graphs with RLS and permissions ([multi-agent](docs/multi-agent.md))
- **Domain routing** — automatic classification into shared semantic graphs ([details](docs/multi-agent.md#domain-routing))
- **Multimodal ingestion** — text, documents, events, audio, video via REST API ([configuration](docs/configuration.md#ingestion-api))
- **Developer TUI** — interactive terminal for testing remember/recall/discover

## Tech Stack

| Component | Technology |
|-----------|------------|
| LLM | Gemini (via Pydantic AI) |
| Embeddings | Gemini embedding model (768 dims) |
| Database | PostgreSQL 16 + pgvector + tsvector |
| MCP Server | FastMCP (Python) |
| Agent Framework | Pydantic AI |
| Background Jobs | Procrastinate (PostgreSQL-based) |
| Data Access | asyncpg |
| TUI | Textual + Click |
| Language | Python 3.13 |

## Documentation

| Document | Description |
|----------|-------------|
| [How it Works](docs/how-it-works.md) | Knowledge graph, extraction pipeline, recall scoring, cognitive heuristics |
| [Multi-Agent](docs/multi-agent.md) | Graph isolation, shared knowledge, permissions, domain routing |
| [Configuration](docs/configuration.md) | Setup, auth, environment variables, ingestion API, admin API |
| [Development Guide](docs/development.md) | Contributing, tests, project layout, adding tools/migrations |
| [Architecture](docs/architecture.md) | Technical deep-dive, data model, embedding service |

## License

Apache 2.0
