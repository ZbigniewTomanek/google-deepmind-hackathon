# Plan 10: Multimodal Audio/Video Ingestion via Gemini 3 Flash Preview

## Overview

Extend the ingestion API with audio and video support. Media files are pre-processed through a two-stage pipeline: (1) ffmpeg/ImageMagick compression to create storage-efficient minimized copies, (2) Gemini 3 Flash Preview multimodal inference to generate rich text descriptions. The text description is stored as an episode (feeds into the existing extraction pipeline), while the compressed media file is persisted on the filesystem with a stable reference so agents can access the original content when text alone is insufficient.

**Key design decisions:**
- Media files are **not** stored in PostgreSQL — they live on a configurable filesystem path (`NEOCORTEX_MEDIA_STORE_PATH`, default `./media_store/`)
- Each media file gets a deterministic path: `{store_path}/{agent_id}/{uuid}.{ext}`
- The episode's `metadata` dict carries a `media_ref` key with the filesystem path and original filename, enabling agents to locate the source material
- Compression is mandatory before Gemini upload to reduce token cost and storage — audio compressed to 64kbps mono opus, video to 480p CRF-30 h264 with 64kbps audio
- `IngestionProcessor` protocol gains two new methods: `process_audio` and `process_video`
- Mock mode skips compression and Gemini calls, stores a placeholder description
- ffmpeg is a system dependency (must be installed on host / in Docker image)

## Architecture

```
                      Client
                        │
                   POST /ingest/audio or /ingest/video
                        │ (multipart: file + metadata + target_graph)
                        ▼
                ┌──────────────┐
                │  routes.py   │  Validate content-type, size limit (100 MB)
                └──────┬───────┘
                       │
                       ▼
              ┌─────────────────┐
              │ EpisodeProcessor │
              │  .process_audio  │
              │  .process_video  │
              └────────┬────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
    ┌──────────┐ ┌───────────┐ ┌──────────────┐
    │ MediaFile │ │ Media     │ │ Episode      │
    │ Store    │ │ Compressor│ │ Store +      │
    │          │ │ (ffmpeg)  │ │ Embed +      │
    │ save     │ │ compress  │ │ Extract      │
    │ minimized│ │ audio/    │ │ (existing    │
    │ file to  │ │ video     │ │  pipeline)   │
    │ disk     │ └─────┬─────┘ └──────────────┘
    └──────────┘       │                ▲
                       ▼                │
               ┌──────────────┐         │
               │ MediaDescrip │   text description
               │ tionService  │─────────┘
               │ (Gemini 3    │
               │  Flash)      │
               │ generate_    │
               │ content()    │
               └──────────────┘
```

## Execution Protocol

Each stage is independently testable, committable, and leaves the codebase in a working state. Execute stages sequentially. Run `uv run pytest tests/ -v` after each stage. One commit per stage.

---

## Stage 1: Settings, Models, and Media File Store

**Goal**: Add configuration knobs, request/response models for media, and a filesystem-based media store that persists compressed files with stable paths.

### Steps

#### 1.1 — New settings in `MCPSettings`

Add to `src/neocortex/mcp_settings.py`:

```python
# Media ingestion
media_store_path: str = "./media_store"          # Root dir for compressed media files
media_max_upload_bytes: int = 100 * 1024 * 1024  # 100 MB upload limit
media_description_model: str = "gemini-3-flash-preview"  # Model for multimodal description
media_description_max_tokens: int = 8192         # Max output tokens for description
```

#### 1.2 — Media ingestion models

Create `src/neocortex/ingestion/media_models.py`:

```python
from pydantic import BaseModel

class MediaRef(BaseModel):
    """Reference to a stored media file on the filesystem."""
    path: str              # Absolute path to compressed file
    original_filename: str # Original upload filename
    content_type: str      # MIME type of original upload
    compressed_size: int   # Size in bytes after compression
    duration_seconds: float | None = None  # Duration if available

class MediaIngestionResult(BaseModel):
    """Extended result for media ingestion."""
    status: str            # "stored" | "failed" | "partial"
    episodes_created: int
    message: str
    media_ref: MediaRef | None = None  # Reference to stored media
```

