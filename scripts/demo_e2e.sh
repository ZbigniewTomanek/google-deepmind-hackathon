#!/usr/bin/env bash
# End-to-end demo script for NeoCortex extraction pipeline.
#
# Starts infrastructure, ingests seed corpus, waits for extraction,
# then launches the TUI for interactive exploration.
#
# Usage:
#   ./scripts/demo_e2e.sh
#
# Prerequisites:
#   - Docker running (for PostgreSQL)
#   - GOOGLE_API_KEY set (for Gemini embeddings + extraction agents)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

MCP_PID=""
ING_PID=""

log()  { printf '\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m==> %s\033[0m\n' "$*" >&2; exit 1; }

cleanup() {
    log "Cleaning up..."
    for pid in $MCP_PID $ING_PID; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
            log "Stopped process (PID $pid)."
        fi
    done
    docker compose -f "$PROJECT_DIR/docker-compose.yml" stop postgres --timeout 5 2>/dev/null || true
    log "Stopped PostgreSQL container."
}

wait_for_healthy() {
    local url="$1" max="$2" elapsed=0
    log "Waiting for $url (up to ${max}s)..."
    while (( elapsed < max )); do
        if curl -sf "$url" >/dev/null 2>&1; then
            ok "Healthy: $url (${elapsed}s)."
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    fail "Service at $url did not become healthy within ${max}s."
}

trap cleanup EXIT INT TERM

cd "$PROJECT_DIR"

echo "=== NeoCortex PoC Demo ==="

# 1. Start infrastructure
log "Starting PostgreSQL..."
docker compose up -d postgres
sleep 3

# 2. Start MCP server (background)
log "Starting MCP server (port 8000)..."
NEOCORTEX_AUTH_MODE=dev_token \
NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
NEOCORTEX_MOCK_DB=false \
uv run python -m neocortex &
MCP_PID=$!
sleep 2

# 3. Start ingestion API (background)
log "Starting ingestion API (port 8001)..."
NEOCORTEX_AUTH_MODE=dev_token \
NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
NEOCORTEX_MOCK_DB=false \
uv run python -m neocortex.ingestion &
ING_PID=$!
sleep 2

wait_for_healthy "http://127.0.0.1:8000/health" 30
wait_for_healthy "http://127.0.0.1:8001/health" 30

# 4. Ingest seed corpus
log "Ingesting medical seed corpus..."
uv run python -m neocortex.extraction.cli --ingest-corpus --token claude-code-work

# 5. Wait for extraction jobs to complete
log "Waiting for extraction jobs..."
sleep 30  # Allow extraction pipeline to process

# 6. Launch TUI for interactive demo
ok "Demo ready! Launching TUI..."
echo ""
echo "Try these in the TUI:"
echo "  Recall: 'serotonin mood regulation'"
echo "  Recall: 'SSRI side effects'"
echo "  Discover: fetch ontology to see extracted types"
echo ""
NEOCORTEX_AUTH_MODE=dev_token uv run python -m neocortex.tui --token tui-dev
