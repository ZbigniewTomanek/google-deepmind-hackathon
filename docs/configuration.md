# Configuration

## Quick Setup

```bash
# 1. Start PostgreSQL
docker compose up -d postgres

# 2. Install dependencies
uv sync

# 3. Run the MCP server
NEOCORTEX_AUTH_MODE=dev_token \
NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
uv run python -m neocortex

# 4. (Optional) Run the ingestion API
NEOCORTEX_AUTH_MODE=dev_token \
NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
uv run python -m neocortex.ingestion
```

Or use the service manager which handles PostgreSQL, migrations, and both servers:

```bash
./scripts/manage.sh start        # Start everything
./scripts/manage.sh stop         # Stop app services (PG keeps running)
./scripts/manage.sh stop --all   # Stop everything including PostgreSQL
./scripts/manage.sh start --fresh  # Wipe data and start clean
```

### Mock Mode (no Docker)

For quick testing without PostgreSQL:

```bash
NEOCORTEX_MOCK_DB=true uv run python -m neocortex
```

This uses an in-memory repository. Data does not persist across restarts.

## Services

| Service | Port | Purpose |
|---------|------|---------|
| MCP Server | 8000 | `remember`/`recall`/`discover` tools + extraction worker |
| Ingestion API | 8001 | Bulk loading (text, documents, events, audio, video) + Admin API |
| PostgreSQL | 5432 | Storage, search, isolation |

## Authentication

Four auth modes, set via `NEOCORTEX_AUTH_MODE`:

| Mode | Use case | How it works |
|------|----------|-------------|
| `none` | Local development | All requests map to agent `"anonymous"` |
| `dev_token` | Multi-agent testing | Bearer tokens mapped to agent IDs via a JSON file |
| `google_oauth` | Production (Google) | Google OAuth via FastMCP OAuthProxy |
| `auth0` | Production (enterprise) | Auth0 JWT verification |

### Token Configuration (dev_token mode)

Create a `dev_tokens.json` mapping bearer tokens to agent identities:

```json
{
  "admin-token": "admin",
  "claude-code-work": "cc-work",
  "claude-code-private": "cc-private",
  "tui-dev": "dev-user"
}
```

Then set:
```bash
NEOCORTEX_AUTH_MODE=dev_token
NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json
```

Agents authenticate with `Authorization: Bearer claude-code-work`. Each token resolves to an agent ID that determines which personal graph they use and what permissions they have.

## Ingestion API

The ingestion API provides bulk loading endpoints. All require a bearer token.

### Text & Documents

```bash
# Plain text
curl -X POST localhost:8001/ingest/text \
  -H "Authorization: Bearer claude-code-work" \
  -H "Content-Type: application/json" \
  -d '{"text": "Python asyncio is great for I/O-bound tasks", "metadata": {"source": "notes"}}'

# Document upload (text/plain, application/json, text/markdown, text/csv)
curl -X POST localhost:8001/ingest/document \
  -H "Authorization: Bearer claude-code-work" \
  -F "file=@notes.md;type=text/markdown"

# Structured events
curl -X POST localhost:8001/ingest/events \
  -H "Authorization: Bearer claude-code-work" \
  -H "Content-Type: application/json" \
  -d '{"events": [{"text": "Sprint planning completed", "metadata": {"date": "2026-03-31"}}]}'
```

### Audio & Video

Requires `ffmpeg` and `ffprobe` on PATH. Files are compressed and described via Gemini multimodal inference.

```bash
# Audio (compressed to 64 kbps mono Opus)
curl -X POST localhost:8001/ingest/audio \
  -H "Authorization: Bearer claude-code-work" \
  -F "file=@meeting.wav;type=audio/wav"

# Video (compressed to 480p H.264)
curl -X POST localhost:8001/ingest/video \
  -H "Authorization: Bearer claude-code-work" \
  -F "file=@demo.mp4;type=video/mp4"
```

Supported formats: MP3, WAV, OGG, FLAC, AAC (audio); MP4, WebM, MOV, AVI, MKV (video).
Upload limit: 100 MB (configurable via `NEOCORTEX_MEDIA_MAX_UPLOAD_BYTES`).

All ingestion endpoints accept an optional `target_graph` field to write to a specific shared graph (requires write permission).

## Admin API

