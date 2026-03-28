"""Integration test for Gemini media description.

Gated behind GOOGLE_API_KEY env var. Verifies a real Gemini API call
with a tiny audio file returns a non-empty description.
"""

import os
import struct
import wave

import pytest

from neocortex.ingestion.media_description import MediaDescription, MediaDescriptionService

HAS_API_KEY = bool(os.environ.get("GOOGLE_API_KEY"))


@pytest.fixture
def wav_file(tmp_path) -> str:
    """Generate a 1-second mono WAV file (silence)."""
    path = str(tmp_path / "integration_test.wav")
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(struct.pack("<" + "h" * 16000, *([0] * 16000)))
    return path


@pytest.mark.skipif(not HAS_API_KEY, reason="No GOOGLE_API_KEY")
@pytest.mark.asyncio
async def test_gemini_audio_description(wav_file: str):
    """Upload a tiny audio file and verify Gemini returns a non-empty description."""
    service = MediaDescriptionService(
        api_key=os.environ["GOOGLE_API_KEY"],
        model="gemini-2.0-flash",
    )

    result = await service.describe_audio(wav_file, "audio/wav")

    assert isinstance(result, MediaDescription)
    assert len(result.text) > 0
    assert result.model == "gemini-2.0-flash"
