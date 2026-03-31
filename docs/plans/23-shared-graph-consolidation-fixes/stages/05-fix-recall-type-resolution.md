# Stage 5: Fix Recall Type Resolution

**Goal**: Ensure `item_type` in recall results always shows the resolved type name instead of "Unknown".
**Dependencies**: None (independent fix)

---

## Background

The recall system has two code paths that build `type_names` maps:

1. **Personal graph recall** (`adapter.py:1560-1565`): `_get_type_names(type_ids)` —
   targeted lookup by IDs collected from matching nodes.

2. **Shared graph recall** (`adapter.py:1810`): `SELECT id, name FROM node_type` —
   fetches ALL types in the schema; dict built at line 1839: `{id: name}`.

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
- Function: `_recall_in_schema` (starts at line 1714)
- Lines to change:
  - **Line ~1810**: `type_rows = await conn.fetch("SELECT id, name FROM node_type")` — **delete** this line
  - **Line ~1839**: `type_names = {int(row["id"]): str(row["name"]) for row in type_rows}` — **delete** this line
  - **Line ~1892**: `type_names.get(int(row["type_id"]), "Unknown")` — **replace** (see below)
- Details:
  - Add a `LEFT JOIN node_type nt ON nt.id = n.type_id` to the node recall query
    and select `COALESCE(nt.name, 'Untyped') AS resolved_type_name`:
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
  - Full list of downstream changes:
    1. Delete the `type_rows` fetch (line ~1810)
    2. Delete the `type_names` dict comprehension (line ~1839)
    3. At line ~1892, replace `type_names.get(int(row["type_id"]), "Unknown")`
       with `row["resolved_type_name"]`
  - **Note**: The LEFT JOIN adds minimal overhead — `node_type` is a small table
    (typically <50 rows) and the join is on primary key.

### 3. Apply same fix to personal-graph recall

- File: `src/neocortex/db/adapter.py`
- Lines: ~1555-1625 (personal recall code path)
- Details:
  - `_get_type_names` (line 1981) iterates type IDs and calls
    `self._graph.get_node_type(type_id)` for each. Missing IDs return `None`
    and are simply omitted from the dict — so the "Unknown" fallback at line 1624
    fires for any orphaned type.
  - Apply the same LEFT JOIN approach to the personal recall query for consistency:
    add `LEFT JOIN node_type nt ON nt.id = n.type_id` and select
    `COALESCE(nt.name, 'Untyped') AS resolved_type_name`.
  - Then delete the `_get_type_names` call at line 1565, and replace
    `type_names.get(int(hit["type_id"]), "Unknown")` at line 1624 with
    `hit["resolved_type_name"]`.

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
