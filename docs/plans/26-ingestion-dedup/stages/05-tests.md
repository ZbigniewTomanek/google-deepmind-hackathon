# Stage 5: Tests

**Goal**: Comprehensive test coverage for dedup logic, check endpoint, force override, and multi-schema behavior.
**Dependencies**: Stages 1-4

---

## Steps

1. **Create `tests/unit/test_ingestion_dedup.py`**
   - Details: Unit tests using `InMemoryRepository` (no Docker). Cover:
     - **Hash computation**: Verify `_compute_hash()` produces consistent SHA-256 hex
     - **First ingestion**: Returns `"stored"` with `content_hash` set
     - **Duplicate detection**: Same content returns `"skipped"` with `existing_episode_id`
     - **Force override**: Same content with `force=True` returns `"stored"`, creates new episode
     - **Different content**: Different text returns `"stored"` (no false dedup)
     - **Agent isolation**: Agent A's content doesn't trigger dedup for agent B
     - **Events batch dedup**: Mix of new + duplicate events returns `"partial"`
     - **Events all duplicates**: Returns `"skipped"`
     - **Target schema**: Dedup works correctly with `target_schema` (shared graph)
     - **Document dedup**: Same file content detected as duplicate
   - Use the `EpisodeProcessor` directly with mock repo (follow pattern from existing tests).

2. **Add check endpoint tests to `tests/test_ingestion_api.py`**
   - Details: API-level tests using `TestClient`. Cover:
     - **Empty check**: Unknown hashes return in `missing`
     - **After ingestion**: Hash moves from `missing` to `existing`
     - **Batch check**: Multiple hashes, mix of existing and missing
     - **Agent isolation**: Agent A's hashes not visible to agent B
     - **Auth required**: Unauthenticated request returns 401 (if auth mode is dev_token)
     - **Validation**: Empty hashes list returns 422

3. **Add dedup integration tests to existing ingestion tests**
   - File: `tests/test_ingestion_api.py`
   - Details: Add tests for:
     - `POST /ingest/text` returns `content_hash` in response
     - `POST /ingest/text` same content twice: second returns `"skipped"`
     - `POST /ingest/text` with `"force": true` always stores
     - Response schema includes `content_hash` and `existing_episode_id` fields

4. **Verify media dedup if media tests exist**
   - Search for existing media ingestion tests. If they exist, add a dedup test.
   - If no media tests exist, skip — unit tests in step 1 cover the processor logic.

---

## Verification

- [ ] `uv run pytest tests/unit/test_ingestion_dedup.py -v` — all new tests pass
- [ ] `uv run pytest tests/test_ingestion_api.py -v` — all tests pass (old + new)
- [ ] `uv run pytest tests/ -v -x` — full suite passes, no regressions

---

## Commit

`test(ingestion): add dedup and hash check endpoint tests`