#### 1.3 — MediaFileStore

Create `src/neocortex/ingestion/media_store.py`:

```python
class MediaFileStore:
    """Persists compressed media files on the local filesystem.

    Directory layout: {base_path}/{agent_id}/{uuid}.{ext}
    """

    def __init__(self, base_path: str) -> None: ...

    async def save(
        self, agent_id: str, data: bytes, extension: str, original_filename: str
    ) -> MediaRef: ...
        # 1. Ensure {base_path}/{agent_id}/ exists (os.makedirs, exist_ok=True)
        # 2. Generate UUID4 filename
        # 3. Write bytes to path via aiofiles (or sync write in executor)
        # 4. Return MediaRef with absolute path

    async def get_path(self, agent_id: str, file_id: str) -> str | None: ...
        # Resolve UUID to path, return None if not found

    async def delete(self, path: str) -> bool: ...
        # Remove file, return success
```

Use `anyio.to_thread.run_sync` for blocking I/O (consistent with asyncpg patterns in the codebase).

**Verification**: `uv run python -c "from neocortex.ingestion.media_store import MediaFileStore; from neocortex.ingestion.media_models import MediaRef, MediaIngestionResult; print('OK')"`

**Commit**: `feat(media): add settings, models, and filesystem media store`

---

## Stage 2: Media Compressor Service (ffmpeg)

**Goal**: Create a service that compresses audio/video files using ffmpeg subprocess calls, producing storage-efficient copies suitable for both filesystem persistence and Gemini API upload.

### Steps

#### 2.1 — Compressor service

Create `src/neocortex/ingestion/media_compressor.py`:

```python
class MediaCompressor:
    """Compresses audio/video files via ffmpeg for storage and Gemini upload.

    Audio: re-encode to 64kbps mono opus in ogg container
    Video: re-encode to 480p, CRF 30, h264, 64kbps mono audio, mp4 container
    """

    async def compress_audio(self, input_path: str, output_path: str) -> CompressedMedia: ...
        # ffmpeg -i {input} -ac 1 -b:a 64k -c:a libopus {output}.ogg
        # Return CompressedMedia(path, size, duration, mime_type)

    async def compress_video(self, input_path: str, output_path: str) -> CompressedMedia: ...
        # ffmpeg -i {input} -vf scale=-2:480 -c:v libx264 -crf 30
        #        -c:a libopus -b:a 64k -ac 1 {output}.mp4
        # Return CompressedMedia(path, size, duration, mime_type)

    async def extract_thumbnail(self, video_path: str, output_path: str) -> str: ...
        # ffmpeg -i {input} -ss 00:00:01 -frames:v 1 {output}.jpg
        # Optional: use ImageMagick to further compress thumbnail
        # convert {output}.jpg -resize 320x240 -quality 75 {output}.jpg

    async def probe_duration(self, path: str) -> float: ...
        # ffprobe -v quiet -show_entries format=duration -of csv=p=0 {path}

    @staticmethod
    async def _run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess: ...
        # Run via anyio.to_thread.run_sync(subprocess.run, ...)
        # Log command at DEBUG level
        # Raise on non-zero return code with stderr
```

Data class for compression results:

```python
@dataclass
class CompressedMedia:
    path: str
    size_bytes: int
    duration_seconds: float
    mime_type: str
```

#### 2.2 — System dependency check

Add a startup check in the compressor `__init__` that verifies `ffmpeg` and `ffprobe` are on PATH (via `shutil.which`). Log a warning if missing — media endpoints will return 503 if compression is attempted without ffmpeg.

**Verification**:
```bash
# Unit test with a tiny synthetic WAV
uv run pytest tests/test_media_compressor.py -v
```

