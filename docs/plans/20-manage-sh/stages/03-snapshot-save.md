# Stage 3: `snapshot save`

## Goal

Implement `manage.sh snapshot save <name>` to create a backup archive containing
a pg_dump of the database and a copy of `media_store/`.

## Dependencies

- Stage 2 (need `start` to have a running DB to dump)

## Steps

1. **Implement `do_snapshot()`** as a sub-dispatcher:
   ```bash
   do_snapshot() {
       local subcmd="${1:-help}"
       shift || true
       case "$subcmd" in
           save)   snapshot_save "$@" ;;
           list)   snapshot_list "$@" ;;
           load)   snapshot_load "$@" ;;
           delete) snapshot_delete "$@" ;;
           *)      fail "Unknown snapshot command: $subcmd" ;;
       esac
   }
   ```
   (list/load/delete are stubs for now — `fail "Not implemented yet"`)

2. **Implement `snapshot_save()`**:

   ```
   a. Validate: exactly one arg (the snapshot name)
      - Name must match [a-zA-Z0-9_-]+ (no spaces, no path separators)
   b. require_pg_running
   c. Generate filename: "${name}-$(date +%Y%m%d-%H%M%S)"
   d. Create temp directory for staging
   e. pg_dump via docker exec:
      docker compose -f "$COMPOSE_FILE" exec -T \
        -e PGPASSWORD=neocortex postgres \
        pg_dump -U neocortex -d neocortex --clean --if-exists \
        | gzip > "$tmpdir/db.sql.gz"
   f. Copy media_store/ if it exists and is non-empty:
      if [[ -d "$MEDIA_STORE" ]] && [[ -n "$(ls -A "$MEDIA_STORE" 2>/dev/null)" ]]; then
          cp -r "$MEDIA_STORE" "$tmpdir/media_store"
      fi
   g. Write metadata file "$tmpdir/snapshot.json":
      {
        "name": "<name>",
        "created_at": "<ISO 8601>",
        "pg_version": "<from pg_dump output>",
        "has_media": true/false,
        "original_host": "$(hostname)"
      }
   h. Create tar archive:
      mkdir -p "$BACKUPDIR"
      tar -czf "$BACKUPDIR/${filename}.tar.gz" -C "$tmpdir" .
   i. Cleanup temp dir
   j. Print: ok "Snapshot saved: $BACKUPDIR/${filename}.tar.gz"
      Show file size
   ```

3. **Handle edge cases**:
   - PG not running → `require_pg_running` fails with guidance
   - Empty DB (just migrations) → still valid, just a small dump
   - No media_store dir → skip media, set `has_media: false`
   - Duplicate name → different timestamp makes it unique

## Verification

```bash
# Start services with fresh data
./scripts/manage.sh start --fresh

# Save a snapshot
./scripts/manage.sh snapshot save test-empty
ls -la backups/test-empty-*.tar.gz

# Verify contents
tar -tzf backups/test-empty-*.tar.gz | head -20
# Should show: db.sql.gz, snapshot.json, optionally media_store/

# Verify metadata
tar -xzf backups/test-empty-*.tar.gz -C /tmp/verify-snap snapshot.json
cat /tmp/verify-snap/snapshot.json
rm -rf /tmp/verify-snap
```

## Commit

```
feat(scripts): add snapshot save with pg_dump + media bundling
```