Mounted on the ingestion server (port 8001). Requires admin bearer token.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/graphs` | POST | Create shared graph |
| `/admin/graphs` | GET | List all graphs |
| `/admin/graphs/{schema}` | DELETE | Drop shared graph |
| `/admin/permissions` | POST | Grant/update permission |
| `/admin/permissions` | GET | List permissions (filter by `?agent_id=` or `?schema_name=`) |
| `/admin/permissions/{agent}/{schema}` | DELETE | Revoke permission |
| `/admin/agents` | GET | List registered agents |
| `/admin/agents/{agent}/admin` | PUT | Promote to admin |
| `/admin/agents/{agent}/admin` | DELETE | Demote from admin |

## Developer TUI

Interactive terminal UI for testing. Connects to a running MCP server.

```bash
uv run python -m neocortex.tui --url http://localhost:8000 --token tui-dev
```

Keys: `r` = remember, `q` = recall, `d` = discover, `Ctrl+Q` = quit.

## Environment Variables

All prefixed with `NEOCORTEX_` (Pydantic BaseSettings).

### Server

| Variable | Default | Description |
|----------|---------|-------------|
| `NEOCORTEX_SERVER_HOST` | `127.0.0.1` | Listen address |
| `NEOCORTEX_SERVER_PORT` | `8000` | Listen port |
| `NEOCORTEX_TRANSPORT` | `http` | MCP transport: `stdio`, `http`, `sse`, `streamable-http` |
| `NEOCORTEX_MOCK_DB` | `false` | Use in-memory mock (no PostgreSQL) |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `neocortex` | Database name |
| `POSTGRES_USER` | `neocortex` | Database user |
| `POSTGRES_PASSWORD` | `neocortex` | Database password |

### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `NEOCORTEX_AUTH_MODE` | `none` | `none`, `dev_token`, `google_oauth`, `auth0` |
| `NEOCORTEX_DEV_TOKENS_FILE` | _(empty)_ | Path to token→agent JSON file |
| `NEOCORTEX_BOOTSTRAP_ADMIN_ID` | `admin` | Agent ID seeded as admin on startup |
| `NEOCORTEX_ADMIN_TOKEN` | `admin-token` | Bootstrap admin bearer token |

### Embeddings & Recall

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_API_KEY` | _(unset)_ | Google AI API key. When unset, recall falls back to text-only. |
| `NEOCORTEX_EMBEDDING_MODEL` | `gemini-embedding-001` | Embedding model |
| `NEOCORTEX_RECALL_WEIGHT_VECTOR` | `0.3` | Vector similarity weight |
| `NEOCORTEX_RECALL_WEIGHT_TEXT` | `0.2` | Text rank weight |
| `NEOCORTEX_RECALL_WEIGHT_RECENCY` | `0.15` | Recency decay weight |
| `NEOCORTEX_RECALL_WEIGHT_ACTIVATION` | `0.20` | ACT-R activation weight |
| `NEOCORTEX_RECALL_WEIGHT_IMPORTANCE` | `0.15` | Node importance weight |
| `NEOCORTEX_RECALL_RECENCY_HALF_LIFE_HOURS` | `168.0` | Recency half-life (7 days) |

### Media

| Variable | Default | Description |
|----------|---------|-------------|
| `NEOCORTEX_MEDIA_STORE_PATH` | `./media_store` | Compressed media storage directory |
| `NEOCORTEX_MEDIA_MAX_UPLOAD_BYTES` | `104857600` | Max upload size (100 MB) |
| `NEOCORTEX_MEDIA_DESCRIPTION_MODEL` | `gemini-3-flash-preview` | Multimodal description model |

### Domain Routing

| Variable | Default | Description |
|----------|---------|-------------|
| `NEOCORTEX_DOMAIN_ROUTING_ENABLED` | `true` | Auto-route to shared domain graphs |
| `NEOCORTEX_DOMAIN_CLASSIFICATION_THRESHOLD` | `0.3` | Minimum confidence for routing |
| `NEOCORTEX_DOMAIN_CLASSIFIER_MODEL` | `google-gla:gemini-3-flash-preview` | Classification model (any Pydantic AI provider string) |

### Extraction Pipeline

| Variable | Default | Description |
|----------|---------|-------------|
| `NEOCORTEX_EXTRACTION_ENABLED` | `true` | Run background extraction |
| `NEOCORTEX_ONTOLOGY_MODEL` | `google-gla:gemini-3-flash-preview` | Ontology agent model (any Pydantic AI provider string) |
| `NEOCORTEX_EXTRACTOR_MODEL` | `google-gla:gemini-3-flash-preview` | Extractor agent model (any Pydantic AI provider string) |
| `NEOCORTEX_LIBRARIAN_MODEL` | `google-gla:gemini-3-flash-preview` | Librarian agent model (any Pydantic AI provider string) |
| `NEOCORTEX_EXTRACTION_TOOL_CALLS_LIMIT` | `150` | Max tool calls per extraction run |

## Snapshots

Save and restore database state + media files:

```bash
./scripts/manage.sh snapshot save my-backup     # Save current state
./scripts/manage.sh snapshot list                # List snapshots
./scripts/manage.sh snapshot load my-backup      # Restore from snapshot
./scripts/manage.sh snapshot delete my-backup    # Delete snapshot
```
