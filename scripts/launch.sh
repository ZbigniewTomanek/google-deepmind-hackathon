#!/usr/bin/env bash
# Launch NeoCortex services for manual testing / skill validation.
#
# Kills any existing processes on ports 8000/8001, starts PostgreSQL (Docker),
# MCP server, and ingestion API, waits for health checks, then exits leaving
# everything running in the background.
#
# Usage:
#   ./scripts/launch.sh          # start everything
#   ./scripts/launch.sh --stop   # tear down background services
#
# Environment overrides:
#   MCP_PORT=8000   INGESTION_PORT=8001   MAX_WAIT=60

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

MCP_PORT="${MCP_PORT:-8000}"
INGESTION_PORT="${INGESTION_PORT:-8001}"
MAX_WAIT="${MAX_WAIT:-60}"
PIDFILE_MCP="$PROJECT_DIR/.mcp.pid"
PIDFILE_INGESTION="$PROJECT_DIR/.ingestion.pid"
LOGDIR="$PROJECT_DIR/log"

log()  { printf '\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m==> %s\033[0m\n' "$*" >&2; exit 1; }

kill_port() {
    local port="$1"
    local pids
    pids=$(lsof -ti ":$port" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        log "Killing existing process(es) on port $port (PIDs: $pids)..."
        echo "$pids" | xargs kill 2>/dev/null || true
        sleep 1
        # Force-kill stragglers
        pids=$(lsof -ti ":$port" 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            echo "$pids" | xargs kill -9 2>/dev/null || true
            sleep 1
        fi
    fi
}

kill_pidfile() {
    local pidfile="$1"
    if [[ -f "$pidfile" ]]; then
        local pid
        pid=$(<"$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
        fi
        rm -f "$pidfile"
    fi
}

wait_for_healthy() {
    local url="$1" max="$2" elapsed=0
    log "Waiting for $url (up to ${max}s)..."
    while (( elapsed < max )); do
        if curl -sf "$url" >/dev/null 2>&1; then
            ok "Healthy: $url (${elapsed}s)"
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    fail "Service at $url not healthy after ${max}s"
}

wait_for_postgres() {
    log "Waiting for PostgreSQL..."
    local elapsed=0
    while (( elapsed < MAX_WAIT )); do
        if docker compose -f "$PROJECT_DIR/docker-compose.yml" exec -T postgres \
            pg_isready -U neocortex -d neocortex >/dev/null 2>&1; then
            ok "PostgreSQL ready (${elapsed}s)"
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    fail "PostgreSQL not ready after ${MAX_WAIT}s"
}

apply_migrations() {
    log "Applying migrations..."
    local migration_dir="$PROJECT_DIR/migrations/init"
    for f in "$migration_dir"/*.sql; do
        local name
        name="$(basename "$f")"
        local already
        already=$(docker compose -f "$PROJECT_DIR/docker-compose.yml" exec -T postgres \
            psql -U neocortex -d neocortex -tAc \
            "SELECT 1 FROM _migration WHERE name = '$name' LIMIT 1;" 2>/dev/null || echo "")
        if [[ "$already" == "1" ]]; then
            continue
        fi
        log "  Applying $name..."
        docker compose -f "$PROJECT_DIR/docker-compose.yml" exec -T -e PGPASSWORD=neocortex postgres \
            psql -U neocortex -d neocortex < "$f" >/dev/null 2>&1
        docker compose -f "$PROJECT_DIR/docker-compose.yml" exec -T postgres \
            psql -U neocortex -d neocortex -c \
            "INSERT INTO _migration (name) VALUES ('$name') ON CONFLICT DO NOTHING;" >/dev/null 2>&1 || true
        ok "  Applied $name"
    done
}

do_stop() {
    log "Stopping NeoCortex services..."
    kill_pidfile "$PIDFILE_MCP"
    kill_pidfile "$PIDFILE_INGESTION"
    kill_port "$MCP_PORT"
    kill_port "$INGESTION_PORT"
    ok "Services stopped. PostgreSQL container left running."
    exit 0
}

do_start() {
    cd "$PROJECT_DIR"
    mkdir -p "$LOGDIR"

    # --- Clean up old instances ---
    log "Clearing old instances..."
    kill_pidfile "$PIDFILE_MCP"
    kill_pidfile "$PIDFILE_INGESTION"
    kill_port "$MCP_PORT"
    kill_port "$INGESTION_PORT"

    # --- PostgreSQL ---
    log "Ensuring PostgreSQL is running..."
    docker compose -f "$PROJECT_DIR/docker-compose.yml" up -d postgres 2>&1 || {
        log "Container conflict — removing stale container and retrying..."
        docker rm -f neocortex-postgres 2>/dev/null || true
        docker compose -f "$PROJECT_DIR/docker-compose.yml" up -d postgres 2>&1
    }
    wait_for_postgres
    apply_migrations

    # --- Source .env ---
    if [[ -f "$PROJECT_DIR/.env" ]]; then
        set -a; source "$PROJECT_DIR/.env"; set +a
    fi

    # --- MCP server ---
    log "Starting MCP server (port $MCP_PORT)..."
    NEOCORTEX_AUTH_MODE=dev_token \
    NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
    NEOCORTEX_MOCK_DB=false \
    uv run python -m neocortex \
        >"$LOGDIR/mcp_stdout.log" 2>&1 &
    echo $! > "$PIDFILE_MCP"
    log "  PID $(cat "$PIDFILE_MCP") → log: $LOGDIR/mcp_stdout.log"

    # --- Ingestion server ---
    log "Starting ingestion server (port $INGESTION_PORT)..."
    NEOCORTEX_AUTH_MODE=dev_token \
    NEOCORTEX_DEV_TOKENS_FILE=dev_tokens.json \
    NEOCORTEX_MOCK_DB=false \
    uv run python -m neocortex.ingestion \
        >"$LOGDIR/ingestion_stdout.log" 2>&1 &
    echo $! > "$PIDFILE_INGESTION"
    log "  PID $(cat "$PIDFILE_INGESTION") → log: $LOGDIR/ingestion_stdout.log"

    # --- Health checks ---
    wait_for_healthy "http://127.0.0.1:${MCP_PORT}/health" "$MAX_WAIT"
    wait_for_healthy "http://127.0.0.1:${INGESTION_PORT}/health" "$MAX_WAIT"

    ok "All services running. Ready for testing."
    echo ""
    echo "  MCP server:       http://127.0.0.1:${MCP_PORT}"
    echo "  Ingestion API:    http://127.0.0.1:${INGESTION_PORT}"
    echo "  Admin token:      admin-token-neocortex"
    echo "  Dev token:        dev-token-neocortex"
    echo ""
    echo "  Stop with:        $0 --stop"
    echo "  Logs:             tail -f $LOGDIR/mcp_stdout.log $LOGDIR/ingestion_stdout.log"
}

# --- Parse args ---
case "${1:-start}" in
    --stop|-s|stop)  do_stop ;;
    --help|-h|help)
        echo "Usage: $(basename "$0") [--stop | --help]"
        echo "  (no args)  Start PostgreSQL + MCP + ingestion, wait for healthy"
        echo "  --stop     Kill background services"
        exit 0
        ;;
    start|"")  do_start ;;
    *)  fail "Unknown argument: $1" ;;
esac
