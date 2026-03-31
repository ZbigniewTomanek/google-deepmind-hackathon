# Stage 3: Temporal Schema Extension

**Goal**: Add temporal signal fields to the extraction schema so the extractor can mark corrections and the librarian has structured data to create SUPERSEDES/CORRECTS edges.
**Dependencies**: None (independent of Stages 1-2)

---

## Background

The extractor agent can detect correction signals in episode text ("CORRECTION", "instead of", "switched from"), but has no way to communicate this to the librarian. The `ExtractedEntity` schema (schemas.py:34-39) only has: `name`, `type_name`, `description`, `properties`, `importance`.

Without structured temporal metadata, the librarian follows the simpler path: find existing node → update in place → no temporal edges.

---

## Steps

### 1. Add temporal fields to `ExtractedEntity`

**File**: `src/neocortex/extraction/schemas.py:34-39`

Add two optional fields:

```python
class ExtractedEntity(BaseModel):
    name: str = Field(description="Canonical entity name")
    type_name: str = Field(description="Must match an existing node type name")
    description: str | None = None
    properties: dict = Field(default_factory=dict, description="Scalar facts as key-value pairs")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="How critical is this entity to the domain")
    supersedes: str | None = Field(
        default=None,
        description="If this entity CORRECTS or SUPERSEDES an existing entity, "
        "put the name of the old entity here. Signals: 'CORRECTION', 'UPDATE', "
        "'instead of', 'replaced by', 'switched from', 'no longer'.",
    )
    temporal_signal: str | None = Field(
        default=None,
        description="The type of temporal relationship: 'CORRECTS' (error fix) "
        "or 'SUPERSEDES' (newer version, reversed decision). "
        "Only set when 'supersedes' is also set.",
    )
```

### 2. Add temporal fields to `ExtractedRelation`

**File**: `src/neocortex/extraction/schemas.py:42-47`

The relation schema already has `relation_type`, but we should ensure the extractor can explicitly emit CORRECTS/SUPERSEDES relations. No schema change needed here -- the extractor can already set `relation_type="SUPERSEDES"`. But add a note in the field description:

```python
class ExtractedRelation(BaseModel):
    source_name: str
    target_name: str
    relation_type: str = Field(
        description="Must match an existing edge type name. "
        "Use 'CORRECTS' or 'SUPERSEDES' for temporal correction relationships."
    )
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    properties: dict = Field(default_factory=dict, description="Evidence text, confidence, etc.")
```

### 3. Update `CurationAction` to track temporal edges

**File**: `src/neocortex/extraction/schemas.py:89-96`

The `CurationAction.action` field already supports "created_edge". No schema change needed, but add a validation note in the description. The librarian should report temporal edges as:
```json
{"action": "created_edge", "edge_source": "Metaphone3 v2", "edge_target": "Metaphone3", "details": "SUPERSEDES edge for correction"}
```

---

## Verification

```bash
# Schema imports clean
python3 -c "from neocortex.extraction.schemas import ExtractedEntity; e = ExtractedEntity(name='X', type_name='Y', supersedes='Z', temporal_signal='CORRECTS'); print(e.model_dump())"

# All tests pass
uv run pytest tests/ -v -x
```

Expected: `ExtractedEntity` accepts `supersedes` and `temporal_signal` fields. All existing tests pass (new fields are optional with defaults).

---

## Commit

```
feat(extraction): add temporal signal fields to ExtractedEntity schema

Adds `supersedes` and `temporal_signal` fields so the extractor can
mark correction/supersession relationships explicitly. The librarian
receives structured data instead of relying on prompt-only guidance.

Preparation for M4 (temporal recall) fix from Plan 18.5 E2E revalidation.
```
