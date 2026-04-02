# Stage 2: Protocol & Repository — Hash Storage and Lookup

**Goal**: Add content hash computation, storage, and batch lookup methods to the MemoryRepository protocol and both implementations (adapter + mock).
**Dependencies**: Stage 1 (content_hash column must exist)

---

## Steps

1. **Add `check_episode_hashes()` to the protocol**
   - File: `src/neocortex/db/protocol.py`
   - Details: Add a new method to `MemoryRepository`:
     ```python
     async def check_episode_hashes(
         self,
         agent_id: str,
         hashes: list[str],
         target_schema: str | None = None,
     ) -> dict[str, int]:
         """Check which content hashes already exist for this agent.
         Returns a dict of {hash: episode_id} for hashes that exist."""
         ...
     ```

2. **Update `store_episode` / `store_episode_to` signatures in protocol**
   - File: `src/neocortex/db/protocol.py`
   - Details: Add `content_hash: str | None = None` parameter to both methods.

3. **Implement in `GraphServiceAdapter`**
   - File: `src/neocortex/db/adapter.py`
   - Details:
     - `store_episode()`: Add `content_hash` param, include in INSERT SQL (`INSERT INTO episode (..., content_hash) VALUES (..., $N)`)
     - `store_episode_to()`: Same treatment
     - `check_episode_hashes()`: Query episode table filtered by `agent_id` and `content_hash = ANY($2)`, return `{hash: id}` dict. Route via `_router.route_store(agent_id)` for personal, or use `target_schema` for shared.

   Example SQL for check:
   ```sql
   SELECT content_hash, id FROM episode
   WHERE agent_id = $1 AND content_hash = ANY($2)
   ```

4. **Implement in `InMemoryRepository`**
   - File: `src/neocortex/db/mock.py`
   - Details:
     - Add `content_hash` field to the in-memory `EpisodeRecord` (or store in metadata)
     - `store_episode()`: Accept and store `content_hash`
     - `store_episode_to()`: Same
     - `check_episode_hashes()`: Iterate stored episodes, match by `agent_id` and hash

5. **Update Episode model**
   - File: `src/neocortex/models.py`
   - Details: Add `content_hash: str | None = None` to the `Episode` dataclass/model (search for `class Episode`).

6. **Update GraphService.create_episode() if used**
   - File: `src/neocortex/graph_service.py`
   - Details: Search for `create_episode` method. If it's used by the adapter fallback path, add `content_hash` param and include in its INSERT SQL.

---

## Verification

- [ ] Protocol defines `check_episode_hashes()` and updated `store_episode*` signatures
- [ ] `GraphServiceAdapter` implements all three methods with correct SQL
- [ ] `InMemoryRepository` implements all three methods
- [ ] Episode model has `content_hash` field
- [ ] `uv run pytest tests/ -v -x` — all existing tests pass

---

## Commit

`feat(db): add content hash storage and lookup to MemoryRepository`
