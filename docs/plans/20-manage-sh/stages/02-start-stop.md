# Stage 2: `start` and `stop` Subcommands

## Goal

Implement service lifecycle with **persist-by-default** semantics. `start` reuses
the existing Docker volume; `start --fresh` wipes and recreates it (old behavior).

## Dependencies

- Stage 1 (skeleton must exist)

## Steps

1. **Implement `do_start()`**:

   Parse `--fresh` flag from args. Core flow:

   ```
   a. mkdir -p "$LOGDIR"
   b. Kill old MCP/ingestion processes (pidfiles + port scan)
   c. IF --fresh:
        docker compose -f "$COMPOSE_FILE" down -v
        log "Starting with fresh volume..."
      ELSE:
        # Just ensure container is running, don't touch volume
        log "Starting with existing data..."
      FI
   d. docker compose -f "$COMPOSE_FILE" up -d postgres
      (with the stale-container retry from launch.sh)
   e. wait_for_postgres
   f. apply_migrations  (idempotent — safe on existing data)
   g. Source .env if present
   h. Start MCP server (background, PID file, log redirect)
      - Same env vars: NEOCORTEX_AUTH_MODE, NEOCORTEX_DEV_TOKENS_FILE, NEOCORTEX_MOCK_DB
   i. Start ingestion server (background, PID file, log redirect)
   j. wait_for_healthy on both endpoints
   k. Print connection info summary
   ```

2. **Implement `do_stop()`**:

   Parse `--all` flag from args.

   ```
   a. Kill MCP process (pidfile + port)
   b. Kill ingestion process (pidfile + port)
   c. IF --all:
        docker compose -f "$COMPOSE_FILE" down  # stop PG, keep volume
        ok "All services stopped (data preserved)."
      ELSE:
        ok "App services stopped. PostgreSQL still running."
      FI
   ```

   Key difference from old `launch.sh do_stop()`: never uses `down -v` (volume preserved).

3. **Connection info output** should match current format:
   ```
   MCP server:       http://127.0.0.1:8000
   Ingestion API:    http://127.0.0.1:8001
   Admin token:      admin-token-neocortex
   Dev token:        dev-token-neocortex

   Stop with:        ./scripts/manage.sh stop
   Logs:             tail -f log/mcp_stdout.log log/ingestion_stdout.log
   ```

## Verification

```bash
# Fresh start works (equivalent to old launch.sh)
./scripts/manage.sh start --fresh
curl -sf http://127.0.0.1:8000/health | grep -q ok
curl -sf http://127.0.0.1:8001/health | grep -q ok

# Stop app services, PG stays
./scripts/manage.sh stop
curl -sf http://127.0.0.1:8000/health && echo "FAIL: MCP still up" || echo "OK: MCP stopped"
docker compose -f docker-compose.yml exec -T postgres pg_isready -U neocortex && echo "OK: PG still up"

# Restart preserves data — migrate a second time without error
./scripts/manage.sh start
curl -sf http://127.0.0.1:8000/health | grep -q ok

# Stop --all takes down PG too
./scripts/manage.sh stop --all
docker compose -f docker-compose.yml ps | grep -q postgres && echo "FAIL" || echo "OK: PG stopped"
```

## Commit

```
feat(scripts): implement start/stop with persist-by-default semantics
```