Write a test that:
- Creates a minimal WAV file (1 second of silence via Python `wave` module)
- Compresses it with the audio compressor
- Asserts output is smaller and `.ogg` extension
- Skip if ffmpeg not installed (`pytest.mark.skipif`)

**Commit**: `feat(media): add ffmpeg-based media compressor service`

---

## Stage 3: Gemini Media Description Service

**Goal**: Create a service that uploads compressed media to the Gemini Files API and calls `generate_content` with Gemini 3 Flash Preview to produce a structured text description.

### Steps

#### 3.1 — MediaDescriptionService

Create `src/neocortex/ingestion/media_description.py`:

```python
class MediaDescriptionService:
    """Generates text descriptions of audio/video using Gemini 3 Flash Preview.

    Uses the Gemini Files API for upload (handles files up to 2GB) and
    generate_content for multimodal inference. Files are deleted from
    Gemini after description is generated (they auto-expire after 48h
    regardless).
    """

    def __init__(self, api_key: str, model: str = "gemini-3-flash-preview",
                 max_output_tokens: int = 8192) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._max_output_tokens = max_output_tokens

    async def describe_audio(self, file_path: str, mime_type: str,
                              context: str = "") -> MediaDescription: ...
        # 1. Upload via Files API: await self._client.aio.files.upload(file=file_path)
        # 2. Poll until state == ACTIVE (audio is usually instant)
        # 3. Call generate_content with structured prompt:
        #    "Provide a detailed description of this audio. Include:
        #     - Full transcription if speech is present
        #     - Speaker identification where possible
        #     - Description of non-speech audio (music, sounds, silence)
        #     - Language(s) detected
        #     - Overall summary
        #     Context from the user: {context}"
        # 4. Delete uploaded file from Gemini
        # 5. Return MediaDescription

    async def describe_video(self, file_path: str, mime_type: str,
                              context: str = "") -> MediaDescription: ...
        # 1. Upload via Files API
        # 2. Poll until state == ACTIVE (videos need processing time)
        # 3. Call generate_content with structured prompt:
        #    "Provide a detailed description of this video. Include:
        #     - Scene-by-scene description with timestamps
        #     - Full transcription of any speech
        #     - Description of visual elements, actions, and text on screen
        #     - Key objects, people, locations identified
        #     - Overall summary
        #     Context from the user: {context}"
        # 4. Delete uploaded file from Gemini
        # 5. Return MediaDescription

    async def _upload_and_wait(self, file_path: str) -> genai.types.File: ...
        # Upload + poll loop (5s interval, 5min timeout)

    async def _cleanup_file(self, file_name: str) -> None: ...
        # Best-effort delete, log warning on failure
```

Result model:

```python
@dataclass
class MediaDescription:
    text: str           # Full generated description (stored as episode content)
    model: str          # Model used
    token_count: int    # Tokens consumed (for audit logging)
```

#### 3.2 — Mock implementation

Create `src/neocortex/ingestion/media_description_mock.py`:

```python
class MockMediaDescriptionService:
    """Returns placeholder descriptions for mock/test mode."""

    async def describe_audio(self, file_path: str, mime_type: str,
                              context: str = "") -> MediaDescription:
        return MediaDescription(
            text=f"[Mock audio description for {Path(file_path).name}]",
            model="mock", token_count=0,
        )

    async def describe_video(self, file_path: str, mime_type: str,
                              context: str = "") -> MediaDescription:
        return MediaDescription(
            text=f"[Mock video description for {Path(file_path).name}]",
            model="mock", token_count=0,
        )
```

#### 3.3 — Audit logging

All Gemini API calls must log to `agent_actions.log`:
```python
logger.bind(action_log=True).info(
    "media_description_generated",
    media_type="audio"|"video",
    model=self._model,
    file_path=file_path,
    token_count=result.token_count,
    description_length=len(result.text),
)
```

**Verification**:
```bash
uv run pytest tests/test_media_description.py -v
```

Write tests using `MockMediaDescriptionService`. For integration test (skipped without API key), verify a real Gemini call with a tiny audio file.

