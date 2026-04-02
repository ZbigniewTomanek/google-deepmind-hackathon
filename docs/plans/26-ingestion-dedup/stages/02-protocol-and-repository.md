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
     - `check_episode_hashes()`: Dual connection path depending on `target_schema`:
       - **Without `target_schema`** (personal graph): route via `schema = await self._router.route_store(agent_id)`, then use `schema_scoped_connection(self._pool, schema)` — same pattern as `store_episode()`.
       - **With `target_schema`** (shared graph): use `graph_scoped_connection(self._pool, target_schema, agent_id)` — same pattern as `store_episode_to()`.
       - If routing returns `None` (no personal graph exists yet), return an empty dict (no episodes to match against).
     - Note: `store_episode_to()` INSERT includes an `owner_role` column that `store_episode()` does not. Ensure `content_hash` is added to each INSERT's column list independently.

   Example SQL for check:
   ```sql
   SELECT content_hash, id FROM episode
   WHERE agent_id = $1 AND content_hash = ANY($2)
   ```

4. **Implement in `InMemoryRepository`**
   - File: `src/neocortex/db/mock.py`
   - Details:
     - Add `content_hash: str | None` directly to the `EpisodeRecord` TypedDict (do NOT store in metadata — the lookup needs direct field access)
     - `store_episode()`: Accept and store `content_hash`
     - `store_episode_to()`: Same
     - `check_episode_hashes()`: Iterate stored episodes, match by `agent_id` and hash

5. **Update Episode model**
   - File: `src/neocortex/models.py`
   - Details: Add `content_hash: str | None = None` to the `Episode` dataclass/model (search for `class Episode`).

6. **Update GraphService.create_episode() — used by adapter fallback**
   - File: `src/neocortex/graph_service.py`
   - Details: The adapter falls back to `GraphService.create_episode()` when `self._pool is None` (mock/testing mode). This path **is used** — add `content_hash: str | None = None` param and include it in the INSERT SQL (`INSERT INTO episode (..., content_hash) VALUES (..., $N)`).

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
