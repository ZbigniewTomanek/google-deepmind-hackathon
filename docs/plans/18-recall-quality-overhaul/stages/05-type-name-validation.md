# Stage 5: Type Name Validation

**Goal**: Reject malformed type names (containing `}`, `{`, or other invalid characters) in the normalization layer so corrupted LLM output never enters the graph.
**Dependencies**: None (independent of Phase A and Phase B)

---

## Background

E2E testing produced the corrupted node type `Constraint}OceanScience`. This is malformed JSON from the LLM output that the normalization layer passed through because:

1. `normalize_node_type()` (`normalization.py:76-96`) only handles casing — it doesn't validate characters.
2. The function's final branch (`return name` for mixed-case input) is a catch-all that accepts anything.
3. Similarly, `normalize_edge_type()` (`normalization.py:59-73`) doesn't validate characters.
4. The PostgreSQL schema has no CHECK constraint on type names.

**Fix**: Add character validation after normalization. Invalid characters are stripped, and if the result is empty or still invalid, the type name is rejected (logged + skipped).

Valid patterns:
- **Node types**: PascalCase — `^[A-Z][a-zA-Z0-9]*$`
- **Edge types**: SCREAMING_SNAKE — `^[A-Z][A-Z0-9_]*[A-Z0-9]$`

---

## Steps

1. **Add validation regex to normalization functions**
   - File: `src/neocortex/normalization.py`
   - After `normalize_node_type` (around line 96), add a validation step:
     ```python
     import re

     _VALID_NODE_TYPE = re.compile(r"^[A-Z][a-zA-Z0-9]*$")
     _VALID_EDGE_TYPE = re.compile(r"^[A-Z][A-Z0-9_]*[A-Z0-9]$")
     _INVALID_CHARS = re.compile(r"[^a-zA-Z0-9_\- ]")  # preserves hyphens for edge type processing

     def normalize_node_type(name: str) -> str:
         """Ensure PascalCase for node type names."""
         # Strip invalid characters before any other processing
         name = _INVALID_CHARS.sub("", name).strip()
         if not name:
             raise ValueError(f"Node type name is empty after stripping invalid characters")

         # ... existing casing logic (unchanged) ...

         result = ...  # existing return value

         # Final validation
         if not _VALID_NODE_TYPE.match(result):
             raise ValueError(
                 f"Node type '{result}' does not match PascalCase pattern after normalization"
             )
         return result
     ```

   - Similarly for `normalize_edge_type`:
     ```python
     def normalize_edge_type(name: str) -> str:
         """Convert any edge type name to SCREAMING_SNAKE_CASE."""
         # Strip invalid characters before processing
         name = _INVALID_CHARS.sub("", name).strip()
         if not name:
             raise ValueError(f"Edge type name is empty after stripping invalid characters")

         # ... existing casing logic (unchanged) ...

         result = ...  # existing return value

         # Final validation
         if not _VALID_EDGE_TYPE.match(result):
             raise ValueError(
                 f"Edge type '{result}' does not match SCREAMING_SNAKE pattern after normalization"
             )
         return result
     ```

2. **Handle validation errors in `get_or_create_node_type` / `get_or_create_edge_type`**
   - File: `src/neocortex/db/adapter.py`, methods around lines 416-485
   - Wrap the normalization call in try/except and log + skip on ValueError:
     ```python
     async def get_or_create_node_type(self, agent_id, name, description=None, ...):
         try:
             name = normalize_node_type(name)
         except ValueError as e:
             logger.warning("invalid_node_type_rejected", raw_name=name, error=str(e))
             return None  # Caller must handle None
         # ... rest of method ...
     ```
   - Similarly for `get_or_create_edge_type`.

3. **Handle `None` type returns in the extraction pipeline**
   - File: `src/neocortex/extraction/pipeline.py` (around lines 111-115)
   - When creating types from ontology proposals, skip entries where `get_or_create_node_type` returns `None`:
     ```python
     for nt in ontology_result.output.new_node_types:
         type_obj = await repo.get_or_create_node_type(agent_id, nt.name, nt.description, ...)
         if type_obj is None:
             logger.warning("skipping_invalid_node_type", name=nt.name)
             continue
     ```
   - Similarly for edge types.

4. **Handle `None` type in librarian tool calls**
   - File: `src/neocortex/extraction/agents.py`
   - In the `create_or_update_node` tool function (used by librarian), where `get_or_create_node_type` is called, handle `None` return:
     ```python
     node_type = await repo.get_or_create_node_type(agent_id, type_name, ...)
     if node_type is None:
         return {"error": f"Invalid type name '{type_name}' — rejected by validation"}
     ```

5. **Test the validation**
   - File: `tests/unit/test_normalization.py` (create if it doesn't exist, or add to existing normalization tests)
   - Add tests:
     ```python
     def test_node_type_rejects_json_corruption():
         """Type names with } or { should raise ValueError."""
         with pytest.raises(ValueError):
             normalize_node_type("Constraint}OceanScience")

     def test_node_type_strips_parentheses():
         with pytest.raises(ValueError):  # or returns cleaned version
             normalize_node_type("(InvalidType)")

     def test_node_type_valid_pascal_case():
         assert normalize_node_type("DataStore") == "DataStore"
         assert normalize_node_type("tool") == "Tool"
         assert normalize_node_type("data_store") == "DataStore"

     def test_edge_type_rejects_json_corruption():
         with pytest.raises(ValueError):
             normalize_edge_type("RELATES{TO")

     def test_edge_type_valid_screaming_snake():
         assert normalize_edge_type("RELATES_TO") == "RELATES_TO"
         assert normalize_edge_type("relates to") == "RELATES_TO"
         assert normalize_edge_type("relatesTo") == "RELATES_TO"

     def test_empty_after_strip_raises():
         with pytest.raises(ValueError):
             normalize_node_type("}{}")
     ```

6. **Verify existing normalization tests still pass**
   - Check existing tests in `tests/unit/test_normalization.py` for edge cases.
   - The `_INVALID_CHARS` regex preserves hyphens (`[^a-zA-Z0-9_\- ]`) so that the existing `name.replace("-", "_")` step in edge types still works correctly.
   - Verify: `normalize_edge_type("RELATES-TO")` → `"RELATES_TO"` (hyphen handling preserved).
   - Verify: `normalize_node_type("DataStore")` → `"DataStore"` (existing behavior preserved).

---

## Verification

- [ ] `uv run pytest tests/unit/test_normalization.py -v` — all tests pass (both new and existing)
- [ ] `normalize_node_type("Constraint}OceanScience")` raises `ValueError`
- [ ] `normalize_node_type("DataStore")` returns `"DataStore"` (existing behavior preserved)
- [ ] `normalize_edge_type("RELATES-TO")` returns `"RELATES_TO"` (hyphen handling preserved)
- [ ] `uv run pytest tests/ -v` — no regressions in extraction or adapter tests
- [ ] `NEOCORTEX_MOCK_DB=true uv run python -m neocortex` starts without errors

---

## Commit

`fix(normalization): reject malformed type names with invalid characters`
