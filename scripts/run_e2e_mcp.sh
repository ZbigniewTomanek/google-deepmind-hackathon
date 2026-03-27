#!/usr/bin/env bash
# E2E smoke test coordinator for the multi-graph NeoCortex server.
#
# Starts PostgreSQL + MCP server, waits for readiness, runs the smoke test,
# and tears everything down on exit.
#
# Usage:
#   ./scripts/run_e2e_mcp.sh            # default: run locally (server as background process)
#   ./scripts/run_e2e_mcp.sh --docker   # run everything via docker compose
#
# Environment overrides:
#   NEOCORTEX_BASE_URL   (default: http://127.0.0.1:8000)
#   KEEP_RUNNING=1       keep services up after test (skip teardown)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

BASE_URL="${NEOCORTEX_BASE_URL:-http://127.0.0.1:8000}"
HEALTH_URL="$BASE_URL/health"
MAX_WAIT=60          # seconds to wait for server readiness
SERVER_PID=""
MODE="local"

# --- helpers ---------------------------------------------------------------

log()  { printf '\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m==> %s\033[0m\n' "$*" >&2; exit 1; }

cleanup() {
    local exit_code=$?
    if [[ "${KEEP_RUNNING:-}" == "1" ]]; then
        ok "KEEP_RUNNING=1 — leaving services up."
        return
    fi

    log "Cleaning up..."
    if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
        log "Stopped MCP server (PID $SERVER_PID)."
    fi

    if [[ "$MODE" == "docker" ]]; then
        docker compose -f "$PROJECT_DIR/docker-compose.yml" down --timeout 5 2>/dev/null || true
        log "Stopped docker compose services."
    else
        docker compose -f "$PROJECT_DIR/docker-compose.yml" stop postgres --timeout 5 2>/dev/null || true
        log "Stopped PostgreSQL container."
    fi

    exit "$exit_code"
}

wait_for_healthy() {
    local url="$1" max="$2" elapsed=0
    log "Waiting for $url (up to ${max}s)..."
    while (( elapsed < max )); do
        if curl -sf "$url" >/dev/null 2>&1; then
            ok "Server is healthy (${elapsed}s)."
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    fail "Server did not become healthy within ${max}s."
}

# --- parse args ------------------------------------------------------------

for arg in "$@"; do
    case "$arg" in
        --docker) MODE="docker" ;;
        *) fail "Unknown argument: $arg" ;;
    esac
done

# --- main ------------------------------------------------------------------

trap cleanup EXIT INT TERM

cd "$PROJECT_DIR"

if [[ "$MODE" == "docker" ]]; then
    # ---------- Docker mode: everything via docker compose ------------------
    log "Starting all services via docker compose..."
    docker compose up -d --build
    wait_for_healthy "$HEALTH_URL" "$MAX_WAIT"

    log "Running E2E smoke test..."
    uv run python scripts/e2e_mcp_test.py
else
    # ---------- Local mode: PG in Docker, server as local process -----------
    log "Starting PostgreSQL via docker compose..."
    docker compose up -d postgres

    # Wait for PG to be ready
    log "Waiting for PostgreSQL to be ready..."
    elapsed=0
    while (( elapsed < MAX_WAIT )); do
        if docker compose exec -T postgres pg_isready -U neocortex -d neocortex >/dev/null 2>&1; then
            ok "PostgreSQL is ready (${elapsed}s)."
            break
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    if (( elapsed >= MAX_WAIT )); then
        fail "PostgreSQL did not become ready within ${MAX_WAIT}s."
    fi

    log "Starting NeoCortex MCP server..."
    NEOCORTEX_AUTH_MODE=dev_token \
    NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
    NEOCORTEX_MOCK_DB=false \
    uv run python -m neocortex &
    SERVER_PID=$!

    wait_for_healthy "$HEALTH_URL" "$MAX_WAIT"

    log "Running E2E smoke test..."
    uv run python scripts/e2e_mcp_test.py
fi

ok "ALL E2E CHECKS PASSED"
