from __future__ import annotations

from pathlib import Path

from neocortex.ingestion.media_description import MediaDescription


class MockMediaDescriptionService:
    """Returns placeholder descriptions for mock/test mode."""

    async def describe_audio(self, file_path: str, mime_type: str, context: str = "") -> MediaDescription:
        return MediaDescription(
            text=f"[Mock audio description for {Path(file_path).name}]",
            model="mock",
            token_count=0,
        )

    async def describe_video(self, file_path: str, mime_type: str, context: str = "") -> MediaDescription:
        return MediaDescription(
            text=f"[Mock video description for {Path(file_path).name}]",
            model="mock",
            token_count=0,
        )
