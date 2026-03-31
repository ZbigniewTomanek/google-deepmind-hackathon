# Stage 4: Graceful Update Failure Handling

**Goal**: Handle `UPDATE 0 rows` in `upsert_node` gracefully instead of raising `RuntimeError`, enabling the extraction pipeline to continue even when a single node update fails unexpectedly.
**Dependencies**: Stage 1 (primary cause of UPDATE failures removed), Stage 2 (content merging in place)

---

## Steps

### 1. Replace RuntimeError with fallback INSERT in upsert_node

- File: `src/neocortex/db/adapter.py`
- Lines: 728-729 (`if updated_row is None: raise RuntimeError("Failed to update node")`)
- Details:
  - **Current behavior**: If UPDATE matches 0 rows, raise RuntimeError. This crashes
    the entire librarian agent.
  - **New behavior**: If UPDATE matches 0 rows, log a warning and fall through to
    INSERT a new node. This handles edge cases like:
    - Concurrent deletion of the target node between SELECT and UPDATE
    - Race conditions in high-concurrency extraction
  - Implementation: Replace lines 728-729 with:
    ```python
    if updated_row is None:
        logger.bind(action_log=True).warning(
            "upsert_node_update_missed",
            node_id=row["id"],
            name=name,
            agent_id=agent_id,
            target_schema=target_schema,
            msg="UPDATE matched 0 rows (concurrent delete?), falling back to INSERT",
        )
        row = None  # Reset to trigger INSERT branch
    ```
  - Then adjust the control flow so that when `row` is reset to `None`, execution
    falls through to the INSERT branch (line 735 onward). This may require
    restructuring the if/else into a loop or re-checking `row`:
    ```python
    if updated_row is None:
        # ... warning log ...
        # Fall through to INSERT below
    else:
        d = dict(updated_row)
        if isinstance(d.get("properties"), str):
            d["properties"] = json.loads(d["properties"])
        return Node(**d)

    # INSERT path (reached when row was None initially OR update missed)
    new_row = await conn.fetchrow(...)
    ```

### 2. Check upsert_edge for same pattern

- File: `src/neocortex/db/adapter.py`
- Details:
  - Find the `upsert_edge` method. Check if it has a similar RuntimeError pattern.
  - The edge upsert likely uses `ON CONFLICT (source_id, target_id, type_id) DO UPDATE`
    which handles the upsert atomically in SQL — no separate SELECT + UPDATE.
  - If so, no change needed for edges.
  - If there IS a RuntimeError on edge update failure, apply the same fallback pattern.

### 3. Verify no other RuntimeError("Failed to update") patterns exist

- Grep: `RuntimeError.*update` across `src/neocortex/db/adapter.py`
- Fix any other instances with the same graceful pattern.

---

## Verification

- [ ] Read `adapter.py` upsert_node and confirm: no RuntimeError on UPDATE 0 rows
- [ ] Grep for `RuntimeError.*update` in adapter.py — should be zero
- [ ] `uv run pytest tests/ -v -k "test_upsert"` — tests pass
- [ ] `uv run pytest tests/ -v` — full suite passes

---

## Commit

`fix(adapter): handle UPDATE 0 rows gracefully in upsert_node instead of crashing`
