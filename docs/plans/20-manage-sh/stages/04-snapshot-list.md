# Stage 4: `snapshot list` and `snapshot info`

## Goal

Implement `manage.sh snapshot list` to enumerate saved snapshots with useful metadata,
and optional `snapshot info <name>` for detailed inspection.

## Dependencies

- Stage 3 (need saved snapshots to list)

## Steps

1. **Implement `snapshot_list()`**:

   ```
   a. Check if $BACKUPDIR exists and has .tar.gz files
      - If empty: "No snapshots found. Create one with: $0 snapshot save <name>"
   b. For each .tar.gz in $BACKUPDIR (sorted by mtime, newest first):
      - Extract snapshot.json to a temp location (tar -xzf ... snapshot.json)
      - Read name, created_at, has_media from JSON
      - Get file size (du -h or stat)
      - Print formatted row
   c. Output format:
      NAME                      DATE                 SIZE    MEDIA
      my-demo-20260331-143022   2026-03-31 14:30:22  42MB    yes
      clean-seed-20260328-0900  2026-03-28 09:00:15  1.2MB   no
   ```

2. **JSON parsing**: Use `python3 -c` for portable JSON extraction (already available
   since the project uses Python). Fallback: `grep`/`sed` for simple fields.

   ```bash
   local meta
   meta=$(tar -xzf "$f" -O snapshot.json 2>/dev/null)
   local name created_at has_media
   name=$(echo "$meta" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])")
   created_at=$(echo "$meta" | python3 -c "import sys,json; print(json.load(sys.stdin)['created_at'])")
   has_media=$(echo "$meta" | python3 -c "import sys,json; print('yes' if json.load(sys.stdin).get('has_media') else 'no')")
   ```

3. **Handle edge cases**:
   - No backups directory → print empty message
   - Corrupted tar.gz → skip with warning
   - Missing snapshot.json → show filename and "?" for metadata fields

## Verification

```bash
# Create two snapshots (need running services from Stage 2)
./scripts/manage.sh snapshot save alpha
sleep 2
./scripts/manage.sh snapshot save beta

# List shows both
./scripts/manage.sh snapshot list
# Should show two entries with dates and sizes

# Empty case (after deleting backups/)
mv backups backups.bak
./scripts/manage.sh snapshot list
# Should show "No snapshots found" message
mv backups.bak backups
```

## Commit

```
feat(scripts): add snapshot list with metadata display
```