**Commit**: `feat(media): add Gemini-powered media description service`

---

## Stage 4: Extend IngestionProcessor Protocol and EpisodeProcessor

**Goal**: Add `process_audio` and `process_video` to the protocol and implement the full pipeline in `EpisodeProcessor`: compress → describe → store file → store episode → embed → enqueue extraction.

### Steps

#### 4.1 — Extend protocol

Update `src/neocortex/ingestion/protocol.py`:

```python
class IngestionProcessor(Protocol):
    # ... existing methods unchanged ...

    async def process_audio(
        self, agent_id: str, filename: str, content: bytes,
        content_type: str, metadata: dict, target_schema: str | None = None,
    ) -> MediaIngestionResult: ...

    async def process_video(
        self, agent_id: str, filename: str, content: bytes,
        content_type: str, metadata: dict, target_schema: str | None = None,
    ) -> MediaIngestionResult: ...
```

#### 4.2 — Implement in EpisodeProcessor

Update `src/neocortex/ingestion/episode_processor.py`:

Add constructor parameters:
```python
def __init__(
    self,
    repo: MemoryRepository,
    embeddings: EmbeddingService | None = None,
    job_app: procrastinate.App | None = None,
    extraction_enabled: bool = True,
    # New: media services
    media_store: MediaFileStore | None = None,
    media_compressor: MediaCompressor | None = None,
    media_describer: MediaDescriptionService | None = None,
) -> None:
```

Implement `process_audio`:
```
1. Write raw upload to temp file (tempfile.NamedTemporaryFile)
2. Compress via media_compressor.compress_audio(temp, output_path)
3. Save compressed file via media_store.save(agent_id, compressed_bytes, "ogg", filename)
4. Generate description via media_describer.describe_audio(compressed_path, content_type)
5. Build episode text: "[Audio: {filename}]\n\n{description.text}\n\n[Media reference: {media_ref.path}]"
6. Store episode via _store_episode(agent_id, episode_text, "ingestion_audio", target_schema)
7. Embed episode via _embed_episode(...)
8. Enqueue extraction via _enqueue_extraction(...)
9. Return MediaIngestionResult with media_ref
10. Clean up temp files in finally block
```

Implement `process_video` (same flow, using `compress_video` and `describe_video`, plus optional `extract_thumbnail`).

If any media service is `None` (mock mode without ffmpeg), fall back to storing raw content reference with a placeholder description.

#### 4.3 — Episode metadata enrichment

The episode `metadata` dict for media episodes should include:

```python
metadata = {
    **user_metadata,
    "media_ref": media_ref.model_dump(),  # path, original_filename, content_type, etc.
    "media_type": "audio" | "video",
    "duration_seconds": compressed.duration_seconds,
    "description_model": description.model,
    "description_tokens": description.token_count,
}
```

This ensures agents using `recall` can see that the episode originated from media and where to find it.

**Verification**:
```bash
uv run pytest tests/test_episode_processor.py -v
# Extended with new test cases for process_audio / process_video
```

Write tests using mock services (MockMediaDescriptionService, InMemoryRepository). Verify:
- Episode created with correct source_type
- Metadata contains media_ref
- Episode text includes description

**Commit**: `feat(media): extend IngestionProcessor with audio/video pipeline`

---

## Stage 5: API Endpoints for Audio and Video

**Goal**: Add `POST /ingest/audio` and `POST /ingest/video` endpoints with proper content-type validation and size limits.

### Steps

#### 5.1 — New accepted content types

Add to `src/neocortex/ingestion/routes.py`:

```python
_ACCEPTED_AUDIO_TYPES = {
    "audio/mpeg",        # .mp3
    "audio/wav",         # .wav
    "audio/x-wav",       # .wav (alternative)
    "audio/ogg",         # .ogg
    "audio/flac",        # .flac
    "audio/aac",         # .aac
    "audio/mp4",         # .m4a
    "audio/webm",        # .weba
}

_ACCEPTED_VIDEO_TYPES = {
    "video/mp4",         # .mp4
    "video/mpeg",        # .mpeg
    "video/webm",        # .webm
    "video/quicktime",   # .mov
    "video/x-msvideo",   # .avi
    "video/x-matroska",  # .mkv
    "video/3gpp",        # .3gp
}
```

