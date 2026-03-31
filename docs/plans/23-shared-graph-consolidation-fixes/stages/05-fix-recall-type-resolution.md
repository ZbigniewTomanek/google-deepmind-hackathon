# Stage 5: Fix Recall Type Resolution

**Goal**: Ensure `item_type` in recall results always shows the resolved type name instead of "Unknown".
**Dependencies**: None (independent fix)

---

## Background

The recall system has two code paths that build `type_names` maps:

1. **Personal graph recall** (`adapter.py:1562-1565`): `_get_type_names(type_ids)` —
   targeted lookup by IDs collected from matching nodes.

2. **Shared graph recall** (`adapter.py:1839`): `SELECT id, name FROM node_type` —
   fetches ALL types in the schema, builds `{id: name}` dict.

The "Unknown" fallback at `adapter.py:1624` and `adapter.py:1892`:
```python
item_type=type_names.get(int(hit["type_id"]), "Unknown")
```

Fires when a node's `type_id` has no matching entry in `node_type`. Possible causes:
- `cleanup_empty_types` deleted a type that still has referencing nodes
- Type created in one transaction, node in another, with a visibility gap
- Auto-increment ID collision across schemas (less likely)

---

## Steps

### 1. Run diagnostic query to confirm root cause

- See: `resources/diagnostic-queries.md` — Query D1
- Run against a test database (or add to the test in Stage 6) to determine whether
  orphaned type IDs actually exist.

### 2. Add JOIN-based type resolution to shared-graph recall

- File: `src/neocortex/db/adapter.py`
- Lines: ~1790-1840 (shared recall query and type resolution)
- Details:
  - Find the recall query that fetches `node_rows`. It currently fetches `type_id`
    from the `node` table and resolves it separately via `type_names` dict.
  - **Change**: Add a LEFT JOIN to `node_type` in the recall query itself:
    ```sql
    SELECT n.id, n.name, n.content, n.type_id,
           COALESCE(nt.name, 'Untyped') AS resolved_type_name,
           n.source, n.importance, n.access_count, n.last_accessed_at,
           n.created_at, n.updated_at,
           ...
    FROM node n
    LEFT JOIN node_type nt ON nt.id = n.type_id
    WHERE n.forgotten = false
      AND ...
    ```
  - Then use `row["resolved_type_name"]` instead of `type_names.get(...)`.
  - This eliminates the separate type lookup AND handles orphaned type IDs.
  - **Note**: The LEFT JOIN adds minimal overhead — `node_type` is a small table
    (typically <50 rows) and the join is on primary key.

### 3. Apply same fix to personal-graph recall

- File: `src/neocortex/db/adapter.py`
- Lines: ~1555-1625 (personal recall code path)
- Details:
  - The `_get_type_names` approach at line 1565 works differently — it collects
    type IDs from results and does a batch lookup.
  - Apply the same JOIN approach for consistency, or verify that `_get_type_names`
    correctly handles all IDs (check its implementation).
  - If `_get_type_names` already handles missing IDs gracefully (returns empty dict
    for missing), the "Unknown" fallback is the only issue. Change the fallback
    string to something more informative or use the JOIN approach.

### 4. Protect against `cleanup_empty_types` race condition

- File: `src/neocortex/db/adapter.py` (or wherever `cleanup_empty_types` lives)
- Details:
  - Verify the cleanup query checks for actual zero references:
    ```sql
    DELETE FROM node_type
    WHERE id NOT IN (SELECT DISTINCT type_id FROM node WHERE type_id IS NOT NULL)
      AND created_at < now() - interval '5 minutes'
    ```
  - If the current query is different (e.g., counts nodes differently), fix it.
  - This prevents deleting types that still have referencing nodes.

---

## Verification

- [ ] Run diagnostic query D1 — understand whether orphaned types exist
- [ ] Read recall code and confirm: type names resolved via JOIN or equivalent
- [ ] `uv run pytest tests/ -v -k "test_recall"` — tests pass
- [ ] `uv run pytest tests/ -v` — full suite passes

---

## Commit

`fix(recall): resolve item_type via JOIN instead of separate lookup, eliminating "Unknown" types`
