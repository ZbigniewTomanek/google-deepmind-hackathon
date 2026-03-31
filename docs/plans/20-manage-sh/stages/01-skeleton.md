# Stage 1: Script Skeleton + Shared Utilities

## Goal

Create `scripts/manage.sh` with argument parsing, help text, and all shared utility
functions extracted from `launch.sh`.

## Dependencies

None.

## Steps

1. **Create `scripts/manage.sh`** with `#!/usr/bin/env bash`, `set -euo pipefail`.

2. **Port shared config variables** from `launch.sh`:
   ```bash
   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
   PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
   MCP_PORT="${MCP_PORT:-8000}"
   INGESTION_PORT="${INGESTION_PORT:-8001}"
   MAX_WAIT="${MAX_WAIT:-60}"
   PIDFILE_MCP="$PROJECT_DIR/.mcp.pid"
   PIDFILE_INGESTION="$PROJECT_DIR/.ingestion.pid"
   LOGDIR="$PROJECT_DIR/log"
   BACKUPDIR="$PROJECT_DIR/backups"      # NEW
   MEDIA_STORE="$PROJECT_DIR/media_store" # NEW
   COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"
   ```

3. **Port utility functions** verbatim from `launch.sh`:
   - `log()`, `ok()`, `fail()` — colored output
   - `pids_on_port()` — find PIDs on a port (lsof/ss)
   - `kill_port()` — kill processes on a port
   - `kill_pidfile()` — kill process tracked by PID file
   - `wait_for_healthy()` — poll HTTP endpoint
   - `wait_for_postgres()` — poll `pg_isready`
   - `apply_migrations()` — idempotent migration loop

4. **Add a new helper** `require_pg_running()`:
   ```bash
   require_pg_running() {
       if ! docker compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U neocortex -d neocortex >/dev/null 2>&1; then
           fail "PostgreSQL is not running. Run '$0 start' first."
       fi
   }
   ```

5. **Implement subcommand dispatch** via positional args:
   ```bash
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
   ```

6. **Implement `usage()`** showing all subcommands:
   ```
   Usage: manage.sh <command> [options]

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
   ```

7. **Implement `do_status()`** — lightweight status check:
   - Check if PG container is running
   - Check if MCP / ingestion PIDs are alive
   - Print ports and log locations

8. **`chmod +x scripts/manage.sh`**

## Verification

```bash
# Script parses without error
bash -n scripts/manage.sh

# Help works
./scripts/manage.sh help

# Unknown command fails gracefully
./scripts/manage.sh bogus 2>&1 | grep -q "Unknown command"

# Status works (even if nothing is running)
./scripts/manage.sh status
```

## Commit

```
feat(scripts): add manage.sh skeleton with subcommand dispatch and shared utilities
```
