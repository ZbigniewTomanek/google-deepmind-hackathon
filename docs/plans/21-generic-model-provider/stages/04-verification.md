# Stage 4: Verification

**Goal**: Full integration verification — ensure the system works end-to-end with the new string-based model configuration.
**Dependencies**: Stage 3 (DONE)

---

## Steps

1. Run the full test suite
   - Run: `uv run pytest tests/ -v`
   - All tests must pass. The mock/test paths use `TestModel` (unchanged) and
     the `InMemoryRepository` (unchanged), so they should work without modification.

2. Verify mock DB server starts
   - Run: `NEOCORTEX_MOCK_DB=true uv run python -m neocortex` (start, verify no import errors, Ctrl+C)
   - The MCP server must boot without `GoogleModel`-related import errors.

3. Verify custom model override via env var
   - Run: `NEOCORTEX_MOCK_DB=true NEOCORTEX_ONTOLOGY_MODEL=openai:gpt-4o uv run python -c "from neocortex.mcp_settings import MCPSettings; s = MCPSettings(); print(s.ontology_model)"`
   - Must print `openai:gpt-4o` — proving the user can override the provider via env vars.

4. Verify no remaining Google-specific model imports in agent code
   - Run: `grep -rn "GoogleModel\|from pydantic_ai.models.google" src/neocortex/extraction/ src/neocortex/domains/ src/pydantic_agents_playground/`
   - Must return empty (no matches).
   - Note: `embedding_service.py` and `media_description.py` still use `google.genai` directly — this is expected and out of scope.

5. Update the plan index with final status

---

## Verification

- [ ] `uv run pytest tests/ -v` — all tests pass
- [ ] MCP server boots in mock mode without errors
- [ ] Env var override works for model selection
- [ ] No `GoogleModel` imports remain in agent code (extraction, domains, playground)

---

## Commit

`docs(plans): mark generic-model-provider plan as complete`
