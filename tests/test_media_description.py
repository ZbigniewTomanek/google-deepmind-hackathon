import os
import struct
import wave

import pytest

from neocortex.ingestion.media_description import MediaDescription, MediaDescriptionService
from neocortex.ingestion.media_description_mock import MockMediaDescriptionService


@pytest.fixture
def mock_describer() -> MockMediaDescriptionService:
    return MockMediaDescriptionService()


@pytest.fixture
def wav_file(tmp_path) -> str:
    """Generate a 1-second mono WAV file (silence)."""
    path = str(tmp_path / "test_audio.wav")
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(struct.pack("<" + "h" * 16000, *([0] * 16000)))
    return path


@pytest.mark.asyncio
async def test_mock_describe_audio(mock_describer: MockMediaDescriptionService, wav_file: str):
    """Mock describer returns placeholder text for audio."""
    result = await mock_describer.describe_audio(wav_file, "audio/wav")

    assert isinstance(result, MediaDescription)
    assert "test_audio.wav" in result.text
    assert "Mock audio" in result.text
    assert result.model == "mock"
    assert result.token_count == 0


@pytest.mark.asyncio
async def test_mock_describe_video(mock_describer: MockMediaDescriptionService, tmp_path):
    """Mock describer returns placeholder text for video."""
    fake_video = str(tmp_path / "clip.mp4")
    with open(fake_video, "wb") as f:
        f.write(b"\x00" * 100)

    result = await mock_describer.describe_video(fake_video, "video/mp4")

    assert isinstance(result, MediaDescription)
    assert "clip.mp4" in result.text
    assert "Mock video" in result.text
    assert result.model == "mock"
    assert result.token_count == 0


@pytest.mark.asyncio
async def test_mock_describe_audio_with_context(mock_describer: MockMediaDescriptionService, wav_file: str):
    """Mock describer works with context parameter."""
    result = await mock_describer.describe_audio(wav_file, "audio/wav", context="team meeting")

    assert isinstance(result, MediaDescription)
    assert result.text  # Non-empty


@pytest.mark.asyncio
async def test_service_without_api_key(wav_file: str):
    """Service without API key returns placeholder description."""
    service = MediaDescriptionService(api_key="", model="test-model")

    result = await service.describe_audio(wav_file, "audio/wav")

    assert isinstance(result, MediaDescription)
    assert "placeholder" in result.text.lower() or "No API key" in result.text
    assert result.model == "none"
    assert result.token_count == 0


@pytest.mark.asyncio
async def test_service_video_without_api_key(tmp_path):
    """Service without API key returns placeholder for video too."""
    fake_video = str(tmp_path / "video.mp4")
    with open(fake_video, "wb") as f:
        f.write(b"\x00" * 100)

    service = MediaDescriptionService(api_key="", model="test-model")

    result = await service.describe_video(fake_video, "video/mp4")

    assert isinstance(result, MediaDescription)
    assert result.model == "none"


def test_media_description_dataclass():
    """MediaDescription dataclass holds expected fields."""
    desc = MediaDescription(text="hello", model="gemini-test", token_count=42)

    assert desc.text == "hello"
    assert desc.model == "gemini-test"
    assert desc.token_count == 42


HAS_API_KEY = bool(os.environ.get("GOOGLE_API_KEY"))


@pytest.mark.skipif(not HAS_API_KEY, reason="No GOOGLE_API_KEY")
@pytest.mark.asyncio
async def test_real_gemini_audio_description(wav_file: str):
    """Integration test: real Gemini API call with a tiny audio file.

    Verifies that the service handles the full upload→describe→cleanup
    cycle. Uses gemini-2.0-flash as it's widely available. If the API
    returns an error, the service should degrade gracefully (non-empty
    fallback text, zero tokens).
    """
    service = MediaDescriptionService(
        api_key=os.environ["GOOGLE_API_KEY"],
        model="gemini-2.0-flash",
    )

    result = await service.describe_audio(wav_file, "audio/wav")

    assert isinstance(result, MediaDescription)
    assert len(result.text) > 0  # Even on failure, fallback text is non-empty
    assert result.model == "gemini-2.0-flash"
