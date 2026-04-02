# Stage 3: Check Endpoint — POST /ingest/check

**Goal**: Add a batch endpoint that accepts a list of content hashes and returns which ones have already been ingested, so callers can pre-filter before uploading.
**Dependencies**: Stage 2 (check_episode_hashes must be implemented)

---

## Steps

1. **Add request/response models**
   - File: `src/neocortex/ingestion/models.py`
   - Details: Add:
     ```python
     class HashCheckRequest(BaseModel):
         hashes: list[str] = Field(min_length=1, max_length=500)
         target_graph: str | None = Field(
             default=None,
             description="Check against a specific graph schema. If omitted, checks personal graph.",
         )

     class HashCheckResult(BaseModel):
         existing: dict[str, int]  # {hash: episode_id} for hashes that exist
         missing: list[str]        # hashes not found
     ```

2. **Add the route**
   - File: `src/neocortex/ingestion/routes.py`
   - Details: Add a new endpoint after the existing ingestion routes:
     ```python
     @router.post("/check", response_model=HashCheckResult)
     async def check_hashes(
         body: HashCheckRequest,
         request: Request,
         agent_id: Annotated[str, Depends(get_agent_id)],
     ) -> HashCheckResult:
         repo = request.app.state.services_ctx["repo"]
         existing = await repo.check_episode_hashes(
             agent_id, body.hashes, target_schema=body.target_graph
         )
         missing = [h for h in body.hashes if h not in existing]
         return HashCheckResult(existing=existing, missing=missing)
     ```
   - Note: The route prefix is `/ingest`, so the full path will be `POST /ingest/check`.
   - The `services_ctx` dict is stored on `app.state` in the lifespan — verify by reading `app.py`.
   - If `services_ctx` is not on `app.state`, store `repo` directly on `app.state` in the lifespan.

3. **Add audit logging**
   - In the route handler, add:
     ```python
     logger.bind(action_log=True).info(
         "hash_check",
         agent_id=agent_id,
         hashes_checked=len(body.hashes),
         hashes_found=len(existing),
     )
     ```

---

## Verification

- [ ] `POST /ingest/check` with `{"hashes": ["abc123"]}` returns `{"existing": {}, "missing": ["abc123"]}`
- [ ] After ingesting text, the hash of that text appears in `existing` on re-check
- [ ] Agent-scoped: agent A's hashes are not visible to agent B
- [ ] `uv run pytest tests/ -v -x` — all existing tests pass

---

## Commit

`feat(ingestion): add POST /ingest/check endpoint for batch hash lookup`
