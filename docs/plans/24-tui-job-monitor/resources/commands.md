# Commands Reference

## Development

```bash
# Start all services
./scripts/manage.sh start

# Start with fresh DB
./scripts/manage.sh start --fresh

# Run MCP server only (with real DB)
docker compose up -d postgres
uv run python -m neocortex

# Run ingestion API only (with real DB)
docker compose up -d postgres
uv run python -m neocortex.ingestion
```

## TUI

```bash
# Launch TUI (MCP + ingestion on default ports)
uv run python -m neocortex.tui

# Launch TUI with custom URLs
uv run python -m neocortex.tui --url http://localhost:8000 --ingestion-url http://localhost:8001

# Launch TUI with auth token
uv run python -m neocortex.tui --token tui-dev --ingestion-url http://localhost:8001
```

## Testing

```bash
# All tests
uv run pytest tests/ -v

# Admin tests only
uv run pytest tests/ -v -k "test_admin"

# TUI-related tests
uv run pytest tests/ -v -k "tui"

# Single test file
uv run pytest tests/test_admin_jobs.py -v
```

## Manual verification (curl)

```bash
# Job summary
curl -s http://localhost:8001/admin/jobs/summary \
  -H "Authorization: Bearer admin-dev" | python -m json.tool

# List all jobs
curl -s "http://localhost:8001/admin/jobs?limit=10" \
  -H "Authorization: Bearer admin-dev" | python -m json.tool

# List failed jobs only
curl -s "http://localhost:8001/admin/jobs?status=failed" \
  -H "Authorization: Bearer admin-dev" | python -m json.tool

# Single job detail
curl -s http://localhost:8001/admin/jobs/42 \
  -H "Authorization: Bearer admin-dev" | python -m json.tool

# Cancel a queued job
curl -s -X DELETE http://localhost:8001/admin/jobs/42 \
  -H "Authorization: Bearer admin-dev" | python -m json.tool

# Retry a failed job
curl -s -X POST http://localhost:8001/admin/jobs/42/retry \
  -H "Authorization: Bearer admin-dev" | python -m json.tool

# Ingest text (to create jobs for testing)
curl -s -X POST http://localhost:8001/ingest/text \
  -H "Authorization: Bearer admin-dev" \
  -H "Content-Type: application/json" \
  -d '{"text": "Test content for job monitoring", "metadata": {}}' | python -m json.tool
```
