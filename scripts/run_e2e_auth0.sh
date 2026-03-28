#!/usr/bin/env bash
# E2E test runner for Auth0 integration.
#
# Starts PostgreSQL + MCP server + ingestion server in auth0 mode,
# runs the Auth0 E2E test, and tears everything down on exit.
#
# Requires .env.auth0 with valid Auth0 credentials.
#
# Usage:
#   ./scripts/run_e2e_auth0.sh
#
# Environment overrides:
#   KEEP_RUNNING=1    keep services up after test
#   MAX_WAIT=60       seconds to wait for readiness

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

MCP_BASE_URL="${NEOCORTEX_BASE_URL:-http://127.0.0.1:8000}"
INGESTION_BASE_URL="${NEOCORTEX_INGESTION_BASE_URL:-http://127.0.0.1:8001}"
MAX_WAIT="${MAX_WAIT:-60}"
MCP_PID=""
INGESTION_PID=""

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
    for pid_var in MCP_PID INGESTION_PID; do
        local pid="${!pid_var}"
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
            log "Stopped process (PID $pid)."
        fi
    done
    log "PostgreSQL container left running (use 'docker compose stop postgres' to stop)."
    exit "$exit_code"
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

wait_for_postgres() {
    log "Waiting for PostgreSQL to be ready..."
    local elapsed=0
    while (( elapsed < MAX_WAIT )); do
        if docker compose exec -T postgres pg_isready -U neocortex -d neocortex >/dev/null 2>&1; then
            ok "PostgreSQL is ready (${elapsed}s)."
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    fail "PostgreSQL did not become ready within ${MAX_WAIT}s."
}

apply_migrations() {
    log "Applying any missing migrations..."
    local migration_dir="$PROJECT_DIR/migrations/init"
    for f in "$migration_dir"/*.sql; do
        local name
        name="$(basename "$f")"
        local already_applied
        already_applied=$(docker compose exec -T postgres psql -U neocortex -d neocortex -tAc \
            "SELECT 1 FROM _migration WHERE name = '$name' LIMIT 1;" 2>/dev/null || echo "")
        if [[ "$already_applied" == "1" ]]; then
            continue
        fi
        log "  Applying $name..."
        docker compose exec -T postgres psql -U neocortex -d neocortex -f "/docker-entrypoint-initdb.d/$name" >/dev/null 2>&1 \
            || docker compose exec -T -e PGPASSWORD=neocortex postgres psql -U neocortex -d neocortex < "$f" 2>&1
        docker compose exec -T postgres psql -U neocortex -d neocortex -c \
            "INSERT INTO _migration (name) VALUES ('$name') ON CONFLICT DO NOTHING;" >/dev/null 2>&1 || true
        ok "  Applied $name"
    done
}

# --- main ------------------------------------------------------------------

trap cleanup EXIT INT TERM
cd "$PROJECT_DIR"

# Check .env.auth0 exists
if [[ ! -f "$PROJECT_DIR/.env.auth0" ]]; then
    fail ".env.auth0 not found. Create it with Auth0 credentials (see docs/plans/12-auth0-integration.md)."
fi

# Source Auth0 credentials
log "Loading Auth0 configuration from .env.auth0..."
set -a; source "$PROJECT_DIR/.env.auth0"; set +a

# Source .env if present (for GOOGLE_API_KEY etc.)
if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a; source "$PROJECT_DIR/.env"; set +a
fi

# Verify required Auth0 env vars
for var in NEOCORTEX_AUTH0_DOMAIN NEOCORTEX_AUTH0_AUDIENCE NEOCORTEX_AUTH0_M2M_CLIENT_ID NEOCORTEX_AUTH0_M2M_CLIENT_SECRET NEOCORTEX_AUTH0_CLIENT_ID NEOCORTEX_AUTH0_CLIENT_SECRET; do
    if [[ -z "${!var:-}" ]]; then
        fail "Missing required env var: $var (check .env.auth0)"
    fi
done

log "Auth0 domain: $NEOCORTEX_AUTH0_DOMAIN"
log "Auth0 audience: $NEOCORTEX_AUTH0_AUDIENCE"

# Start PostgreSQL
log "Ensuring PostgreSQL is running via docker compose..."
docker compose up -d postgres 2>&1 || {
    log "Container conflict — removing stale container and retrying..."
    docker rm -f neocortex-postgres 2>/dev/null || true
    docker compose up -d postgres 2>&1
}
wait_for_postgres
apply_migrations

# Kill any existing servers on our ports
for port in 8000 8001; do
    existing_pids=$(lsof -ti ":$port" 2>/dev/null || true)
    if [[ -n "$existing_pids" ]]; then
        log "Killing existing processes on port $port (PIDs: $(echo $existing_pids | tr '\n' ' '))..."
        echo "$existing_pids" | xargs kill 2>/dev/null || true
    fi
done
sleep 2  # Let ports be released

# Start services in auth0 mode
log "Starting NeoCortex MCP server (port 8000, auth0 mode)..."
NEOCORTEX_AUTH_MODE=auth0 \
NEOCORTEX_MOCK_DB=false \
uv run python -m neocortex &
MCP_PID=$!

log "Starting NeoCortex ingestion server (port 8001, auth0 mode)..."
NEOCORTEX_AUTH_MODE=auth0 \
NEOCORTEX_MOCK_DB=false \
uv run python -m neocortex.ingestion &
INGESTION_PID=$!

wait_for_healthy "$MCP_BASE_URL/health" "$MAX_WAIT"
wait_for_healthy "$INGESTION_BASE_URL/health" "$MAX_WAIT"

log "Running Auth0 E2E test..."
uv run python scripts/e2e_auth0_test.py

ok "AUTH0 E2E TEST PASSED"
