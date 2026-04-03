# CLI Commands Reference

All commands assume you're in the project root (`/Users/zbigi/projects/neocortex`).

---

## Service Lifecycle

```bash
# Backup existing data
./scripts/manage.sh snapshot save pre-plan29

# Start fresh (wipes all data)
./scripts/manage.sh start --fresh

# Start with existing data
./scripts/manage.sh start

# Stop app servers (PG keeps running for queries)
./scripts/manage.sh stop

# Stop everything
./scripts/manage.sh stop --all

# Check service status
./scripts/manage.sh status

# Restore from backup
./scripts/manage.sh snapshot load pre-plan29
```

---

## Ingestion via curl

All requests use the ingestion API on port 8001.

### Ingest text

```bash
curl -s -X POST http://localhost:8001/ingest/text \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer claude-code-work" \
  -d '{
    "text": "YOUR_TEXT_HERE",
    "metadata": {"source": "plan29-test", "doc": "DOC_ID"}
  }' | python3 -m json.tool
```

### Ingest text to specific shared graph

```bash
curl -s -X POST http://localhost:8001/ingest/text \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer claude-code-work" \
  -d '{
    "text": "YOUR_TEXT_HERE",
    "target_graph": "ncx_shared__user_profile",
    "metadata": {"source": "plan29-test"}
  }' | python3 -m json.tool
```

### Force re-ingest (skip dedup)

```bash
curl -s -X POST http://localhost:8001/ingest/text \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer claude-code-work" \
  -d '{
    "text": "YOUR_TEXT_HERE",
    "force": true,
    "metadata": {"source": "plan29-retest"}
  }' | python3 -m json.tool
```

---

## Job Monitoring via Admin API

```bash
# Job summary (counts by status)
curl -s "http://localhost:8001/admin/jobs/summary?all_agents=true" \
  -H "Authorization: Bearer admin-token" | python3 -m json.tool

# List all jobs
curl -s "http://localhost:8001/admin/jobs?all_agents=true" \
  -H "Authorization: Bearer admin-token" | python3 -m json.tool

# List failed jobs only
curl -s "http://localhost:8001/admin/jobs?status=failed&all_agents=true" \
  -H "Authorization: Bearer admin-token" | python3 -m json.tool

# Single job detail
curl -s http://localhost:8001/admin/jobs/{job_id} \
  -H "Authorization: Bearer admin-token" | python3 -m json.tool

# Retry a failed job
curl -s -X POST http://localhost:8001/admin/jobs/{job_id}/retry \
  -H "Authorization: Bearer admin-token" | python3 -m json.tool
```

---

## Graph & Permission Management

```bash
# List all graphs
curl -s http://localhost:8001/admin/graphs \
  -H "Authorization: Bearer admin-token" | python3 -m json.tool

# List permissions
curl -s http://localhost:8001/admin/permissions \
  -H "Authorization: Bearer admin-token" | python3 -m json.tool

# List agents
curl -s http://localhost:8001/admin/agents \
  -H "Authorization: Bearer admin-token" | python3 -m json.tool
```

---

## Consolidation Endpoints

```bash
# Preview what consolidation would do (dry run)
curl -s -X POST "http://localhost:8001/admin/consolidate/preview?schema_name=ncx_shared__user_profile" \
  -H "Authorization: Bearer admin-token" | python3 -m json.tool

# Apply consolidation
curl -s -X POST "http://localhost:8001/admin/consolidate/apply?schema_name=ncx_shared__user_profile" \
  -H "Authorization: Bearer admin-token" | python3 -m json.tool
```

---

## Direct SQL via docker compose

```bash
# Interactive psql
docker compose exec postgres psql -U neocortex -d neocortex

# Run a single query
docker compose exec postgres psql -U neocortex -d neocortex -c \
  "SELECT schema_name FROM graph_registry ORDER BY schema_name;"

# Run a query file
docker compose exec postgres psql -U neocortex -d neocortex -f /path/to/query.sql
```

---

## Log Inspection

```bash
# Watch agent action logs (structured JSON — ontology agent activity)
tail -f log/agent_actions.log | python3 -m json.tool

# Watch ingestion server logs
tail -f log/ingestion_stdout.log

# Watch MCP server logs
tail -f log/mcp_stdout.log

# Search for ontology agent tool usage
grep "ontology_agent_complete" log/agent_actions.log | python3 -m json.tool

# Search for specific tool calls
grep "tool_calls" log/agent_actions.log | python3 -m json.tool
```

---

## Polling Pattern: Wait for Extraction Jobs

Use this pattern to wait for all extraction jobs to complete before running
diagnostic queries:

```bash
# Poll until no 'todo' or 'doing' jobs remain
while true; do
  summary=$(curl -s "http://localhost:8001/admin/jobs/summary?all_agents=true" \
    -H "Authorization: Bearer admin-token")
  echo "$summary" | python3 -m json.tool

  todo=$(echo "$summary" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('todo',0)+d.get('doing',0))")
  if [ "$todo" = "0" ]; then
    echo "All jobs complete."
    break
  fi
  echo "Waiting... ($todo jobs remaining)"
  sleep 5
done
```
