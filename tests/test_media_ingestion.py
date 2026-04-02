"""Unit tests for the media ingestion flow through EpisodeProcessor and HTTP endpoints.

Uses InMemoryRepository + MockMediaDescriptionService + real MediaFileStore (tmp_path).
MediaCompressor is mocked to avoid requiring ffmpeg.
"""

import io
import os
import struct
import wave
from collections.abc import Generator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from neocortex.db.mock import InMemoryRepository
from neocortex.ingestion.episode_processor import EpisodeProcessor
from neocortex.ingestion.media_compressor import CompressedMedia
from neocortex.ingestion.media_description_mock import MockMediaDescriptionService
from neocortex.ingestion.media_models import MediaIngestionResult
from neocortex.ingestion.media_store import MediaFileStore


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.fixture
def media_store(tmp_path) -> MediaFileStore:
    return MediaFileStore(str(tmp_path / "media"))


@pytest.fixture
def mock_describer() -> MockMediaDescriptionService:
    return MockMediaDescriptionService()


@pytest.fixture
def mock_compressor(tmp_path):
    """A mock compressor that copies the input file and returns CompressedMedia."""
    compressor = AsyncMock()
    compressor.available = True

    async def fake_compress_audio(input_path: str, output_path: str) -> CompressedMedia:
        # Ensure output has .ogg extension
        if not output_path.endswith(".ogg"):
            output_path = output_path + ".ogg"
        # Copy input to output to simulate compression
        import shutil

        shutil.copy2(input_path, output_path)
        size = os.path.getsize(output_path)
        return CompressedMedia(
            path=output_path,
            size_bytes=size,
            duration_seconds=1.0,
            mime_type="audio/ogg",
        )

    async def fake_compress_video(input_path: str, output_path: str) -> CompressedMedia:
        if not output_path.endswith(".mp4"):
            output_path = output_path + ".mp4"
        import shutil

        shutil.copy2(input_path, output_path)
        size = os.path.getsize(output_path)
        return CompressedMedia(
            path=output_path,
            size_bytes=size,
            duration_seconds=2.5,
            mime_type="video/mp4",
        )

    compressor.compress_audio = fake_compress_audio
    compressor.compress_video = fake_compress_video
    return compressor


@pytest.fixture
def processor(repo, media_store, mock_describer, mock_compressor) -> EpisodeProcessor:
    return EpisodeProcessor(
        repo=repo,
        media_store=media_store,
        media_compressor=mock_compressor,
        media_describer=mock_describer,
    )


def _write_wav_file(path: str) -> str:
    """Write a minimal 1-second WAV to the given path and return it."""
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(struct.pack("<" + "h" * 16000, *([0] * 16000)))
    return path


@pytest.fixture
def wav_file(tmp_path) -> str:
    """Write a minimal WAV file and return its path."""
    return _write_wav_file(str(tmp_path / "test.wav"))


@pytest.fixture
def mp4_file(tmp_path) -> str:
    """Write a fake MP4 file and return its path."""
    path = str(tmp_path / "test.mp4")
    with open(path, "wb") as f:
        f.write(b"\x00\x00\x00\x1c\x66\x74\x79\x70\x69\x73\x6f\x6d" + b"\x00" * 1000)
    return path


# --- EpisodeProcessor tests ---


@pytest.mark.asyncio
async def test_process_audio_stores_episode(processor: EpisodeProcessor, repo: InMemoryRepository, wav_file: str):
    """process_audio creates an episode with source_type='ingestion_audio'."""
    result = await processor.process_audio(
        agent_id="test_agent",
        filename="recording.wav",
        raw_path=wav_file,
        content_type="audio/wav",
        metadata={},
    )

    assert isinstance(result, MediaIngestionResult)
    assert result.status == "stored"
    assert result.episodes_created == 1

    # Verify episode stored in repo
    assert len(repo._episodes) == 1
    episode = repo._episodes[0]
    assert episode["agent_id"] == "test_agent"
    assert episode["source_type"] == "ingestion_audio"


