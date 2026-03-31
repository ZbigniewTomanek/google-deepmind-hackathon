# Stage 3: Extraction Pipeline Hardening

**Goal**: Make `tool_calls_limit` configurable with a higher default, and remove eager `cleanup_partial_curation` from the initial run.
**Dependencies**: Stage 1 (RLS removal eliminates the primary systemic failure cause)

---

## Steps

### 1. Add `extraction_tool_calls_limit` to settings

- File: `src/neocortex/mcp_settings.py` (class `MCPSettings`)
- Details:
  - The extraction pipeline uses `MCPSettings` — accessed via
    `services["settings"]` in `jobs/tasks.py` (line 53). Existing extraction
    settings are at lines 107-116 (e.g., `extraction_enabled`, model configs).
  - Add the new field near the other extraction settings:
    ```python
    extraction_tool_calls_limit: int = 150
    ```
  - Env var: `NEOCORTEX_EXTRACTION_TOOL_CALLS_LIMIT` (Pydantic Settings auto-prefix)
  - Default: 150 (up from hardcoded 50). Budget analysis from Plan 22:
    - Typical episode: 12 entities x 2 calls + 6 relations x 2 calls = 36 calls
    - Complex episode: 20 entities + 15 relations + inspections = ~80 calls
    - Correction episodes with archiving + versioned nodes: ~100 calls
    - 150 provides headroom for all observed scenarios

### 2. Use the setting in `run_extraction`

- File: `src/neocortex/extraction/pipeline.py`
- Lines: 181, 229 (both places `UsageLimits(tool_calls_limit=50)` appears)
- Details:
  - Add `tool_calls_limit: int = 150` parameter to `run_extraction` signature.
  - Replace both hardcoded `50` values:
    ```python
    usage_limits=UsageLimits(tool_calls_limit=tool_calls_limit),
    ```
  - Update the caller in `jobs/tasks.py` (`extract_episode` task, lines 16-27)
    to pass the setting value. Call chain:
    ```python
    # jobs/tasks.py — extract_episode task
    services = get_services()                    # line 52
    settings = services["settings"]              # line 53 — MCPSettings instance
    # ... then pass to run_extraction:
    await run_extraction(..., tool_calls_limit=settings.extraction_tool_calls_limit)
    ```

### 3. Remove eager cleanup from initial extraction run

- File: `src/neocortex/extraction/pipeline.py`
- Lines: 150-164 (cleanup before librarian run)
- Details:
  - **Current behavior**: `cleanup_partial_curation` runs before EVERY librarian
    execution, including the first attempt. This means on retry, all previous work
    is deleted before re-running.
  - **New behavior**: Remove the `cleanup_partial_curation` call from the tool-driven
    path entirely. Rationale:
    - `create_or_update_node` is an upsert — re-running the librarian on the same
      episode updates existing nodes rather than creating duplicates.
    - `_source_episode` property tag tracks provenance for debugging.
    - LLM non-determinism may create slightly different graphs on retry, but this
      is acceptable and self-correcting (next extraction merges/deduplicates).
    - With RLS removed (Stage 1), the primary systemic failure cause is gone.
  - **Delete** lines 154-164 (the `cleanup_partial_curation` call and its logging).
  - **Add a comment** explaining why cleanup is not needed:
    ```python
    # No cleanup_partial_curation needed: create_or_update_node uses upsert
    # semantics, so re-running the librarian is naturally idempotent.
    ```
  - **Note**: Do NOT remove `cleanup_partial_curation` from the protocol/adapter —
    it may still be useful for manual maintenance or future use cases.

---

## Verification

- [ ] Grep for `tool_calls_limit=50` in pipeline.py — should be zero
- [ ] Grep for `cleanup_partial_curation` in pipeline.py — should not appear in tool-driven path
- [ ] Read settings and confirm `extraction_tool_calls_limit` field exists with default 150
- [ ] `uv run pytest tests/ -v -k "pipeline or extraction"` — tests pass
- [ ] `uv run pytest tests/ -v` — full suite passes

---

## Commit

`fix(extraction): make tool_calls_limit configurable (default 150), remove eager cleanup`
