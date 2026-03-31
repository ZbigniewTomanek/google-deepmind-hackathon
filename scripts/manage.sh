#!/usr/bin/env bash
# NeoCortex unified service & snapshot manager.
#
# Single entry point for service lifecycle (start/stop) and data persistence
# (snapshot save/list/load/delete).
#
# Usage:
#   ./scripts/manage.sh start [--fresh]    # Start services (persist data by default)
#   ./scripts/manage.sh stop [--all]       # Stop services
#   ./scripts/manage.sh status             # Show running services
#   ./scripts/manage.sh snapshot <cmd>     # Manage snapshots
#   ./scripts/manage.sh help               # Full help
#
# Environment overrides:
#   MCP_PORT=8000   INGESTION_PORT=8001   MAX_WAIT=60

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MCP_PORT="${MCP_PORT:-8000}"
INGESTION_PORT="${INGESTION_PORT:-8001}"
MAX_WAIT="${MAX_WAIT:-60}"
PIDFILE_MCP="$PROJECT_DIR/.mcp.pid"
PIDFILE_INGESTION="$PROJECT_DIR/.ingestion.pid"
LOGDIR="$PROJECT_DIR/log"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"
BACKUPDIR="$PROJECT_DIR/backups"
MEDIA_STORE="$PROJECT_DIR/media_store"

# ---------------------------------------------------------------------------
# Utility functions (ported from launch.sh)
# ---------------------------------------------------------------------------

log()  { printf '\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m==> %s\033[0m\n' "$*" >&2; exit 1; }

pids_on_port() {
    # Try lsof first (macOS + some Linux), fall back to ss+awk (Linux)
    if command -v lsof >/dev/null 2>&1; then
        lsof -ti ":$1" 2>/dev/null || true
    else
        ss -tlnp "sport = :$1" 2>/dev/null \
            | awk 'NR>1 { match($0, /pid=([0-9]+)/, m); if (m[1]) print m[1] }' || true
    fi
}

kill_port() {
    local port="$1"
    local pids
    pids=$(pids_on_port "$port")
    if [[ -n "$pids" ]]; then
        log "Killing existing process(es) on port $port (PIDs: $pids)..."
        echo "$pids" | xargs kill 2>/dev/null || true
        sleep 1
        # Force-kill stragglers
        pids=$(pids_on_port "$port")
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
        if docker compose -f "$COMPOSE_FILE" exec -T postgres \
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
        already=$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
            psql -U neocortex -d neocortex -tAc \
            "SELECT 1 FROM _migration WHERE name = '$name' LIMIT 1;" 2>/dev/null || echo "")
        if [[ "$already" == "1" ]]; then
            continue
        fi
        log "  Applying $name..."
        docker compose -f "$COMPOSE_FILE" exec -T -e PGPASSWORD=neocortex postgres \
            psql -U neocortex -d neocortex < "$f" >/dev/null 2>&1
        docker compose -f "$COMPOSE_FILE" exec -T postgres \
            psql -U neocortex -d neocortex -c \
            "INSERT INTO _migration (name) VALUES ('$name') ON CONFLICT DO NOTHING;" >/dev/null 2>&1 || true
        ok "  Applied $name"
    done
}

require_pg_running() {
    if ! docker compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U neocortex -d neocortex >/dev/null 2>&1; then
        fail "PostgreSQL is not running. Run '$0 start' first."
    fi
}

# ---------------------------------------------------------------------------
# Subcommands (stubs — implemented in later stages)
# ---------------------------------------------------------------------------

do_start() {
    log "start: not yet implemented (Stage 2)"
    exit 1
}

do_stop() {
    log "stop: not yet implemented (Stage 2)"
    exit 1
}

do_snapshot() {
    log "snapshot: not yet implemented (Stages 3-5)"
    exit 1
}

do_status() {
    log "Service status:"
    # PostgreSQL
    if docker compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U neocortex -d neocortex >/dev/null 2>&1; then
        ok "  PostgreSQL:  running"
    else
        log "  PostgreSQL:  stopped"
    fi
    # MCP
    if [[ -f "$PIDFILE_MCP" ]] && kill -0 "$(cat "$PIDFILE_MCP")" 2>/dev/null; then
        ok "  MCP server:  running (PID $(cat "$PIDFILE_MCP"), port $MCP_PORT)"
    else
        log "  MCP server:  stopped"
    fi
    # Ingestion
    if [[ -f "$PIDFILE_INGESTION" ]] && kill -0 "$(cat "$PIDFILE_INGESTION")" 2>/dev/null; then
        ok "  Ingestion:   running (PID $(cat "$PIDFILE_INGESTION"), port $INGESTION_PORT)"
    else
        log "  Ingestion:   stopped"
    fi
    # Logs
    log "  Logs:        $LOGDIR/"
    # Snapshots
    local snap_count=0
    if [[ -d "$BACKUPDIR" ]]; then
        snap_count=$(find "$BACKUPDIR" -name '*.tar.gz' 2>/dev/null | wc -l | tr -d ' ')
    fi
    log "  Snapshots:   $snap_count saved in $BACKUPDIR/"
}

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

usage() {
    cat <<EOF
Usage: $(basename "$0") <command> [options]

Commands:
  start [--fresh]           Start services (persist data by default)
  stop                      Stop MCP + ingestion (PostgreSQL keeps running)
  stop --all                Stop everything including PostgreSQL
  status                    Show running services and DB info
  snapshot save <name>      Save current DB + media to a backup
  snapshot list             List saved snapshots
  snapshot load <name>      Restore DB + media from a snapshot
  snapshot delete <name>    Delete a saved snapshot

Environment:
  MCP_PORT=8000   INGESTION_PORT=8001   MAX_WAIT=60
EOF
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

CMD="${1:-help}"
shift || true
case "$CMD" in
    start)    do_start "$@" ;;
    stop)     do_stop "$@" ;;
    snapshot) do_snapshot "$@" ;;
    status)   do_status ;;
    help|-h|--help) usage ;;
    *)        fail "Unknown command: $CMD. Run '$0 help'." ;;
esac