@pytest.mark.asyncio
async def test_process_audio_episode_text_contains_media_ref(
    processor: EpisodeProcessor, repo: InMemoryRepository, wav_file: str
):
    """Episode text contains the media_ref relative path and description."""
    result = await processor.process_audio(
        agent_id="test_agent",
        filename="meeting.wav",
        raw_path=wav_file,
        content_type="audio/wav",
        metadata={},
    )

    assert result.media_ref is not None
    episode_text = repo._episodes[0]["content"]

    # Should contain the media ref path
    assert result.media_ref.relative_path in episode_text

    # Should contain the mock description text
    assert "Mock audio description" in episode_text

    # Should contain the filename header
    assert "[Audio: meeting.wav]" in episode_text

    # Should contain media metadata section
    assert "Media metadata:" in episode_text
    assert "media_type: audio" in episode_text


@pytest.mark.asyncio
async def test_process_audio_returns_media_ref(processor: EpisodeProcessor, wav_file: str):
    """process_audio returns a MediaIngestionResult with a valid media_ref."""
    result = await processor.process_audio(
        agent_id="test_agent",
        filename="call.wav",
        raw_path=wav_file,
        content_type="audio/wav",
        metadata={},
    )

    assert result.media_ref is not None
    assert result.media_ref.original_filename == "call.wav"
    assert result.media_ref.content_type == "audio/wav"
    assert result.media_ref.relative_path.startswith("test_agent/")
    assert result.media_ref.relative_path.endswith(".ogg")


@pytest.mark.asyncio
async def test_process_video_stores_episode(processor: EpisodeProcessor, repo: InMemoryRepository, mp4_file: str):
    """process_video creates an episode with source_type='ingestion_video'."""
    result = await processor.process_video(
        agent_id="test_agent",
        filename="clip.mp4",
        raw_path=mp4_file,
        content_type="video/mp4",
        metadata={},
    )

    assert isinstance(result, MediaIngestionResult)
    assert result.status == "stored"
    assert result.episodes_created == 1

    episode = repo._episodes[0]
    assert episode["source_type"] == "ingestion_video"


@pytest.mark.asyncio
async def test_process_video_episode_text_contains_metadata(
    processor: EpisodeProcessor, repo: InMemoryRepository, mp4_file: str
):
    """Video episode text includes correct metadata."""
    result = await processor.process_video(
        agent_id="test_agent",
        filename="demo.mp4",
        raw_path=mp4_file,
        content_type="video/mp4",
        metadata={},
    )

    assert result.media_ref is not None
    episode_text = repo._episodes[0]["content"]
    assert "[Video: demo.mp4]" in episode_text
    assert "Mock video description" in episode_text
    assert "media_type: video" in episode_text
    assert result.media_ref.relative_path in episode_text


@pytest.mark.asyncio
async def test_process_audio_dedup_skips_duplicate(processor: EpisodeProcessor, repo: InMemoryRepository, tmp_path):
    """Same audio file ingested twice: second returns 'skipped'."""
    wav1 = _write_wav_file(str(tmp_path / "first.wav"))
    wav2 = _write_wav_file(str(tmp_path / "second.wav"))  # identical content

    r1 = await processor.process_audio(
        agent_id="test_agent", filename="first.wav", raw_path=wav1, content_type="audio/wav", metadata={}
    )
    assert r1.status == "stored"

    r2 = await processor.process_audio(
        agent_id="test_agent", filename="second.wav", raw_path=wav2, content_type="audio/wav", metadata={}
    )
    assert r2.status == "skipped"
    assert r2.episodes_created == 0
    assert r2.existing_episode_id is not None
    assert r2.content_hash == r1.content_hash


