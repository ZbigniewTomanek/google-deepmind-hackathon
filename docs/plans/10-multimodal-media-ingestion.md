# Plan 10: Multimodal Audio/Video Ingestion via Gemini 3 Flash Preview

## Overview

Extend the ingestion API with audio and video support. Media files are pre-processed through a two-stage pipeline: (1) ffmpeg compression to create storage-efficient minimized copies, (2) Gemini 3 Flash Preview multimodal inference to generate rich text descriptions. The text description is stored as an episode (feeds into the existing extraction pipeline), while the compressed media file is persisted on the filesystem with a stable relative-path reference so agents can access the original content when text alone is insufficient.

**Key design decisions:**
- Media files are **not** stored in PostgreSQL — they live on a configurable filesystem path (`NEOCORTEX_MEDIA_STORE_PATH`, default `./media_store/`)
- Each media file gets a deterministic path: `{store_path}/{agent_id}/{uuid}.{ext}`
- The episode text embeds structured media metadata (relative path, original filename, content type, etc.) — no `store_episode` protocol changes needed
- Compression is mandatory before Gemini upload to reduce token cost and storage — audio compressed to 64kbps mono opus, video to 480p CRF-30 h264 with 64kbps audio
- `IngestionProcessor` protocol gains two new methods (`process_audio`, `process_video`) and all existing methods are aligned to include the `target_schema` parameter that the implementation already accepts
- Mock mode skips compression and Gemini calls, stores a placeholder description
- ffmpeg is a system dependency (must be installed on host)
- **Known limitation**: no concurrency control on media processing — concurrent uploads each spawn an ffmpeg process + Gemini API call. Acceptable for hackathon scale; add `asyncio.Semaphore` if load becomes a concern

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

from neocortex.ingestion.models import IngestionResult

class MediaRef(BaseModel):
    """Reference to a stored media file on the filesystem."""
    relative_path: str     # Path relative to media store root ({agent_id}/{uuid}.{ext})
    original_filename: str # Original upload filename
    content_type: str      # MIME type of original upload
    compressed_size: int   # Size in bytes after compression
    duration_seconds: float | None = None  # Duration if available

class MediaIngestionResult(IngestionResult):
    """Extended result for media ingestion — inherits status/episodes_created/message."""
    media_ref: MediaRef | None = None  # Reference to stored media
```

#### 1.3 — MediaFileStore

Create `src/neocortex/ingestion/media_store.py`:

```python
class MediaFileStore:
    """Persists compressed media files on the local filesystem.

    Directory layout: {base_path}/{agent_id}/{uuid}.{ext}
    All returned paths in MediaRef are relative to base_path.
    """

    def __init__(self, base_path: str) -> None: ...

    async def save(
        self, agent_id: str, source_path: str, extension: str,
        original_filename: str, content_type: str,
        duration_seconds: float | None = None,
    ) -> MediaRef: ...
        # 1. Ensure {base_path}/{agent_id}/ exists (os.makedirs, exist_ok=True)
        # 2. Generate UUID4 filename
        # 3. Move source_path to {base_path}/{agent_id}/{uuid}.{ext}
        #    via shutil.move (wrapped in anyio.to_thread.run_sync)
        # 4. Get file size via os.path.getsize
        # 5. Return MediaRef with relative_path="{agent_id}/{uuid}.{ext}"

    def resolve(self, relative_path: str) -> str: ...
        # Return absolute path: os.path.join(self._base_path, relative_path)

    async def delete(self, relative_path: str) -> bool: ...
        # Remove file at resolve(relative_path), return success
```

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

    async def probe_duration(self, path: str) -> float: ...
        # ffprobe -v quiet -show_entries format=duration -of csv=p=0 {path}

    @staticmethod
    async def _run_ffmpeg(args: list[str]) -> asyncio.subprocess.Process: ...
        # Run via asyncio.create_subprocess_exec(*args, stdout=PIPE, stderr=PIPE)
        # Await proc.communicate() for output
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

#### 4.1 — Align and extend protocol

Update `src/neocortex/ingestion/protocol.py`.

The existing protocol methods omit `target_schema` even though `EpisodeProcessor` already accepts
it. Fix all existing signatures to match the implementation, then add the new media methods:

```python
from neocortex.ingestion.models import IngestionResult
from neocortex.ingestion.media_models import MediaIngestionResult


