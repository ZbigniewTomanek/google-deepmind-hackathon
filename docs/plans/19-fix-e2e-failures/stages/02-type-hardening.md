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

### 1. Fix node type regex, add length limit, and add word-count heuristic

**File**: `src/neocortex/normalization.py:11`

Change:
```python
_VALID_NODE_TYPE = re.compile(r"^[a-zA-Z][a-zA-Z0-9]*$")
```

To:
```python
_VALID_NODE_TYPE = re.compile(r"^[A-Z][a-zA-Z0-9]*$")
_MAX_TYPE_NAME_LENGTH = 60
_MAX_TYPE_WORD_COUNT = 5
_PASCAL_WORD_BOUNDARY = re.compile(r"[A-Z][a-z]+|[A-Z]+(?=[A-Z]|$)|[0-9]+")
```

The `_PASCAL_WORD_BOUNDARY` regex splits PascalCase names into words
(e.g., `FeatureMergesWithEntityObjectId167` → 7 segments). Types with more than
5 PascalCase segments are almost certainly LLM reasoning leaks or tool-call
contamination, not legitimate ontology types. The longest legitimate types in
the current graph have 3-4 segments (e.g., `ParseHumanNameUDX`).

### 2. Add length and word-count checks in `normalize_node_type()`

**File**: `src/neocortex/normalization.py:89-116`

After the `_INVALID_CHARS.sub()` strip (line 92) and before the PascalCase normalization logic (line 97), add both checks:

```python
# Reject excessive length (LLM reasoning leaks)
if len(name) > _MAX_TYPE_NAME_LENGTH:
    raise ValueError(
        f"Node type name too long ({len(name)} chars, max {_MAX_TYPE_NAME_LENGTH}): "
        f"'{name[:50]}...'"
    )

# Reject names with too many PascalCase segments (reasoning contamination)
word_count = len(_PASCAL_WORD_BOUNDARY.findall(name))
if word_count > _MAX_TYPE_WORD_COUNT:
    raise ValueError(
        f"Node type name has too many segments ({word_count}, max {_MAX_TYPE_WORD_COUNT}): "
        f"'{name[:50]}...'"
    )
```

Place both BEFORE the PascalCase normalization logic so error messages show the raw input.

### 3. Ensure uppercase start after normalization

The existing normalization logic handles some cases (line 102: `part.capitalize()`, line 108: `name.capitalize()`), but the `else` branch (line 110-111: "Already PascalCase or mixed case") preserves the original case. After the switch statement, before validation:

```python
# Ensure first character is uppercase
if result and result[0].islower():
    result = result[0].upper() + result[1:]
```

### 4. Add length and word-count checks in `normalize_edge_type()`

**File**: `src/neocortex/normalization.py:63-86`

Add the same length and word-count checks after the strip:

```python
if len(name) > _MAX_TYPE_NAME_LENGTH:
    raise ValueError(
        f"Edge type name too long ({len(name)} chars, max {_MAX_TYPE_NAME_LENGTH}): "
        f"'{name[:50]}...'"
    )

word_count = len(_PASCAL_WORD_BOUNDARY.findall(name))
if word_count > _MAX_TYPE_WORD_COUNT:
    raise ValueError(
        f"Edge type name has too many segments ({word_count}, max {_MAX_TYPE_WORD_COUNT}): "
        f"'{name[:50]}...'"
    )
```

### 5. Add Pydantic validators on extraction schema type fields

**File**: `src/neocortex/extraction/schemas.py`

First, update the pydantic import at line 9 to include `field_validator`:
```python
from pydantic import BaseModel, Field, field_validator, model_validator
```

Then add field validators to `ProposedNodeType`, `ProposedEdgeType`, and `ExtractedEntity`.
Use `field_validator` (not `max_length` in Field) to keep validation logic in one place:

```python
class ProposedNodeType(BaseModel):
    name: str = Field(description="PascalCase type name, e.g. 'Neurotransmitter'")
    description: str = ""

    @field_validator("name")
    @classmethod
    def validate_type_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 60:
            raise ValueError(f"Type name too long ({len(v)} chars)")
        if v and not v[0].isupper():
            raise ValueError(f"Type name must start with uppercase: '{v}'")
        return v
```

Apply the same `validate_type_name` validator to `ProposedEdgeType.name` and `ExtractedEntity.type_name`.

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

# Manual check: verify corrupted types are rejected
python3 -c "
from neocortex.normalization import normalize_node_type
for name in [
    'DatasetNoteTheSearchResultsShowedThatThe' + 'x' * 400,  # length
    'FeatureMergesWithEntityObjectId167',                      # word count (7 segments)
    'OperationbrCreateOrUpdate' + 'x' * 300,                  # length
]:
    try:
        normalize_node_type(name)
        print(f'FAIL: accepted {name[:50]}...')
    except ValueError as e:
        print(f'OK: rejected {name[:50]}... -- {e}')
"
```

Expected: All 3 corrupted type names above are rejected (ValueError raised).

**Note on `EvidencedocumentOceanography`**: This 29-char type starts with uppercase,
has only 2 PascalCase segments, and passes all syntactic checks. It is a *semantic*
quality issue (wrong domain concatenation) that cannot be reliably caught by regex or
length heuristics without false positives on legitimate types. This is addressed by
prompt engineering in the extraction pipeline (Stage 4 strengthens type quality guidance).
The word-count heuristic catches the more egregious multi-word reasoning leaks.

---

## Commit

```
fix(normalization): add length, word-count, and uppercase-start enforcement to type names

Rejects LLM reasoning leaks via three checks: 60 char max, 5 PascalCase
segment max, and ^[A-Z] start requirement. Pydantic validators on
ProposedNodeType and ExtractedEntity catch corruption before it reaches
the database. Catches 3/4 corrupted types from Plan 18.5; the 4th
(EvidencedocumentOceanography) is a semantic issue addressed by prompts.

Fixes M6 from Plan 18.5 E2E revalidation.
```