@pytest.mark.asyncio
async def test_process_audio_force_bypasses_dedup(processor: EpisodeProcessor, repo: InMemoryRepository, tmp_path):
    """force=True on audio stores even if content was already ingested."""
    wav1 = _write_wav_file(str(tmp_path / "first.wav"))
    wav2 = _write_wav_file(str(tmp_path / "second.wav"))

    r1 = await processor.process_audio(
        agent_id="test_agent", filename="first.wav", raw_path=wav1, content_type="audio/wav", metadata={}
    )
    assert r1.status == "stored"

    r2 = await processor.process_audio(
        agent_id="test_agent",
        filename="second.wav",
        raw_path=wav2,
        content_type="audio/wav",
        metadata={},
        force=True,
    )
    assert r2.status == "stored"
    assert r2.episodes_created == 1


@pytest.mark.asyncio
async def test_process_audio_without_compressor_returns_failed(
    repo: InMemoryRepository, media_store: MediaFileStore, mock_describer: MockMediaDescriptionService, wav_file: str
):
    """When no compressor is available, process_audio returns status='failed'."""
    processor = EpisodeProcessor(
        repo=repo,
        media_store=media_store,
        media_compressor=None,
        media_describer=mock_describer,
    )

    result = await processor.process_audio(
        agent_id="test_agent",
        filename="test.wav",
        raw_path=wav_file,
        content_type="audio/wav",
        metadata={},
    )

    assert result.status == "failed"
    assert result.episodes_created == 0
    assert "ffmpeg" in result.message.lower()


@pytest.mark.asyncio
async def test_process_video_without_compressor_returns_failed(
    repo: InMemoryRepository, media_store: MediaFileStore, mock_describer: MockMediaDescriptionService, mp4_file: str
):
    """When no compressor is available, process_video returns status='failed'."""
    processor = EpisodeProcessor(
        repo=repo,
        media_store=media_store,
        media_compressor=None,
        media_describer=mock_describer,
    )

    result = await processor.process_video(
        agent_id="test_agent",
        filename="test.mp4",
        raw_path=mp4_file,
        content_type="video/mp4",
        metadata={},
    )

    assert result.status == "failed"
    assert result.episodes_created == 0


# --- HTTP endpoint tests ---


@pytest.fixture
def anon_client() -> Generator[TestClient]:
    from neocortex.ingestion.app import create_app
    from neocortex.mcp_settings import MCPSettings

    settings = MCPSettings(auth_mode="none", mock_db=True)
    app = create_app(settings)
    with TestClient(app) as client:
        yield client


def test_audio_endpoint_rejects_wrong_content_type(anon_client: TestClient):
    """POST /ingest/audio returns 415 for non-audio content types."""
    resp = anon_client.post(
        "/ingest/audio",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp.status_code == 415


def test_video_endpoint_rejects_wrong_content_type(anon_client: TestClient):
    """POST /ingest/video returns 415 for non-video content types."""
    resp = anon_client.post(
        "/ingest/video",
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF-fake"), "application/pdf")},
    )
    assert resp.status_code == 415


def test_audio_endpoint_rejects_oversized_file(anon_client: TestClient):
    """POST /ingest/audio returns 413 for files exceeding the 100MB limit."""
    # The default media_max_upload_bytes is 100 MB; send just over
    big_content = b"\x00" * (100 * 1024 * 1024 + 1)
    resp = anon_client.post(
        "/ingest/audio",
        files={"file": ("big.wav", io.BytesIO(big_content), "audio/wav")},
    )
    assert resp.status_code == 413


def test_video_endpoint_rejects_oversized_file(anon_client: TestClient):
    """POST /ingest/video returns 413 for files exceeding the 100MB limit."""
    big_content = b"\x00" * (100 * 1024 * 1024 + 1)
    resp = anon_client.post(
        "/ingest/video",
        files={"file": ("big.mp4", io.BytesIO(big_content), "video/mp4")},
    )
    assert resp.status_code == 413