#### 5.2 — Audio endpoint

```python
@router.post("/audio", response_model=MediaIngestionResult)
async def ingest_audio(
    file: UploadFile,
    request: Request,
    agent_id: Annotated[str, Depends(get_agent_id)],
    metadata: str | None = Form(default=None),
    target_graph: str | None = Form(default=None),
) -> MediaIngestionResult:
    # 1. Permission check (same as document)
    # 2. Validate content_type in _ACCEPTED_AUDIO_TYPES (415 if not)
    # 3. Read file with media_max_upload_bytes limit (413 if exceeded)
    # 4. Parse metadata JSON
    # 5. Call processor.process_audio(...)
    # 6. Audit log: logger.bind(action_log=True).info("ingest_audio", ...)
```

#### 5.3 — Video endpoint

```python
@router.post("/video", response_model=MediaIngestionResult)
async def ingest_video(
    file: UploadFile,
    request: Request,
    agent_id: Annotated[str, Depends(get_agent_id)],
    metadata: str | None = Form(default=None),
    target_graph: str | None = Form(default=None),
) -> MediaIngestionResult:
    # Same structure as audio, validate against _ACCEPTED_VIDEO_TYPES
```

#### 5.4 — Wire media services into app lifespan

Update `src/neocortex/ingestion/app.py` lifespan:

```python
# After create_services():
media_store = MediaFileStore(settings.media_store_path)
if not settings.mock_db and shutil.which("ffmpeg"):
    media_compressor = MediaCompressor()
    media_describer = MediaDescriptionService(
        api_key=os.environ.get("GOOGLE_API_KEY", ""),
        model=settings.media_description_model,
        max_output_tokens=settings.media_description_max_tokens,
    )
else:
    media_compressor = None
    media_describer = MockMediaDescriptionService() if settings.mock_db else None

processor = EpisodeProcessor(
    repo=ctx["repo"],
    embeddings=ctx.get("embeddings"),
    job_app=ctx.get("job_app"),
    extraction_enabled=settings.extraction_enabled,
    media_store=media_store,
    media_compressor=media_compressor,
    media_describer=media_describer,
)
```

**Verification**:
```bash
# Start server in mock mode
NEOCORTEX_MOCK_DB=true uv run python -m neocortex.ingestion &

# Test audio upload
curl -X POST localhost:8001/ingest/audio \
  -F "file=@test_audio.wav;type=audio/wav"
# Should return {"status":"stored","episodes_created":1,...,"media_ref":{...}}

# Test video upload
curl -X POST localhost:8001/ingest/video \
  -F "file=@test_video.mp4;type=video/mp4"

# Test rejection of unsupported type
curl -X POST localhost:8001/ingest/audio \
  -F "file=@test.txt;type=text/plain"
# Should return 415
```

**Commit**: `feat(media): add POST /ingest/audio and /ingest/video endpoints`

---

## Stage 6: Unit and Integration Tests

**Goal**: Comprehensive test coverage for the media pipeline.

### Steps

#### 6.1 — Unit tests for MediaFileStore

`tests/test_media_store.py`:
- `test_save_creates_file` — save bytes, verify file exists at returned path
- `test_save_creates_agent_directory` — verify agent-scoped directory
- `test_get_path_returns_none_for_missing` — non-existent UUID
- `test_delete_removes_file` — save then delete, verify gone
- Use `tmp_path` fixture for isolation

#### 6.2 — Unit tests for MediaCompressor

