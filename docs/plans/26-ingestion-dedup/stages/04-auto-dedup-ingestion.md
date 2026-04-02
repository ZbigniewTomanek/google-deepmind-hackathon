# Stage 4: Auto-Dedup in Ingestion Endpoints

**Goal**: Wire SHA-256 hash computation and dedup checking into all ingestion flows, with a `force` flag to override.
**Dependencies**: Stage 2 (hash storage), Stage 3 (models)

---

## Steps

1. **Add `force` flag to request models**
   - File: `src/neocortex/ingestion/models.py`
   - Details: Add to `TextIngestionRequest` and `EventsIngestionRequest`:
     ```python
     force: bool = Field(
         default=False,
         description="If true, skip dedup check and ingest even if content was already processed.",
     )
     ```

2. **Add `"skipped"` to IngestionResult status**
   - File: `src/neocortex/ingestion/models.py`
   - Details: Change `status: Literal["stored", "failed", "partial"]` to
     `status: Literal["stored", "failed", "partial", "skipped"]`.
   - Also add optional fields for dedup info:
     ```python
     content_hash: str | None = None
     existing_episode_id: int | None = None
     ```
   - Do the same for `MediaIngestionResult` (it extends `IngestionResult`, so it
     inherits these fields — verify this is the case).

3. **Add hash computation helpers to EpisodeProcessor**
   - File: `src/neocortex/ingestion/episode_processor.py`
   - Details: Add two static methods — one for text, one for raw bytes:
     ```python
     @staticmethod
     def _compute_hash(content: str) -> str:
         return hashlib.sha256(content.encode("utf-8")).hexdigest()

     @staticmethod
     def _compute_hash_bytes(data: bytes) -> str:
         return hashlib.sha256(data).hexdigest()
     ```
   - Add `import hashlib` at the top.

4. **Wire dedup into `process_text()`**
   - File: `src/neocortex/ingestion/episode_processor.py`
   - Details: Add `force: bool = False` param. Before storing:
     ```python
     content_hash = self._compute_hash(text)
     if not force:
         existing = await self._repo.check_episode_hashes(
             agent_id, [content_hash], target_schema=target_schema
         )
         if existing:
             return IngestionResult(
                 status="skipped",
                 episodes_created=0,
                 message="Content already ingested",
                 content_hash=content_hash,
                 existing_episode_id=next(iter(existing.values())),
             )
     ```
     Then pass `content_hash` to `_store_episode()`.

5. **Wire dedup into `process_document()`**
   - Add `force: bool = False` param.
   - Hash the raw `content: bytes` using `_compute_hash_bytes(content)` — this is the
     original uploaded file, before any decoding. This ensures identical files always
     produce the same hash regardless of how text is later extracted.

6. **Wire dedup into `process_events()`**
   - Add `force: bool = False` param.
   - For batch events: compute hash per event, batch-check all hashes upfront,
     skip events whose hash already exists (unless force). Track skipped count.
   - Also track hashes seen within this batch to catch intra-batch duplicates
     (two identical events in the same request). Maintain a `seen_hashes: set[str]`
     alongside the DB lookup results.
   - Return `"partial"` if some were skipped and some stored, `"skipped"` if all skipped.

7. **Wire dedup into `process_audio()` and `process_video()`**
   - Add `force: bool = False` param.
   - Hash the raw uploaded file bytes using `_compute_hash_bytes()` **before** the
     compress+describe pipeline. Media descriptions from Gemini are non-deterministic,
     so hashing the episode text would never match on re-ingestion of the same file.
   - This means the dedup check happens early — if the hash already exists, skip the
     entire compress+describe+store pipeline (significant cost saving).
   - The `raw_path` parameter points to a temp file; read its bytes for hashing.
   - Note: media routes use `Form()` params, not JSON body. The `force` flag needs to
     be added as a Form parameter in the route handler, not the processor.

8. **Update `_store_episode()` to accept and pass content_hash**
   - File: `src/neocortex/ingestion/episode_processor.py`
   - Details: Add `content_hash: str | None = None` param, pass through to
     `self._repo.store_episode()` / `self._repo.store_episode_to()`.

9. **Update route handlers to pass `force` flag**
   - File: `src/neocortex/ingestion/routes.py`
   - Details:
     - `ingest_text`: Pass `body.force` to `processor.process_text(..., force=body.force)`
     - `ingest_document`: Add `force: bool = Form(default=False)` param, pass to processor
     - `ingest_events`: Pass `body.force` to `processor.process_events(..., force=body.force)`
     - `ingest_audio`: Add `force: bool = Form(default=False)` param, pass to processor
     - `ingest_video`: Add `force: bool = Form(default=False)` param, pass to processor

10. **Update IngestionProcessor protocol**
    - File: `src/neocortex/ingestion/protocol.py`
    - Details: Add `force: bool = False` to all method signatures.

---

## Verification

- [ ] `POST /ingest/text {"text": "hello"}` returns `status: "stored"` with `content_hash` set
- [ ] Same request again returns `status: "skipped"` with `existing_episode_id` set
- [ ] Same request with `"force": true` returns `status: "stored"` (new episode created)
- [ ] `POST /ingest/events` with 3 events where 1 is a duplicate: returns `"partial"` with `episodes_created: 2`
- [ ] Document and media endpoints respect dedup + force flag
- [ ] `uv run pytest tests/ -v -x` — all existing tests pass

---

## Commit

`feat(ingestion): auto-dedup ingestion with force override flag`