class IngestionProcessor(Protocol):
    """Abstract interface for ingestion processing backends."""

    async def process_text(
        self, agent_id: str, text: str, metadata: dict,
        target_schema: str | None = None,
    ) -> IngestionResult: ...

    async def process_document(
        self, agent_id: str, filename: str, content: bytes,
        content_type: str, metadata: dict,
        target_schema: str | None = None,
    ) -> IngestionResult: ...

    async def process_events(
        self, agent_id: str, events: list[dict], metadata: dict,
        target_schema: str | None = None,
    ) -> IngestionResult: ...

    async def process_audio(
        self, agent_id: str, filename: str, content: bytes,
        content_type: str, metadata: dict,
        target_schema: str | None = None,
    ) -> MediaIngestionResult: ...

    async def process_video(
        self, agent_id: str, filename: str, content: bytes,
        content_type: str, metadata: dict,
        target_schema: str | None = None,
    ) -> MediaIngestionResult: ...
```

No changes needed in `EpisodeProcessor` or `routes.py` — they already pass `target_schema`.
Existing tests continue to work because `target_schema` defaults to `None`.

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
1. Write raw upload bytes to temp file (tempfile.NamedTemporaryFile, suffix matching input type)
2. Compress via media_compressor.compress_audio(temp_path, compressed_temp_path)
3. Generate description via media_describer.describe_audio(compressed_temp_path, content_type)
4. Save compressed file via media_store.save(agent_id, compressed_temp_path, "ogg", filename, ...)
   — this moves the file into the store; no redundant byte copy
5. Build episode text with embedded structured metadata (see 4.3 below)
6. Store episode via _store_episode(agent_id, episode_text, "ingestion_audio", target_schema)
7. Embed episode via _embed_episode(...)
8. Enqueue extraction via _enqueue_extraction(...)
9. Return MediaIngestionResult with media_ref
10. Clean up temp files in finally block (only the raw upload temp; compressed was moved by store)
```

Implement `process_video` (same flow, using `compress_video` and `describe_video`).

If `media_compressor` is `None` (no ffmpeg), return `MediaIngestionResult(status="failed", episodes_created=0, message="ffmpeg not available")`. If `media_describer` is `None`, use `MockMediaDescriptionService` as fallback.

#### 4.3 — Embed metadata in episode text (no protocol changes needed)

The current `store_episode` protocol has no `metadata` parameter and adding one would require
changes across the protocol, both implementations, and the DB schema. Instead, embed structured
metadata directly in the episode text so it is searchable via `recall` and parseable by the
extraction pipeline:

```python
episode_text = f"""[Audio: {filename}]

{description.text}

---
Media metadata:
- media_ref: {media_ref.relative_path}
- original_filename: {media_ref.original_filename}
- media_type: audio
- content_type: {media_ref.content_type}
- compressed_size: {media_ref.compressed_size}
- duration_seconds: {compressed.duration_seconds}
- description_model: {description.model}
- description_tokens: {description.token_count}
"""
```

This keeps the storage layer unchanged while making media provenance visible to agents via recall.
Paths are relative to the media store root — use `media_store.resolve(relative_path)` to get
the absolute path when needed.

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

if settings.mock_db:
    # Mock mode: no compression, placeholder descriptions
    media_compressor = None
    media_describer = MockMediaDescriptionService()
elif shutil.which("ffmpeg"):
    # Production with ffmpeg available
    media_compressor = MediaCompressor()
    media_describer = MediaDescriptionService(
        api_key=os.environ.get("GOOGLE_API_KEY", ""),
        model=settings.media_description_model,
        max_output_tokens=settings.media_description_max_tokens,
    )
else:
    # Production without ffmpeg — media endpoints will return 503
    logger.warning("ffmpeg not found on PATH — media ingestion disabled")
    media_compressor = None
    media_describer = None

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
- `test_save_moves_file` — save a temp file, verify it exists at the resolved store path
- `test_save_creates_agent_directory` — verify agent-scoped directory created
- `test_save_returns_relative_path` — verify `media_ref.relative_path` is `{agent_id}/{uuid}.{ext}`
- `test_resolve_returns_absolute` — verify `resolve()` joins base path correctly
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
- `test_process_audio_episode_text_contains_media_ref` — verify relative_path in episode text
- `test_process_video_stores_episode` — same for video
- `test_process_audio_without_compressor_returns_failed` — verify status="failed" when no ffmpeg
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

## Stage 7: Documentation

**Goal**: Update documentation to reflect the new media ingestion capabilities.

**Prerequisite**: ffmpeg and ffprobe must be installed on the host (assumed available).

### Steps

#### 7.1 — Update docs/development.md

