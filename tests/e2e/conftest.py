import struct
import subprocess
import wave

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
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=black:s=160x120:d=1",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=16000:cl=mono",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-crf",
            "51",
            "-c:a",
            "aac",
            "-b:a",
            "32k",
            "-shortest",
            path,
        ],
        check=True,
        capture_output=True,
    )
    return path


@pytest.fixture(scope="session")
def oversized_bytes() -> bytes:
    """Return bytes just over the 100 MB limit for size-rejection tests."""
    return b"\x00" * (100 * 1024 * 1024 + 1)
