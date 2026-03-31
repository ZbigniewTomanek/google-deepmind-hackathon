# Stage 2: Type Name Hardening

**Goal**: Reject LLM reasoning leaks and malformed type names by adding length limits, uppercase-start enforcement, and Pydantic validators.
**Dependencies**: None (independent of Stage 1)

---

## Background

Four corrupted type names passed validation during Plan 18.5:

| Type | Length | Issue |
|------|--------|-------|
| `DatasetNoteTheSearchResultsShowed...` | 440+ | LLM reasoning leak |
| `EvidencedocumentOceanography` | 29 | Not PascalCase (lowercase 'd') |
| `FeatureMergesWithEntityObjectId167` | 35 | Node ID embedded |
| `OperationbrCreateOrUpdate...` | 300+ | Tool-call reasoning leak |

Current regex `^[a-zA-Z][a-zA-Z0-9]*$` (normalization.py:11) has no length limit and accepts lowercase starts.

---

## Steps

### 1. Fix node type regex and add length limit

**File**: `src/neocortex/normalization.py:11`

Change:
```python
_VALID_NODE_TYPE = re.compile(r"^[a-zA-Z][a-zA-Z0-9]*$")
```

To:
```python
_VALID_NODE_TYPE = re.compile(r"^[A-Z][a-zA-Z0-9]*$")
_MAX_TYPE_NAME_LENGTH = 60
```

### 2. Add length check in `normalize_node_type()`

**File**: `src/neocortex/normalization.py:89-116`

After the `_INVALID_CHARS.sub()` strip (line 92) and before the final validation (line 114), add:

```python
# Truncate excessive length (LLM reasoning leaks)
if len(name) > _MAX_TYPE_NAME_LENGTH:
    raise ValueError(
        f"Node type name too long ({len(name)} chars, max {_MAX_TYPE_NAME_LENGTH}): "
        f"'{name[:50]}...'"
    )
```

Place this BEFORE the PascalCase normalization logic so the error message shows the raw input.

### 3. Ensure uppercase start after normalization

The existing normalization logic handles some cases (line 102: `part.capitalize()`, line 108: `name.capitalize()`), but the `else` branch (line 110-111: "Already PascalCase or mixed case") preserves the original case. After the switch statement, before validation:

```python
# Ensure first character is uppercase
if result and result[0].islower():
    result = result[0].upper() + result[1:]
```

### 4. Add length check in `normalize_edge_type()`

**File**: `src/neocortex/normalization.py:63-86`

Add the same length check after the strip:

```python
if len(name) > _MAX_TYPE_NAME_LENGTH:
    raise ValueError(
        f"Edge type name too long ({len(name)} chars, max {_MAX_TYPE_NAME_LENGTH}): "
        f"'{name[:50]}...'"
    )
```

### 5. Add Pydantic validators on extraction schema type fields

**File**: `src/neocortex/extraction/schemas.py`

Add field validators to `ProposedNodeType`, `ProposedEdgeType`, and `ExtractedEntity`:

```python
from pydantic import field_validator

class ProposedNodeType(BaseModel):
    name: str = Field(description="PascalCase type name, e.g. 'Neurotransmitter'", max_length=60)
    description: str = ""

    @field_validator("name")
    @classmethod
    def validate_type_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 60:
            raise ValueError(f"Type name too long ({len(v)} chars)")
        if not v[0].isupper():
            raise ValueError(f"Type name must start with uppercase: '{v}'")
        return v
```

Apply analogous validators to `ProposedEdgeType.name` and `ExtractedEntity.type_name`.

### 6. Update existing tests for the stricter regex

**File**: `tests/unit/test_normalization.py`

Some existing test cases may use lowercase-start type names. Update them to start with uppercase. Check for any test that calls `normalize_node_type()` with a lowercase-start input and expects success.

---

## Verification

```bash
# Run normalization tests
uv run pytest tests/unit/test_normalization.py -v

# Run all tests to check for regressions
uv run pytest tests/ -v -x

# Manual check: verify the 4 corrupted types would be rejected
python3 -c "
from neocortex.normalization import normalize_node_type
for name in [
    'DatasetNoteTheSearchResultsShowedThatThe' + 'x' * 400,
    'EvidencedocumentOceanography',
    'FeatureMergesWithEntityObjectId167',
    'OperationbrCreateOrUpdate' + 'x' * 300,
]:
    try:
        normalize_node_type(name)
        print(f'FAIL: accepted {name[:50]}...')
    except ValueError as e:
        print(f'OK: rejected {name[:50]}... -- {e}')
"
```

Expected: All 4 corrupted type names are rejected (ValueError raised).

---

## Commit

```
fix(normalization): add max length and uppercase-start enforcement to type names

Rejects LLM reasoning leaks (440+ char strings) and malformed types.
Node types: ^[A-Z][a-zA-Z0-9]*$ with 60 char max.
Pydantic validators on ProposedNodeType and ExtractedEntity catch
corruption before it reaches the database.

Fixes M6 (4 corrupted types) from Plan 18.5 E2E revalidation.
```