`tests/test_media_compressor.py`:
- `test_compress_audio` — 1s WAV → opus, assert smaller
- `test_compress_video` — skip if no ffmpeg; minimal test with synthetic video if possible
- `test_probe_duration` — verify duration extraction
- `test_ffmpeg_not_found` — verify graceful error when ffmpeg missing
- Mark all with `@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")`

#### 6.3 — Unit tests for media ingestion flow

`tests/test_media_ingestion.py`:
- Use `InMemoryRepository` + `MockMediaDescriptionService` + real `MediaFileStore` (with `tmp_path`)
- `test_process_audio_stores_episode` — verify episode created with source_type="ingestion_audio"
- `test_process_audio_metadata_contains_media_ref` — verify media_ref in metadata
- `test_process_video_stores_episode` — same for video
- `test_process_audio_without_compressor_falls_back` — verify graceful degradation
- `test_audio_endpoint_rejects_wrong_content_type` — HTTP 415 via test client
- `test_video_endpoint_rejects_oversized_file` — HTTP 413 via test client

#### 6.4 — Integration test (optional, gated)

`tests/integration/test_media_gemini.py`:
- Gated behind `GOOGLE_API_KEY` env var
- Upload a tiny audio file, verify Gemini returns a non-empty description
- Mark with `@pytest.mark.skipif(not os.environ.get("GOOGLE_API_KEY"), reason="No API key")`

**Verification**: `uv run pytest tests/ -v` — all existing + new tests pass

**Commit**: `test(media): add comprehensive media ingestion tests`

---

## Stage 7: Docker and Documentation

**Goal**: Ensure the media pipeline works in the Docker Compose environment and update documentation.

### Steps

#### 7.1 — Update Docker images

Update `docker/mcp/Dockerfile` and `docker/ingestion/Dockerfile` (or the shared base):

```dockerfile
# Add ffmpeg and ImageMagick to the image
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*
```

#### 7.2 — Docker Compose volume for media store

Update `docker-compose.yml`:

```yaml
services:
  ingestion:
    # ... existing config ...
    volumes:
      - media_store:/app/media_store
    environment:
      - NEOCORTEX_MEDIA_STORE_PATH=/app/media_store

volumes:
  media_store:
```

#### 7.3 — Update docs/development.md

Add section on media ingestion:
- System requirements (ffmpeg, optional ImageMagick)
- New environment variables
- New endpoints with curl examples
- Media storage path and cleanup considerations
- Size limits and supported formats

#### 7.4 — Update CLAUDE.md codebase map

Add new files to the codebase map section and update the ingestion description.

**Verification**:
```bash
docker compose build ingestion
docker compose up -d postgres ingestion
curl -X POST localhost:8001/ingest/audio -F "file=@test.wav;type=audio/wav"
```

**Commit**: `docs(media): update Docker config and documentation for media ingestion`

---

## Stage 8: Final Validation

**Goal**: End-to-end verification that the entire pipeline works.

### Steps

1. Run full test suite: `uv run pytest tests/ -v`
2. Start mock server: `NEOCORTEX_MOCK_DB=true uv run python -m neocortex.ingestion`
3. Upload audio file → verify episode appears in mock store with description
4. Upload video file → verify episode appears with description and thumbnail
5. Verify existing text/document/events endpoints still work unchanged
6. Verify health endpoint still works
7. Verify 415 for unsupported media types
8. Verify 413 for oversized uploads

**Commit**: No commit — validation stage only.

---

## Progress Tracker

| Stage | Description | Status | Notes |
|-------|-------------|--------|-------|
| 1 | Settings, models, media file store | `PENDING` | |
| 2 | Media compressor (ffmpeg) | `PENDING` | |
| 3 | Gemini media description service | `PENDING` | |
| 4 | Extend IngestionProcessor + EpisodeProcessor | `PENDING` | |
| 5 | API endpoints for audio/video | `PENDING` | |
| 6 | Unit and integration tests | `PENDING` | |
| 7 | Docker and documentation | `PENDING` | |
| 8 | Final validation | `PENDING` | |

**Last stage completed**: —
**Last updated by**: —