Add section on media ingestion:
- System requirements (ffmpeg must be on PATH)
- New environment variables (`NEOCORTEX_MEDIA_STORE_PATH`, `GOOGLE_API_KEY`)
- New settings (`media_store_path`, `media_max_upload_bytes`, `media_description_model`, `media_description_max_tokens`)
- New endpoints with curl examples
- Media storage layout and relative path scheme
- Size limits and supported formats

#### 7.2 — Update CLAUDE.md codebase map

Add new files to the codebase map section:
```
  ingestion/
    media_models.py      # MediaRef, MediaIngestionResult, CompressedMedia
    media_store.py       # Filesystem-based media file store
    media_compressor.py  # ffmpeg compression service
    media_description.py # Gemini multimodal description service
    media_description_mock.py # Mock description service for tests
```

Update the ingestion description to mention audio/video support.

**Verification**: Review docs render correctly, no broken references.

**Commit**: `docs(media): update development docs and codebase map for media ingestion`

---

## Stage 8: E2E Validation Script

**Goal**: Create an automated end-to-end validation script that starts the ingestion server in mock mode, exercises all media endpoints (plus existing ones for regression), and asserts correct responses. This makes the pipeline reproducibly testable without manual curl invocations.

### Steps

#### 8.1 — Generate synthetic test fixtures

Create `tests/e2e/fixtures/` with minimal synthetic media files generated via Python (no binary blobs checked in):

Create `tests/e2e/conftest.py`:
```python
import wave, struct, tempfile, os
import pytest

@pytest.fixture(scope="session")
def synthetic_wav(tmp_path_factory) -> str:
    """Generate a 1-second mono WAV file (silence)."""
    path = str(tmp_path_factory.mktemp("fixtures") / "test.wav")
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(struct.pack("<" + "h" * 16000, *([0] * 16000)))
    return path

@pytest.fixture(scope="session")
def synthetic_mp4(tmp_path_factory) -> str:
    """Generate a minimal valid MP4 via ffmpeg (1s black, silent). Skip if no ffmpeg."""
    import shutil
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    path = str(tmp_path_factory.mktemp("fixtures") / "test.mp4")
    os.system(
        f'ffmpeg -y -f lavfi -i color=black:s=160x120:d=1 '
        f'-f lavfi -i anullsrc=r=16000:cl=mono -t 1 '
        f'-c:v libx264 -crf 51 -c:a aac -b:a 32k -shortest "{path}" '
        f'-loglevel quiet'
    )
    return path

@pytest.fixture(scope="session")
def oversized_bytes() -> bytes:
    """Return bytes just over the 100 MB limit for size-rejection tests."""
    return b"\x00" * (100 * 1024 * 1024 + 1)
```

#### 8.2 — E2E test suite

Create `tests/e2e/test_media_e2e.py`:

```python
"""
End-to-end tests for the media ingestion pipeline.

Starts the ingestion app in mock mode (NEOCORTEX_MOCK_DB=true) via the
FastAPI TestClient and exercises the full request→response cycle for
audio and video endpoints, plus regression checks on existing endpoints.
"""
import json, pytest
from fastapi.testclient import TestClient

@pytest.fixture()
def client():
    """Create a TestClient against the ingestion app in mock mode."""
    import os
    os.environ["NEOCORTEX_MOCK_DB"] = "true"
    from neocortex.ingestion.app import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c

class TestAudioEndpoint:
    def test_upload_wav_returns_stored(self, client, synthetic_wav):
        with open(synthetic_wav, "rb") as f:
            resp = client.post(
                "/ingest/audio",
                files={"file": ("test.wav", f, "audio/wav")},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "stored"
        assert body["episodes_created"] >= 1
        assert body.get("media_ref") is not None
        assert body["media_ref"]["original_filename"] == "test.wav"

    def test_rejects_unsupported_content_type(self, client, tmp_path):
        fake = tmp_path / "notes.txt"
        fake.write_text("hello")
        with open(fake, "rb") as f:
            resp = client.post(
                "/ingest/audio",
                files={"file": ("notes.txt", f, "text/plain")},
            )
        assert resp.status_code == 415

    def test_rejects_oversized_upload(self, client, oversized_bytes):
        resp = client.post(
            "/ingest/audio",
            files={"file": ("big.wav", oversized_bytes, "audio/wav")},
        )
        assert resp.status_code == 413

class TestVideoEndpoint:
    def test_upload_mp4_returns_stored(self, client, synthetic_mp4):
        with open(synthetic_mp4, "rb") as f:
            resp = client.post(
                "/ingest/video",
                files={"file": ("test.mp4", f, "video/mp4")},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "stored"
        assert body["episodes_created"] >= 1
        assert body.get("media_ref") is not None

    def test_rejects_unsupported_content_type(self, client, tmp_path):
        fake = tmp_path / "doc.pdf"
        fake.write_bytes(b"%PDF-fake")
        with open(fake, "rb") as f:
            resp = client.post(
                "/ingest/video",
                files={"file": ("doc.pdf", f, "application/pdf")},
            )
        assert resp.status_code == 415

class TestRegressionExistingEndpoints:
    """Ensure adding media endpoints did not break text/document/events."""

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_ingest_text(self, client):
        resp = client.post(
            "/ingest/text",
            json={"text": "Regression test content", "metadata": {}},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "stored"

    def test_ingest_document(self, client):
        resp = client.post(
            "/ingest/document",
            files={"file": ("test.txt", b"doc content", "text/plain")},
        )
        assert resp.status_code == 200

    def test_ingest_events(self, client):
        resp = client.post(
            "/ingest/events",
            json={"events": [{"type": "test", "data": "hello"}], "metadata": {}},
        )
        assert resp.status_code == 200
```

