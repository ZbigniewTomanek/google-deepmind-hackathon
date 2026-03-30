# Stage 4: Adapter Safety Nets

**Goal**: Add defense-in-depth deduplication at the database adapter layer to catch LLM mistakes that the tool-equipped librarian misses.

**Dependencies**: Stage 3 (tool-driven pipeline is the primary mechanism; this stage adds fallbacks)

**Priority**: P1

---

## Why This Stage Exists

The tool-equipped librarian (Stages 2-3) is the primary fix for dedup and type
stability. But LLMs make mistakes — the librarian might:
- Call `create_or_update_node` with a different type than the existing node
- Create a duplicate edge because it didn't call `get_edges_between` first
- Be used in fallback mode (`_persist_payload`) where tools aren't available

The adapter layer should catch these cases as a safety net, even though the
librarian should handle them correctly most of the time.

---

## Steps

### 4.1 Name-primary node dedup in adapter

**File**: `src/neocortex/db/adapter.py`
**Lines**: 452-515

Change `upsert_node` to use two-phase lookup:

```python
async with self._scoped_conn(schema_name, agent_id, target_schema) as conn:
    # Phase 1: Look up by name only
    rows = await conn.fetch(
        "SELECT id, type_id, name, content, properties, source, importance, "
        "created_at, updated_at "
        "FROM node WHERE lower(name) = lower($1) AND forgotten = false",
        name,
    )

    row = None
    if rows:
        # Phase 2: Prefer exact (name, type_id) match
        for r in rows:
            if r["type_id"] == type_id:
                row = r
                break
        # If no exact match but exactly 1 node exists, reuse it
        if row is None and len(rows) == 1:
            row = rows[0]
            logger.bind(action_log=True).info(
                "node_type_drift_caught",
                name=name,
                existing_type_id=row["type_id"],
                requested_type_id=type_id,
                agent_id=agent_id,
            )

    if row is not None:
        # UPDATE path (unchanged from current)
        ...
    else:
        # INSERT path (unchanged)
        ...
```

### 4.2 Source-target primary edge dedup in adapter

**File**: `src/neocortex/db/adapter.py`
**Lines**: 573-595

Add pre-check before the INSERT...ON CONFLICT:

```python
async with self._scoped_conn(schema_name, agent_id, target_schema) as conn:
    # Check existing edges between this source-target pair
    existing = await conn.fetch(
        "SELECT id, type_id, weight, properties FROM edge "
        "WHERE source_id = $1 AND target_id = $2",
        source_id, target_id,
    )

    if len(existing) == 1 and existing[0]["type_id"] != type_id:
        # Single edge with different type → drift, update the existing one
        old = existing[0]
        merged = json.loads(old["properties"]) if isinstance(old["properties"], str) else dict(old["properties"])
        merged.update(props)
        row = await conn.fetchrow(
            "UPDATE edge SET type_id = $1, weight = $2, "
            "properties = $3::jsonb, last_reinforced_at = now() "
            "WHERE id = $4 RETURNING *",
            type_id, weight, json.dumps(merged), old["id"],
        )
        logger.bind(action_log=True).info(
            "edge_type_drift_caught",
            source_id=source_id, target_id=target_id,
            old_type_id=old["type_id"], new_type_id=type_id,
        )
    else:
        # Normal path: INSERT...ON CONFLICT
        row = await conn.fetchrow(
            """INSERT INTO edge (source_id, target_id, type_id, weight, properties)
               VALUES ($1, $2, $3, $4, $5::jsonb)
               ON CONFLICT (source_id, target_id, type_id)
               DO UPDATE SET weight = $4, properties = edge.properties || $5::jsonb
               RETURNING *""",
            source_id, target_id, type_id, weight, props_json,
        )
```

### 4.3 Mirror in mock.py

**File**: `src/neocortex/db/mock.py`

Apply the same two-phase lookup logic to both `upsert_node` and `upsert_edge`
in InMemoryRepository.

### 4.4 Mirror in fallback path

**File**: `src/neocortex/db/adapter.py`
**Lines**: 429-450 (node fallback), 535-570 (edge fallback)

Apply name-primary dedup to the no-pool/no-router fallback paths.

### 4.5 Add monitoring queries

After these safety nets are in place, the `node_type_drift_caught` and
`edge_type_drift_caught` log entries become a health metric. If they fire
frequently, it means the librarian agent's prompts need tuning.

### 4.6 Add tests

- Same name, different type, 1 existing → reuses existing node (no duplicate)
- Same name, different type, 2+ existing → matches by type (homonym case)
- Same source-target, different edge type, 1 existing → updates existing edge
- Same source-target, different edge type, 2+ existing → adds normally
- Content and properties correctly merged in both cases

---

## Verification

```bash
uv run pytest tests/ -v -k "dedup or safety"
uv run pytest tests/ -v
```

- [ ] No duplicate nodes created for same name with different type (single existing)
- [ ] Homonym case preserved (multiple existing nodes with same name)
- [ ] No duplicate edges for same source-target with different type (single existing)
- [ ] Type drift logged to audit trail
- [ ] Mock behavior matches adapter

---

## Commit

```
fix(db): adapter-level dedup safety nets for type drift

Node upsert uses name-primary two-phase lookup: reuses single existing node
regardless of type_id mismatch. Edge upsert checks source-target pair first:
updates single existing edge's type rather than creating duplicate. Both
log drift events for monitoring librarian prompt effectiveness.

Defense-in-depth for Plan 15 Issues 2, 3, 5
```
