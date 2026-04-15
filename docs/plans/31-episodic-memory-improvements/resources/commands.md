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
# Ingest with explicit session_id
.claude/skills/neocortex/scripts/ingest.sh text \
  --content "First message in session" \
  --session-id "test-session-001"

.claude/skills/neocortex/scripts/ingest.sh text \
  --content "Second message in session" \
  --session-id "test-session-001"

.claude/skills/neocortex/scripts/ingest.sh text \
  --content "Third message in session" \
  --session-id "test-session-001"

# Ingest without session_id (auto-UUID assigned)
.claude/skills/neocortex/scripts/ingest.sh text \
  --content "Isolated episode with no explicit session"
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
# Response should contain structured JSON with session_id, created_at, is_context_neighbor fields
```