#### 8.3 — Shell convenience script

Create `scripts/e2e_media.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
echo "=== Running media ingestion E2E tests ==="
NEOCORTEX_MOCK_DB=true uv run pytest tests/e2e/test_media_e2e.py -v --tb=short
echo ""
echo "=== Running full test suite (regression) ==="
uv run pytest tests/ -v --tb=short
echo ""
echo "✓ All E2E and regression tests passed."
```

Make executable: `chmod +x scripts/e2e_media.sh`

**Verification**:
```bash
bash scripts/e2e_media.sh
# All tests should pass (video tests skip gracefully if ffmpeg is missing)
```

**Commit**: `test(media): add automated e2e validation script and test suite`

---

## Stage 9: Final Validation and Cleanup

**Goal**: Run the full automated E2E suite, verify no regressions, confirm the plan is complete, and update the progress tracker.

### Steps

1. Run the e2e script: `bash scripts/e2e_media.sh`
2. Run full test suite including all prior tests: `uv run pytest tests/ -v`
3. Verify no lint/type errors: `uv run ruff check src/` (if ruff is configured)
4. Review that all new files are tracked by git and none contain secrets or large binaries
5. Confirm documentation from Stage 7 reflects the final implementation (endpoint signatures, settings names, supported formats match the code)
6. Update the progress tracker below — mark all stages `DONE`

**Commit**: `chore(media): mark multimodal ingestion plan complete`

---

## Progress Tracker

| Stage | Description | Status | Notes |
|-------|-------------|--------|-------|
| 1 | Settings, models, media file store | `DONE` | Added 4 settings to MCPSettings, MediaRef/MediaIngestionResult models, MediaFileStore with save/resolve/delete |
| 2 | Media compressor (ffmpeg) | `DONE` | MediaCompressor with compress_audio/compress_video/probe_duration, CompressedMedia dataclass, ffmpeg availability check, 6 passing tests |
| 3 | Gemini media description service | `DONE` | MediaDescriptionService with Gemini Files API upload/poll/generate/cleanup, MockMediaDescriptionService, MediaDescription dataclass, audit logging, 7 passing tests |
| 4 | Extend IngestionProcessor + EpisodeProcessor | `DONE` | Protocol aligned with target_schema, added process_audio/process_video to protocol and EpisodeProcessor with full compress→describe→store→embed→extract pipeline |
| 5 | API endpoints for audio/video | `DONE` | Added POST /ingest/audio and /ingest/video endpoints with content-type validation, size limits, audit logging; wired media services into app lifespan |
| 6 | Unit and integration tests | `DONE` | 7 MediaFileStore tests, 11 media ingestion tests (processor + HTTP endpoints), 1 Gemini integration test; 19 new tests total, all passing |
| 7 | Documentation | `DONE` | Updated development.md with media ingestion section (system requirements, env vars, settings, endpoints, curl examples, storage layout, supported formats); updated CLAUDE.md codebase map with 5 new media files |
| 8 | E2E validation script and tests | `DONE` | E2E test suite (9 tests: audio/video upload, content-type rejection, size rejection, regression for text/doc/events/health), synthetic fixtures, shell script, MockMediaCompressor for mock mode |
| 9 | Final validation and cleanup | `DONE` | E2E suite: 9/9 passed; full suite: 380 passed, 5 skipped; ruff: all checks passed; docs verified aligned with implementation |

**Last stage completed**: Stage 9 — Final Validation and Cleanup
**Last updated by**: plan-runner-agent
