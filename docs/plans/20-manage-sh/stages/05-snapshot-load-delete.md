# Stage 5: `snapshot load` and `snapshot delete`

## Goal

Implement restore-from-snapshot and snapshot cleanup commands.

## Dependencies

- Stage 3 + 4 (need save and list working)

## Steps

### `snapshot_load()`

1. **Resolve snapshot file**:
   ```
   a. Take one arg: snapshot name (can be full filename or just the base name)
   b. Find matching .tar.gz in $BACKUPDIR:
      - Exact match: "${name}.tar.gz"
      - Prefix match: "${name}*.tar.gz" (pick most recent if multiple)
      - No match → fail with "Snapshot not found" + suggest `snapshot list`
   ```

2. **Pre-flight checks**:
   - `require_pg_running` (need PG to restore into)
   - If MCP/ingestion are running, auto-stop them (print a message):
     ```
     log "Stopping app services for clean restore..."
     kill_pidfile "$PIDFILE_MCP"
     kill_pidfile "$PIDFILE_INGESTION"
     kill_port "$MCP_PORT"
     kill_port "$INGESTION_PORT"
     ```

3. **Restore flow**:
   ```
   a. Extract archive to temp dir
   b. Restore DB (pipe pattern — do NOT use process substitution with docker exec):
      gunzip -c "$tmpdir/db.sql.gz" | \
        docker compose -f "$COMPOSE_FILE" exec -T \
          -e PGPASSWORD=neocortex postgres \
          psql -U neocortex -d neocortex

      Note: pg_dump --clean --if-exists generates DROP IF EXISTS + CREATE
      statements, so this replaces existing data.
   c. Restore media (if present in snapshot):
      if [[ -d "$tmpdir/media_store" ]]; then
          rm -rf "$MEDIA_STORE"
          cp -r "$tmpdir/media_store" "$MEDIA_STORE"
          ok "Media store restored"
      fi
   d. Cleanup temp dir
   e. ok "Snapshot loaded: <name>"
   f. Suggest: "Run '$0 start' to bring services back up."
   ```

4. **Safety**: The `--clean --if-exists` flags in the dump mean restore
   drops and recreates objects. This is safe for our use case (full DB replace).

### `snapshot_delete()`

1. **Resolve** snapshot file (same logic as load)
2. **Confirm**: Print snapshot name + size, ask "Delete? [y/N]"
   - Accept `--yes` / `-y` flag to skip confirmation
3. **Remove** the .tar.gz file
4. **Print** confirmation

## Verification

```bash
# Setup: start fresh, save a snapshot, add some data
./scripts/manage.sh start --fresh
./scripts/manage.sh snapshot save before-data

# (Optionally ingest something via the API to make data differ)

# Save post-data snapshot
./scripts/manage.sh snapshot save after-data

# Load the "before" snapshot
./scripts/manage.sh stop
./scripts/manage.sh snapshot load before-data --force
./scripts/manage.sh start
# DB should be in the "before" state

# Delete a snapshot
./scripts/manage.sh snapshot delete after-data --yes
./scripts/manage.sh snapshot list
# Should only show "before-data"

# Error cases
./scripts/manage.sh snapshot load nonexistent 2>&1 | grep -q "not found"
./scripts/manage.sh snapshot delete nonexistent 2>&1 | grep -q "not found"
```

## Commit

```
feat(scripts): add snapshot load and delete commands
```
