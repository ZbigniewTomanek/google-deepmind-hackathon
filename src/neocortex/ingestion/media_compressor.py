import asyncio
import os
import shutil
from dataclasses import dataclass

from loguru import logger


@dataclass
class CompressedMedia:
    path: str
    size_bytes: int
    duration_seconds: float
    mime_type: str


class MediaCompressor:
    """Compresses audio/video files via ffmpeg for storage and Gemini upload.

    Audio: re-encode to 64kbps mono opus in ogg container
    Video: re-encode to 480p, CRF 30, h264, 64kbps mono audio, mp4 container
    """

    def __init__(self) -> None:
        self._ffmpeg = shutil.which("ffmpeg")
        self._ffprobe = shutil.which("ffprobe")
        if not self._ffmpeg:
            logger.warning("ffmpeg not found on PATH — audio/video compression unavailable")
        if not self._ffprobe:
            logger.warning("ffprobe not found on PATH — duration probing unavailable")

    @property
    def available(self) -> bool:
        """True if ffmpeg is installed and usable."""
        return self._ffmpeg is not None

    async def compress_audio(self, input_path: str, output_path: str) -> CompressedMedia:
        """Compress audio to 64kbps mono opus in ogg container."""
        if not self._ffmpeg:
            raise RuntimeError("ffmpeg is not installed")

        # Ensure output has .ogg extension
        if not output_path.endswith(".ogg"):
            output_path = output_path + ".ogg"

        await self._run_ffmpeg(
            [
                self._ffmpeg,
                "-y",
                "-i",
                input_path,
                "-ac",
                "1",
                "-b:a",
                "64k",
                "-c:a",
                "libopus",
                output_path,
            ]
        )

        duration = await self.probe_duration(output_path)
        size = os.path.getsize(output_path)

        return CompressedMedia(
            path=output_path,
            size_bytes=size,
            duration_seconds=duration,
            mime_type="audio/ogg",
        )

    async def compress_video(self, input_path: str, output_path: str) -> CompressedMedia:
        """Compress video to 480p CRF-30 h264 with 64kbps mono audio in mp4 container."""
        if not self._ffmpeg:
            raise RuntimeError("ffmpeg is not installed")

        # Ensure output has .mp4 extension
        if not output_path.endswith(".mp4"):
            output_path = output_path + ".mp4"

        await self._run_ffmpeg(
            [
                self._ffmpeg,
                "-y",
                "-i",
                input_path,
                "-vf",
                "scale=-2:480",
                "-c:v",
                "libx264",
                "-crf",
                "30",
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                "-ac",
                "1",
                output_path,
            ]
        )

        duration = await self.probe_duration(output_path)
        size = os.path.getsize(output_path)

        return CompressedMedia(
            path=output_path,
            size_bytes=size,
            duration_seconds=duration,
            mime_type="video/mp4",
        )

    async def probe_duration(self, path: str) -> float:
        """Extract duration in seconds from a media file using ffprobe."""
        if not self._ffprobe:
            raise RuntimeError("ffprobe is not installed")

        proc = await asyncio.create_subprocess_exec(
            self._ffprobe,
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {stderr.decode().strip()}")

        try:
            return float(stdout.decode().strip())
        except ValueError:
            logger.warning("Could not parse duration from ffprobe output: {}", stdout.decode())
            return 0.0

    @staticmethod
    async def _run_ffmpeg(args: list[str]) -> asyncio.subprocess.Process:
        """Run an ffmpeg command and raise on failure."""
        logger.debug("Running ffmpeg: {}", " ".join(args))

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg exited with code {proc.returncode}: {stderr.decode().strip()}")

        return proc
