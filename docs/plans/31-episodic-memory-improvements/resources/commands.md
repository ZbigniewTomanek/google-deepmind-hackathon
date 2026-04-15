# Build, Test & Ingestion Commands

---

## Tests

```bash
# Run all unit tests (no Docker needed, uses mock DB)
uv run pytest tests/ -v

# Run only episode-related tests
uv run pytest tests/ -v -k episode

# Run with real DB (requires postgres running)
uv run pytest tests/ -v --no-header

# Run with explicit mock mode
NEOCORTEX_MOCK_DB=true uv run pytest tests/ -v
```

---

## Services

```bash
# Start everything (postgres + MCP + ingestion)
./scripts/manage.sh start

# Start with fresh DB (wipes and recreates)
./scripts/manage.sh start --fresh

# Stop app services (postgres keeps running)
./scripts/manage.sh stop

# Stop everything
./scripts/manage.sh stop --all

# Check service status
./scripts/manage.sh status
```

---

## Run migrations manually

```bash
# Apply all pending public schema migrations
uv run python -m neocortex.migrations public

# Apply per-agent graph schema migrations (substitute <agent_id>)
uv run python -m neocortex.migrations graph ncx_<agent_id>__personal
```

---

## Test session-tagged ingestion

```bash
# Ingest with explicit session_id.
# The current ingest.sh wrapper must be updated before it can pass session_id;
# until then use raw curl.
curl -sS -X POST http://localhost:8001/ingest/text \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer claude-code-work" \
  -d '{"text":"First message in session","session_id":"test-session-001"}'

curl -sS -X POST http://localhost:8001/ingest/text \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer claude-code-work" \
  -d '{"text":"Second message in session","session_id":"test-session-001"}'

curl -sS -X POST http://localhost:8001/ingest/text \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer claude-code-work" \
  -d '{"text":"Third message in session","session_id":"test-session-001"}'

# Ingest without session_id (EpisodeProcessor assigns one request-level UUID)
curl -sS -X POST http://localhost:8001/ingest/text \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer claude-code-work" \
  -d '{"text":"Isolated episode with no explicit session"}'
```

---

## Verify STM boost scores (interactive)

```bash
# Start MCP server with debug logging
NEOCORTEX_LOG_LEVEL=DEBUG uv run python -m neocortex

# Then run a recall from the TUI:
uv run python -m neocortex.tui
# → Select Recall mode, enter a query matching recent vs. older episodes
```

---

## Check recall output format

```bash
# Using the MCP client directly:
curl -X POST http://localhost:8000/mcp/v1/call_tool \
  -H "Content-Type: application/json" \
  -d '{"tool": "recall", "arguments": {"query": "test session tagging"}}'
# Response structured_content should include formatted_context with
# session_id, created_at, is_context_neighbor fields
```
