# Stage 5: Shell Script & Docker Cleanup

**Goal**: Replace the shell-based migration loop in `manage.sh` with a Python invocation and remove the Docker entrypoint volume mount.
**Dependencies**: Stage 3 (runner is the migration authority)

---

## Steps

1. **Update `scripts/manage.sh` `apply_migrations()` function**
   - File: `scripts/manage.sh` (lines 112-133)
   - Replace the entire `for f in "$migration_dir"/*.sql` loop with:
     ```bash
     apply_migrations() {
         log "Applying migrations..."
         uv run python -m neocortex.migrations
         ok "Migrations applied"
     }
     ```
   - Remove the `local migration_dir` variable referencing `migrations/init`.
   - If `manage.sh` runs migrations inside Docker (via `docker compose exec`),
     adjust the command accordingly:
     ```bash
     docker compose -f "$COMPOSE_FILE" exec -T neocortex-mcp \
         uv run python -m neocortex.migrations
     ```
   - Check whether `manage.sh` applies migrations locally or inside the container
     and match the invocation pattern.

2. **Update `docker-compose.yml`**
   - File: `docker-compose.yml` (line 23)
   - Remove the volume mount:
     ```yaml
     # Remove this line:
     - ./migrations/init:/docker-entrypoint-initdb.d
     ```
   - The `postgres` service is now a plain database; the application handles all
     schema setup via `MigrationRunner` at startup.
   - Keep the `pgdata` volume — this only removes the init script mount.

3. **Update `scripts/run_e2e_auth0.sh`**
   - File: `scripts/run_e2e_auth0.sh`
   - This script has its own `apply_migrations()` function (lines 81-100) with
     a duplicate shell loop — it does NOT delegate to `manage.sh`.
   - Replace the entire function body with the same `uv run python -m neocortex.migrations`
     invocation used in `manage.sh`.
   - `scripts/run_e2e.sh` delegates to `manage.sh` (line 122: `"$SCRIPT_DIR/manage.sh" start --fresh`)
     so it needs no changes.

4. **Update any references to `migrations/init/` in scripts or docs**
   - Grep for `migrations/init` across the project.
   - Update paths to `migrations/public/` where applicable.

---

## Verification

- [ ] `grep -r "migrations/init" scripts/` — zero results
- [ ] `grep -r "docker-entrypoint-initdb" docker-compose.yml` — zero results
- [ ] `./scripts/manage.sh start` — services start cleanly (if PG is available)
- [ ] The `apply_migrations` function in `manage.sh` calls `python -m neocortex.migrations`
- [ ] `uv run pytest tests/ -v -x` — all existing tests pass

---

## Commit

`refactor(ops): replace shell migration loop with Python runner, remove Docker initdb mount`
