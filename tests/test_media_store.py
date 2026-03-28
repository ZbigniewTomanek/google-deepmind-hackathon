import os

import pytest

from neocortex.ingestion.media_models import MediaRef
from neocortex.ingestion.media_store import MediaFileStore


@pytest.fixture
def store(tmp_path) -> MediaFileStore:
    return MediaFileStore(str(tmp_path))


@pytest.fixture
def source_file(tmp_path) -> str:
    """Create a temporary file to act as compressed media."""
    path = str(tmp_path / "source_input" / "compressed.ogg")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\x00" * 256)
    return path


@pytest.mark.asyncio
async def test_save_moves_file(store: MediaFileStore, source_file: str):
    """save() moves the source file into the store directory."""
    ref = await store.save(
        agent_id="agent1",
        source_path=source_file,
        extension="ogg",
        original_filename="recording.ogg",
        content_type="audio/ogg",
    )

    # Source file should no longer exist (it was moved)
    assert not os.path.exists(source_file)

    # File should exist at resolved store path
    resolved = store.resolve(ref.relative_path)
    assert os.path.exists(resolved)


@pytest.mark.asyncio
async def test_save_creates_agent_directory(store: MediaFileStore, source_file: str):
    """save() creates the agent-scoped directory if it doesn't exist."""
    ref = await store.save(
        agent_id="new_agent",
        source_path=source_file,
        extension="ogg",
        original_filename="test.ogg",
        content_type="audio/ogg",
    )

    agent_dir = os.path.join(store._base_path, "new_agent")
    assert os.path.isdir(agent_dir)
    assert os.path.exists(store.resolve(ref.relative_path))


@pytest.mark.asyncio
async def test_save_returns_relative_path(store: MediaFileStore, source_file: str):
    """MediaRef.relative_path is {agent_id}/{uuid}.{ext}."""
    ref = await store.save(
        agent_id="agent1",
        source_path=source_file,
        extension="ogg",
        original_filename="original.wav",
        content_type="audio/wav",
    )

    assert isinstance(ref, MediaRef)
    assert ref.relative_path.startswith("agent1/")
    assert ref.relative_path.endswith(".ogg")
    # Should contain a UUID-like segment
    parts = ref.relative_path.split("/")
    assert len(parts) == 2
    assert len(parts[1]) > 10  # uuid + .ogg


@pytest.mark.asyncio
async def test_save_populates_media_ref_fields(store: MediaFileStore, source_file: str):
    """MediaRef fields are correctly populated."""
    ref = await store.save(
        agent_id="agent1",
        source_path=source_file,
        extension="ogg",
        original_filename="meeting.wav",
        content_type="audio/wav",
        duration_seconds=42.5,
    )

    assert ref.original_filename == "meeting.wav"
    assert ref.content_type == "audio/wav"
    assert ref.compressed_size == 256  # We wrote 256 bytes
    assert ref.duration_seconds == 42.5


@pytest.mark.asyncio
async def test_resolve_returns_absolute(store: MediaFileStore):
    """resolve() joins base path with relative path."""
    resolved = store.resolve("agent1/abc123.ogg")

    assert os.path.isabs(resolved)
    assert resolved.endswith("agent1/abc123.ogg")
    assert resolved.startswith(store._base_path)


@pytest.mark.asyncio
async def test_delete_removes_file(store: MediaFileStore, source_file: str):
    """delete() removes the stored file and returns True."""
    ref = await store.save(
        agent_id="agent1",
        source_path=source_file,
        extension="ogg",
        original_filename="test.ogg",
        content_type="audio/ogg",
    )

    resolved = store.resolve(ref.relative_path)
    assert os.path.exists(resolved)

    result = await store.delete(ref.relative_path)

    assert result is True
    assert not os.path.exists(resolved)


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_false(store: MediaFileStore):
    """delete() returns False for a file that doesn't exist."""
    result = await store.delete("agent1/nonexistent.ogg")
    assert result is False
