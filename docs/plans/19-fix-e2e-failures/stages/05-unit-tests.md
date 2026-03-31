# Stage 5: Unit Tests

**Goal**: Add targeted unit tests for all fixes from Stages 1-4 to prevent regressions.
**Dependencies**: Stages 1-4 must be DONE

---

## Steps

### 1. Permission grant test for `_ensure_schema`

**File**: `tests/unit/test_domain_routing.py` (existing or new)

Test that `_ensure_schema` grants permissions for both new and existing schemas:

```python
async def test_ensure_schema_grants_permissions_for_existing_schema():
    """_ensure_schema must grant write permissions even when schema already exists."""
    # Setup: create a domain router with a schema_mgr that reports schema exists
    # Act: call _ensure_schema for an agent
    # Assert: permissions.grant was called with the agent_id and schema_name
```

Test that the permission denial log fires at WARNING level:

```python
async def test_routing_logs_permission_denial_at_warning():
    """Permission denial must log at WARNING, not DEBUG."""
```

### 2. Type name rejection tests

**File**: `tests/unit/test_normalization.py` (add to existing)

Add test cases for the 4 corrupted types:

```python
@pytest.mark.parametrize("bad_name", [
    "DatasetNoteTheSearchResultsShowed" + "x" * 400,  # 440+ chars
    "OperationbrCreateOrUpdate" + "x" * 300,            # 300+ chars
    "A" * 61,                                            # Just over limit
])
def test_normalize_node_type_rejects_too_long(bad_name):
    with pytest.raises(ValueError, match="too long"):
        normalize_node_type(bad_name)

@pytest.mark.parametrize("bad_name", [
    "FeatureMergesWithEntityObjectId167",  # 7 PascalCase segments
    "ThisIsAVeryLongCompoundTypeName",      # 6 segments
])
def test_normalize_node_type_rejects_too_many_segments(bad_name):
    with pytest.raises(ValueError, match="too many segments"):
        normalize_node_type(bad_name)

def test_normalize_node_type_enforces_uppercase_start():
    # After normalization, single lowercase word should be capitalized
    assert normalize_node_type("algorithm") == "Algorithm"
    # But the regex must require uppercase start
    # (The normalization code handles this via capitalize())

@pytest.mark.parametrize("good_name,expected", [
    ("Algorithm", "Algorithm"),
    ("SoftwareSystem", "SoftwareSystem"),
    ("Bug", "Bug"),
    ("ParseHumanNameUDX", "ParseHumanNameUDX"),
])
def test_normalize_node_type_accepts_valid(good_name, expected):
    assert normalize_node_type(good_name) == expected
```

### 3. Pydantic validator tests

**File**: `tests/unit/test_extraction_schemas.py` (new file)

```python
from neocortex.extraction.schemas import ProposedNodeType, ExtractedEntity
from pydantic import ValidationError

def test_proposed_node_type_rejects_long_name():
    with pytest.raises(ValidationError):
        ProposedNodeType(name="x" * 61)

def test_extracted_entity_temporal_fields():
    e = ExtractedEntity(
        name="Metaphone3 Hybrid",
        type_name="Algorithm",
        supersedes="Metaphone3",
        temporal_signal="SUPERSEDES",
    )
    assert e.supersedes == "Metaphone3"
    assert e.temporal_signal == "SUPERSEDES"

def test_extracted_entity_temporal_fields_default_none():
    e = ExtractedEntity(name="X", type_name="Y")
    assert e.supersedes is None
    assert e.temporal_signal is None
```

### 4. Add edge type length and word-count rejection tests

**File**: `tests/unit/test_normalization.py` (add to existing)

```python
@pytest.mark.parametrize("bad_name", [
    "A" * 61,
    "RELATES_TO_" + "X" * 50,
])
def test_normalize_edge_type_rejects_too_long(bad_name):
    with pytest.raises(ValueError, match="too long"):
        normalize_edge_type(bad_name)
```

### 5. Verify all existing tests still pass

```bash
uv run pytest tests/ -v
```

Check for any test that relied on lowercase-start type names or types longer than 60 chars. Fix them to use valid type names.

---

## Verification

```bash
# Run full test suite
uv run pytest tests/ -v

# Run only the new/modified tests
uv run pytest tests/unit/test_normalization.py tests/unit/test_extraction_schemas.py tests/unit/test_domain_routing.py -v
```

Expected: All tests pass, including both new tests and all pre-existing tests.

---

## Commit

```
test(plan-19): add unit tests for permission fix, type hardening, temporal schema

- Permission grant for existing schemas in _ensure_schema
- Type name max length (60 chars) and uppercase start rejection
- Pydantic validators on extraction schema type fields
- Temporal signal fields on ExtractedEntity

Validates fixes for M4, M5, M6 from Plan 18.5 E2E revalidation.
```
