from __future__ import annotations

import asyncio
import os
import shutil

from neocortex.ingestion.media_compressor import CompressedMedia


class MockMediaCompressor:
    """Mock compressor that copies files without requiring ffmpeg.

    Used in mock/test mode to exercise the full media pipeline without
    needing ffmpeg installed.
    """

    @property
    def available(self) -> bool:
        return True

    async def compress_audio(self, input_path: str, output_path: str) -> CompressedMedia:
        if not output_path.endswith(".ogg"):
            output_path = output_path + ".ogg"
        await asyncio.to_thread(shutil.copy2, input_path, output_path)
        size = os.path.getsize(output_path)
        return CompressedMedia(
            path=output_path,
            size_bytes=size,
            duration_seconds=1.0,
            mime_type="audio/ogg",
        )

    async def compress_video(self, input_path: str, output_path: str) -> CompressedMedia:
        if not output_path.endswith(".mp4"):
            output_path = output_path + ".mp4"
        await asyncio.to_thread(shutil.copy2, input_path, output_path)
        size = os.path.getsize(output_path)
        return CompressedMedia(
            path=output_path,
            size_bytes=size,
            duration_seconds=2.5,
            mime_type="video/mp4",
        )

    async def probe_duration(self, path: str) -> float:
        return 1.0
