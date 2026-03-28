---
name: ingesting-data
description: "Ingest data into NeoCortex memory via the REST API. Covers all formats (text, documents, events, audio, video), authentication setup, shared graph permissions, and domain routing. Includes executable curl scripts. Use when the user asks about ingesting files, uploading data, setting up shared memory, configuring agent permissions, or bulk-loading content into the knowledge graph."
---

# Ingesting Data into NeoCortex

Guide for ingesting content into NeoCortex memory via the FastAPI ingestion API (port 8001).

## Contents

- [Quick Start](#quick-start)
- [Supported Formats](#supported-formats)
- [Authentication](#authentication)
- [Shared Graph Setup](#shared-graph-setup)
- [Endpoint Reference](ENDPOINTS.md)
- [Permissions & Roles Setup](PERMISSIONS.md)
- [Ingest Script](#ingest-script)

## Quick Start

```bash
# 1. Start the ingestion API
NEOCORTEX_MOCK_DB=true NEOCORTEX_AUTH_MODE=dev_token uv run python -m neocortex.ingestion

# 2. Ingest text
curl -X POST localhost:8001/ingest/text \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev-token-neocortex" \
  -d '{"text": "Important fact to remember"}'

# 3. Verify
curl localhost:8001/health
```

## Supported Formats

| Endpoint | Formats | Max Size | Content Types |
|----------|---------|----------|---------------|
| `/ingest/text` | Plain text (JSON body) | ~10 MB | `application/json` |
| `/ingest/document` | File upload | 10 MB | `text/plain`, `application/json`, `text/markdown`, `text/csv` |
| `/ingest/events` | JSON array (JSON body) | ~10 MB | `application/json` |
| `/ingest/audio` | Audio file upload | 100 MB | `audio/mpeg`, `audio/wav`, `audio/ogg`, `audio/flac`, `audio/aac`, `audio/mp4`, `audio/webm` |
| `/ingest/video` | Video file upload | 100 MB | `video/mp4`, `video/mpeg`, `video/webm`, `video/quicktime`, `video/x-msvideo`, `video/x-matroska`, `video/3gpp` |

Audio is compressed to 64kbps mono opus (.ogg). Video is compressed to 480p h264 + 64kbps audio (.mp4). Both require ffmpeg installed.

## Authentication

All endpoints require `Authorization: Bearer <token>` header (unless `NEOCORTEX_AUTH_MODE=none`).

Token-to-agent mapping is defined in `dev_tokens.json`:

```json
{
  "admin-token-neocortex": "admin",
  "alice-token": "alice",
  "bob-token": "bob",
  "dev-token-neocortex": "dev-user"
}
```

The token determines which agent's personal graph receives the data. Admin token (`admin-token-neocortex`) is required for `/admin/*` endpoints.

## Shared Graph Setup

To ingest into a **shared** knowledge graph instead of a personal one:

```
Step 1: Create shared graph       → POST /admin/graphs
Step 2: Grant write permission    → POST /admin/permissions
Step 3: Ingest with target_graph  → POST /ingest/text (with target_graph field)
```

**Example workflow:**

```bash
# As admin: create a shared graph
curl -X POST localhost:8001/admin/graphs \
  -H "Authorization: Bearer admin-token-neocortex" \
  -H "Content-Type: application/json" \
  -d '{"purpose": "team_knowledge"}'

# As admin: grant alice write access
curl -X POST localhost:8001/admin/permissions \
  -H "Authorization: Bearer admin-token-neocortex" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "alice", "schema_name": "ncx_shared__team_knowledge", "can_read": true, "can_write": true}'

# As alice: ingest to shared graph
curl -X POST localhost:8001/ingest/text \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer alice-token" \
  -d '{"text": "Shared team insight", "target_graph": "ncx_shared__team_knowledge"}'
```

Without `target_graph`, data goes to the agent's personal graph. With it, the system checks write permission and returns 403 if denied.

**Domain routing** can also automatically route content to shared graphs based on semantic classification. See [Permissions & Roles](PERMISSIONS.md) for full setup details.

## Scripts

Two utility scripts in the repo `scripts/` directory:

### `scripts/launch.sh` — Start/stop services

```bash
./scripts/launch.sh          # Start PostgreSQL + MCP + ingestion, wait for healthy
./scripts/launch.sh --stop   # Kill background services
```

### `scripts/ingest.sh` — Curl wrapper for ingestion

Located at `.claude/skills/ingesting-data/scripts/ingest.sh`. Wraps all curl calls with auth headers and error handling.

```bash
# Make executable
chmod +x .claude/skills/ingesting-data/scripts/ingest.sh

# Usage examples
./scripts/ingest.sh text "Some important information"
./scripts/ingest.sh document ./notes.md
./scripts/ingest.sh events '[{"type": "meeting", "topic": "standup"}]'
./scripts/ingest.sh audio ./recording.wav
./scripts/ingest.sh video ./demo.mp4

# With shared graph target
./scripts/ingest.sh --target ncx_shared__research text "Research finding"

# With custom token
./scripts/ingest.sh --token alice-token document ./report.csv

# Full setup: create graph + grant + ingest
./scripts/ingest.sh setup-shared team_knowledge alice
./scripts/ingest.sh --token alice-token --target ncx_shared__team_knowledge text "Shared data"
```

See [scripts/ingest.sh](scripts/ingest.sh) for full usage (`--help`).
