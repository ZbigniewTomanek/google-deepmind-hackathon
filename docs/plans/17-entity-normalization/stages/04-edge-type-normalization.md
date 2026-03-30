# Stage 4: Edge Type Normalization

**Goal**: Normalize edge type names to SCREAMING_SNAKE_CASE before storage, reducing type proliferation from format variants.

**Dependencies**: Stage 1 (normalize_edge_type utility)

---

## Rationale

Plan 16.5 found 38 edge types for only 69 edges — a 1:1.8 ratio. Many of these are
format variants of the same semantic relationship:
- `RELATES_TO` vs `RelatesTo` vs `relates_to`
- `HAS_MEMBER` vs `hasMember` vs `Has_Member`

The ontology agent prompt says "Edge type names: SCREAMING_SNAKE" but there's no
enforcement. The `get_or_create_edge_type()` method stores names as-is with a
case-sensitive `UNIQUE` constraint, so `RELATES_TO` and `RelatesTo` create two types.

This stage normalizes edge type names before they reach the database.

---

## Steps

### Step 1: Normalize in `get_or_create_edge_type()` (adapter.py)

At the top of the method, normalize the name:

```python
from neocortex.normalization import normalize_edge_type

async def get_or_create_edge_type(
    self, agent_id: str, name: str, description: str | None = None,
    target_schema: str | None = None,
) -> EdgeType:
    name = normalize_edge_type(name)  # ← Add this line
    # ... rest of method unchanged ...
```

This ensures that regardless of what the ontology agent or librarian produces,
the stored edge type is always SCREAMING_SNAKE_CASE.

### Step 2: Normalize in `get_or_create_node_type()` (adapter.py)

Similarly, normalize node type names to PascalCase:

```python
from neocortex.normalization import normalize_node_type

async def get_or_create_node_type(
    self, agent_id: str, name: str, description: str | None = None,
    target_schema: str | None = None,
) -> NodeType:
    name = normalize_node_type(name)  # ← Add this line
    # ... rest of method unchanged ...
```

### Step 3: Mirror in mock adapter (`mock.py`)

Apply the same normalization calls in the mock's `get_or_create_edge_type()`
and `get_or_create_node_type()` methods.

### Step 4: Add edge type similarity dedup

Beyond format normalization, add a semantic dedup check for near-duplicate edge types.
When `get_or_create_edge_type()` is called with a name that doesn't exist but is
similar to an existing type, prefer the existing type.

In `adapter.py`, after the `ON CONFLICT` insert:

```python
async def get_or_create_edge_type(self, agent_id, name, description=None, target_schema=None):
    name = normalize_edge_type(name)

    # ... existing insert logic ...
    row = await conn.fetchrow(
        """INSERT INTO edge_type (name, description) VALUES ($1, $2)
           ON CONFLICT (name) DO NOTHING RETURNING *""",
        name, description,
    )
    if row is not None:
        return EdgeType(**dict(row))

    # Exact match found (concurrent insert or already existed)
    row = await conn.fetchrow("SELECT * FROM edge_type WHERE name = $1", name)
    if row is not None:
        return EdgeType(**dict(row))

    # Fallback: check for very similar existing type (e.g., after normalization
    # both are SCREAMING_SNAKE but differ by a word)
    # This handles "HAS_MEMBER" vs "HAS_MEMBERS" (singular/plural)
    similar = await conn.fetchrow(
        "SELECT * FROM edge_type WHERE similarity(name, $1) >= 0.8 "
        "ORDER BY similarity(name, $1) DESC LIMIT 1",
        name,
    )
    if similar:
        logger.bind(action_log=True).info(
            "edge_type_similar_reuse",
            requested=name, reused=similar["name"],
            similarity=await conn.fetchval(
                "SELECT similarity($1, $2)", name, similar["name"]
            ),
        )
        return EdgeType(**dict(similar))

    raise RuntimeError(f"Failed to create edge type: {name}")
```

**Note**: Use a high threshold (0.8) to avoid false merges. This catches
`HAS_MEMBER` ↔ `HAS_MEMBERS`, `WORKS_ON` ↔ `WORKED_ON`, etc.

### Step 5: Add edge type normalization tests

In `tests/mcp/test_dedup_safety.py` or a new test file:

```python
# Test: PascalCase → SCREAMING_SNAKE before storage
async def test_edge_type_normalization():
    repo = InMemoryRepository()
    et1 = await repo.get_or_create_edge_type("agent", "RelatesTo")
    et2 = await repo.get_or_create_edge_type("agent", "RELATES_TO")
    assert et1.id == et2.id  # same type
    assert et1.name == "RELATES_TO"

# Test: idempotent normalization
async def test_edge_type_idempotent():
    repo = InMemoryRepository()
    et = await repo.get_or_create_edge_type("agent", "MEMBER_OF")
    assert et.name == "MEMBER_OF"

# Test: node type PascalCase normalization
async def test_node_type_normalization():
    repo = InMemoryRepository()
    nt1 = await repo.get_or_create_node_type("agent", "software_tool")
    nt2 = await repo.get_or_create_node_type("agent", "SoftwareTool")
    assert nt1.id == nt2.id
    assert nt1.name == "SoftwareTool"
```

---

## Verification

```bash
# Run tests
uv run pytest tests/mcp/test_dedup_safety.py -v
uv run pytest tests/ -v --timeout=60

# Verify normalization is idempotent
python -c "
from neocortex.normalization import normalize_edge_type, normalize_node_type
assert normalize_edge_type('RelatesTo') == 'RELATES_TO'
assert normalize_edge_type('RELATES_TO') == 'RELATES_TO'  # idempotent
assert normalize_node_type('software_tool') == 'SoftwareTool'
assert normalize_node_type('SoftwareTool') == 'SoftwareTool'  # idempotent
print('All normalization checks passed')
"
```

Check:
- [ ] Edge types always stored in SCREAMING_SNAKE_CASE
- [ ] Node types always stored in PascalCase
- [ ] Format variants resolve to same type ID
- [ ] Similar edge types (singular/plural) reuse existing type
- [ ] Normalization is idempotent
- [ ] All existing tests pass

---

## Commit

```
feat(normalization): normalize edge/node types before storage

Edge types are now converted to SCREAMING_SNAKE_CASE and node types
to PascalCase in get_or_create_*_type(). Similar edge types (≥0.8
trigram similarity) reuse existing types. Reduces type proliferation
from format variants.
```
