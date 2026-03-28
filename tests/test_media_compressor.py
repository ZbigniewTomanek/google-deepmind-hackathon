import os
import shutil
import struct
import wave

import pytest

from neocortex.ingestion.media_compressor import CompressedMedia, MediaCompressor

HAS_FFMPEG = shutil.which("ffmpeg") is not None


@pytest.fixture
def compressor() -> MediaCompressor:
    return MediaCompressor()


@pytest.fixture
def wav_file(tmp_path) -> str:
    """Generate a 1-second mono WAV file (silence)."""
    path = str(tmp_path / "test.wav")
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(struct.pack("<" + "h" * 16000, *([0] * 16000)))
    return path


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
@pytest.mark.asyncio
async def test_compress_audio(compressor: MediaCompressor, wav_file: str, tmp_path):
    """Compressing a WAV to opus/ogg should produce a smaller file."""
    original_size = os.path.getsize(wav_file)
    output_path = str(tmp_path / "compressed.ogg")

    result = await compressor.compress_audio(wav_file, output_path)

    assert isinstance(result, CompressedMedia)
    assert result.path == output_path
    assert result.path.endswith(".ogg")
    assert os.path.exists(result.path)
    assert result.size_bytes > 0
    assert result.size_bytes < original_size
    assert result.mime_type == "audio/ogg"
    assert result.duration_seconds > 0


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
@pytest.mark.asyncio
async def test_compress_audio_appends_extension(compressor: MediaCompressor, wav_file: str, tmp_path):
    """If output_path doesn't end with .ogg, the extension is appended."""
    output_path = str(tmp_path / "compressed")

    result = await compressor.compress_audio(wav_file, output_path)

    assert result.path.endswith(".ogg")
    assert os.path.exists(result.path)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
@pytest.mark.asyncio
async def test_probe_duration(compressor: MediaCompressor, wav_file: str):
    """Duration of a 1-second WAV should be approximately 1 second."""
    duration = await compressor.probe_duration(wav_file)

    assert 0.9 <= duration <= 1.1


@pytest.mark.asyncio
async def test_compress_audio_without_ffmpeg(tmp_path):
    """Compressor should raise RuntimeError when ffmpeg is not found."""
    compressor = MediaCompressor()
    # Force ffmpeg to appear unavailable
    compressor._ffmpeg = None

    with pytest.raises(RuntimeError, match="ffmpeg is not installed"):
        await compressor.compress_audio(
            str(tmp_path / "fake.wav"),
            str(tmp_path / "output.ogg"),
        )


@pytest.mark.asyncio
async def test_probe_duration_without_ffprobe(tmp_path):
    """Compressor should raise RuntimeError when ffprobe is not found."""
    compressor = MediaCompressor()
    compressor._ffprobe = None

    with pytest.raises(RuntimeError, match="ffprobe is not installed"):
        await compressor.probe_duration(str(tmp_path / "fake.wav"))


def test_available_property():
    """available property should reflect ffmpeg presence."""
    compressor = MediaCompressor()
    # Reflects actual system state
    assert compressor.available == HAS_FFMPEG

    # Force unavailable
    compressor._ffmpeg = None
    assert compressor.available is False
