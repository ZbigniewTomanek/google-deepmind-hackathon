# Commands Reference

Quick-reference for all commands used across stages.

## Service Lifecycle

```bash
# Start fresh (wipe DB + recreate)
NEOCORTEX_DEV_TOKENS_FILE=dev_tokens_test.json ./scripts/manage.sh start --fresh

# Stop everything
./scripts/manage.sh stop --all

# Health checks
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8001/health
```

## Ingest.sh Shortcuts

```bash
INGEST=".claude/skills/neocortex/scripts/ingest.sh"

# Create shared graph + grant permissions
$INGEST --admin-token admin-token-neocortex setup-shared project_titan alice
$INGEST --admin-token admin-token-neocortex grant bob ncx_shared__project_titan rw

# Ingest as alice
$INGEST --token alice-token --target ncx_shared__project_titan text "<text>"

# Ingest as bob
$INGEST --token bob-token --target ncx_shared__project_titan text "<text>"

# List graphs / permissions
$INGEST --admin-token admin-token-neocortex list-graphs
$INGEST --admin-token admin-token-neocortex list-permissions alice
$INGEST --admin-token admin-token-neocortex list-permissions bob
```

## Direct curl (for longer texts)

```bash
curl -s -X POST http://127.0.0.1:8001/ingest/text \
  -H "Authorization: Bearer alice-token" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "...",
    "target_graph": "ncx_shared__project_titan",
    "metadata": {"source": "alice"}
  }'
```

## MCP Tool Calls (via fastmcp Client)

```bash
uv run python -c "
import asyncio, json
from fastmcp import Client

async def call(token, tool, args):
    async with Client('http://127.0.0.1:8000/mcp', auth=token) as c:
        r = await c.call_tool(tool, args)
        print(json.dumps(r.structured_content, indent=2, default=str))

asyncio.run(call('alice-token', 'recall', {'query': 'PROJECT_QUERY', 'limit': 5}))
"
```

## Extraction Job Polling

```bash
# Get baseline job ID
docker exec neocortex-postgres psql -U neocortex -d neocortex -t -c \
  "SELECT coalesce(max(id), 0) FROM procrastinate_jobs;"

# Poll until done (replace BASELINE with actual ID)
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT
    count(*) FILTER (WHERE status = 'todo') AS pending,
    count(*) FILTER (WHERE status = 'doing') AS running,
    count(*) FILTER (WHERE status = 'succeeded') AS completed,
    count(*) FILTER (WHERE status = 'failed') AS failed
  FROM procrastinate_jobs
  WHERE id > BASELINE;"
```

## Graph Inspection Queries

```bash
SCHEMA="ncx_shared__project_titan"

# Node count
docker exec neocortex-postgres psql -U neocortex -d neocortex -t -c \
  "SELECT count(*) FROM ${SCHEMA}.node WHERE forgotten = false;"

# Edge count
docker exec neocortex-postgres psql -U neocortex -d neocortex -t -c \
  "SELECT count(*) FROM ${SCHEMA}.edge;"

# Episode count
docker exec neocortex-postgres psql -U neocortex -d neocortex -t -c \
  "SELECT count(*) FROM ${SCHEMA}.episode;"

# All nodes
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT name, type, substring(content, 1, 80) AS content_preview
   FROM ${SCHEMA}.node WHERE forgotten = false ORDER BY name;"

# All edges
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT source_name, type, target_name
   FROM ${SCHEMA}.edge ORDER BY type, source_name;"

# Node types
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT type, count(*) AS cnt
   FROM ${SCHEMA}.node WHERE forgotten = false
   GROUP BY type ORDER BY cnt DESC;"

# Edge types
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT type, count(*) AS cnt
   FROM ${SCHEMA}.edge GROUP BY type ORDER BY cnt DESC;"

# Duplicate detection
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT lower(name) AS norm_name, count(*) AS cnt, array_agg(name) AS variants
   FROM ${SCHEMA}.node WHERE forgotten = false
   GROUP BY lower(name) HAVING count(*) > 1
   ORDER BY cnt DESC;"

# Per-agent episode counts
docker exec neocortex-postgres psql -U neocortex -d neocortex -c \
  "SELECT agent_id, count(*) FROM ${SCHEMA}.episode GROUP BY agent_id;"
```

## Token Reference

From `dev_tokens_test.json`:
- `admin-token-neocortex` → agent_id: `admin`
- `alice-token` → agent_id: `alice`
- `bob-token` → agent_id: `bob`
- `eve-token` → agent_id: `eve`
