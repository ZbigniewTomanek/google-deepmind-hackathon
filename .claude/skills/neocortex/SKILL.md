---
name: neocortex-project
description: "Work with, debug, and operate the NeoCortex agent memory system. Covers database schema, diagnostic SQL queries, REST API endpoints, permission model, known issues from E2E testing, and ingestion workflows. Use when the user asks about NeoCortex internals, needs help debugging graph/recall/extraction issues, wants to inspect or query the database, manage permissions, ingest data, or understand system behavior."
---

# NeoCortex Project Skill

Operational guide for working with and debugging the NeoCortex agent memory system — a PostgreSQL knowledge graph with multi-schema isolation, MCP tools, and a FastAPI ingestion API.

## Contents

- [Quick Start](#quick-start)
- [Key Architecture](#key-architecture)
- [Database Schema & Diagnostic Queries](DB_SCHEMA.md)
- [Multi-Agent Setup & Debugging](KNOWN_ISSUES.md)
- [REST API Endpoints](ENDPOINTS.md)
- [Permissions & Shared Graphs](PERMISSIONS.md)
- [Ingestion Script](#ingestion-script)

## Quick Start

```bash
# Start everything (PG + MCP :8000 + ingestion :8001)
./scripts/manage.sh start

# Start fresh (wipe existing data)
./scripts/manage.sh start --fresh

# Mock mode (no Docker)
NEOCORTEX_MOCK_DB=true uv run python -m neocortex
NEOCORTEX_MOCK_DB=true uv run python -m neocortex.ingestion

# Run tests
uv run pytest tests/ -v

# Stop app services (PG keeps running)
./scripts/manage.sh stop

# Stop everything including PostgreSQL
./scripts/manage.sh stop --all
```

Connect to the database:

```bash
psql "postgresql://neocortex:neocortex@localhost:5432/neocortex"
```

## Key Architecture

**Multi-schema isolation**: Each agent gets `ncx_{agent_id}__memory`. Shared graphs use `ncx_shared__{purpose}`. Schema naming regex: `^ncx_[a-z0-9]+__[a-z0-9_]+$`.

**Three MCP tools**: `remember` (store), `recall` (search), `discover` (explore ontology). All use the `MemoryRepository` protocol, never `GraphService` directly.

**Recall pipeline**: hybrid scoring = vector similarity (cosine, 768-dim Gemini embeddings) + full-text (tsvector) + recency decay. Fan-out across personal + all readable shared schemas.

**Extraction pipeline**: episode stored -> ontology agent proposes types -> extraction agent creates nodes/edges -> domain router classifies and fans out to shared schemas.

**Domain routing**: Gemini classifier assigns semantic domains (user_profile, technical_knowledge, work_context, domain_knowledge). Additive — never replaces personal graph. Skipped when `target_graph` is explicit.

**Auth modes**: `none` (anonymous), `dev_token` (from `dev_tokens.json`), `google_oauth`. Token determines agent identity.

## Ingestion Script

Curl wrapper at `.claude/skills/neocortex/scripts/ingest.sh`. Handles auth, MIME detection, shared graph setup. Alias it for convenience:

```bash
INGEST=".claude/skills/neocortex/scripts/ingest.sh"

# Basic usage
$INGEST text "Some fact"
$INGEST document ./notes.md
$INGEST audio ./recording.wav
$INGEST video ./demo.mp4

# Shared graph workflow
$INGEST setup-shared team_knowledge alice
$INGEST --token alice-token --target ncx_shared__team_knowledge text "Shared data"

# Admin operations
$INGEST list-graphs
$INGEST list-permissions
$INGEST grant bob ncx_shared__team_knowledge r

# Run with --help for full options
```

## Service Ports & Health

| Service | Port | Health Check |
|---------|------|-------------|
| MCP server | 8000 | `curl localhost:8000/health` (SSE transport) |
| Ingestion API | 8001 | `curl localhost:8001/health` |
| PostgreSQL | 5432 | `pg_isready -h localhost -p 5432` |

## Log Files

| File | Contents |
|------|----------|
| `log/mcp.log` | MCP server logs |
| `log/ingestion.log` | Ingestion API logs |
| `log/agent_actions.log` | Structured JSON audit trail (tool calls, ingestion requests) |

Set `NEOCORTEX_LOG_LEVEL=DEBUG` for routing decisions and DB operations, `TRACE` for connection-level detail.
