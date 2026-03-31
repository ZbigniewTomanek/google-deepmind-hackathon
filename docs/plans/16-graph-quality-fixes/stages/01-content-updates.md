# Stage 1: Fix Node Content Updates

**Goal**: Ensure node content reflects the latest extraction, not the first-ever value.

**Dependencies**: None (independent fix)

**Priority**: P0

---

## Root Cause Analysis

The content-never-updates bug has **two contributing factors**:

### Factor A: Librarian drops descriptions for existing entities

`NormalizedEntity` has `description: str | None = None` (`schemas.py:64`).
When the librarian marks an entity as `is_new=False` (matching a known node name),
the LLM often returns `description=None` — it interprets "this entity already exists"
as "no need to re-describe it."

The pipeline then calls:
```python
upsert_node(content=entity.description)  # entity.description is None
```
→ `adapter.py:470`: `COALESCE(NULL, content)` → keeps old content.

### Factor B: COALESCE semantics are ambiguous

`COALESCE($1, content)` conflates two meanings of NULL:
- "I have no new content" (don't update) — current behavior
- "I want to clear the content" (set to NULL) — impossible to express

The current SQL is technically correct for the "don't update" case,
but the pipeline never intentionally passes NULL-to-mean-don't-update.
When the extractor *does* provide a description and the librarian preserves it,
COALESCE works fine. The problem is that the librarian drops it.

### Evidence

From Plan 15, Stage 2:
> "1 Alice node (dedup works). Content NOT updated (COALESCE keeps old)."

The extraction pipeline at `pipeline.py:200-209` always calls `upsert_node`,
so the update path IS reached. The issue is `entity.description` being None.

---

## Steps

### 1.1 Update librarian prompt to require descriptions

**File**: `src/neocortex/extraction/agents.py`
**Lines**: 259-264 (librarian rules in `inject_context`)

Add a rule requiring descriptions for all entities, including existing ones:

```
"- ALWAYS provide a description for every entity, even if is_new=False.",
"- For existing entities, write an UPDATED description that incorporates new information from the text.",
"- The description becomes the entity's canonical summary — make it comprehensive and current.",
```

This is the primary fix. The LLM needs explicit instruction to provide descriptions.

### 1.2 Add pipeline fallback: use extractor description when librarian's is None

**File**: `src/neocortex/extraction/pipeline.py`
**Lines**: 193-210 (entity persistence loop)

Before calling `upsert_node`, if `entity.description` is None, fall back to the
extractor's description for the same entity name. This is a safety net in case the
librarian still occasionally returns None despite the prompt change.

```python
# Build fallback map from extractor output
extractor_descriptions = {
    e.name: e.description
    for e in extraction_result.output.entities
    if e.description
}

# In the persist loop:
description = entity.description or extractor_descriptions.get(entity.name)
node = await repo.upsert_node(
    agent_id=agent_id,
    name=entity.name,
    type_id=node_type.id,
    content=description,  # fallback to extractor
    ...
)
```

Note: The `_persist_payload` function doesn't currently have access to
`extraction_result`. Either pass it as a parameter, or build the fallback
map in `run_extraction_pipeline` and pass it through. The simpler approach
is to add an `extractor_descriptions` parameter to `_persist_payload`.

### 1.3 Change adapter.py SQL to always overwrite content when provided

**File**: `src/neocortex/db/adapter.py`
**Lines**: 468-471

The COALESCE is already correct (prefers new when non-NULL), but let's make the
intent explicit with a comment and ensure consistency:

```sql
-- Content: prefer new value, keep old only when new is NULL
content = COALESCE($1, content),
```

No SQL change needed — COALESCE semantics are correct for our use case.
The fix is upstream (steps 1.1 and 1.2).

### 1.4 Fix graph_service.py fallback path

**File**: `src/neocortex/graph_service.py`
**Lines**: 160-163

Same COALESCE pattern exists in the fallback `update_node`. Add a comment for
consistency. The `adapter.py:438` fallback path uses `content or node.content`
which has the same semantics.

### 1.5 Update mock.py for behavior parity

**File**: `src/neocortex/db/mock.py`
**Lines**: 401-403

The mock uses `content or node.content`. Verify this matches adapter behavior.
Note: `""` (empty string) is falsy in Python but non-NULL in PostgreSQL.
Consider using `content if content is not None else node.content` for exact parity.

### 1.6 Add test: content updates on upsert

**File**: `tests/test_content_update.py` (new file, or add to existing test file)

Test scenario:
1. Create node with content "Alice is on billing team"
2. Upsert same node (same name, same type_id) with content "Alice is on auth team"
3. Assert node content == "Alice is on auth team"
4. Upsert same node with content=None
5. Assert node content still == "Alice is on auth team" (preserved)

Test both mock and adapter paths.

---

## Verification

```bash
# Run the new test
uv run pytest tests/test_content_update.py -v

# Run full test suite to check for regressions
uv run pytest tests/ -v

# Manual smoke test with mock DB
NEOCORTEX_MOCK_DB=true uv run python -c "
# Quick script to verify upsert behavior through the protocol
"
```

- [ ] New test passes: content updates when new content provided
- [ ] New test passes: content preserved when new content is None
- [ ] Existing tests pass (no regressions)
- [ ] Librarian prompt includes description requirement

---

## Commit

```
fix(extraction): ensure node content updates on re-extraction

Librarian agent now explicitly required to provide descriptions for all
entities including existing ones. Pipeline falls back to extractor
description when librarian returns None. Fixes stale content issue where
COALESCE(NULL, old_content) preserved first-ever value indefinitely.

Closes: Plan 15 Issue 1
```
