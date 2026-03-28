import asyncio
import os
import shutil
import uuid

from neocortex.ingestion.media_models import MediaRef


class MediaFileStore:
    """Persists compressed media files on the local filesystem.

    Directory layout: {base_path}/{agent_id}/{uuid}.{ext}
    All returned paths in MediaRef are relative to base_path.
    """

    def __init__(self, base_path: str) -> None:
        self._base_path = base_path

    async def save(
        self,
        agent_id: str,
        source_path: str,
        extension: str,
        original_filename: str,
        content_type: str,
        duration_seconds: float | None = None,
    ) -> MediaRef:
        """Move a file into the store and return a MediaRef."""
        agent_dir = os.path.join(self._base_path, agent_id)
        os.makedirs(agent_dir, exist_ok=True)

        file_id = str(uuid.uuid4())
        dest_filename = f"{file_id}.{extension}"
        dest_path = os.path.join(agent_dir, dest_filename)

        # Move file into the store (offload blocking I/O)
        await asyncio.to_thread(shutil.move, source_path, dest_path)

        file_size = os.path.getsize(dest_path)
        relative_path = f"{agent_id}/{dest_filename}"

        return MediaRef(
            relative_path=relative_path,
            original_filename=original_filename,
            content_type=content_type,
            compressed_size=file_size,
            duration_seconds=duration_seconds,
        )

    def resolve(self, relative_path: str) -> str:
        """Return absolute path for a relative media reference."""
        resolved = os.path.normpath(os.path.join(self._base_path, relative_path))
        if not resolved.startswith(os.path.normpath(self._base_path) + os.sep) and resolved != os.path.normpath(
            self._base_path
        ):
            raise ValueError(f"Path traversal detected: {relative_path}")
        return resolved

    async def delete(self, relative_path: str) -> bool:
        """Remove a file from the store. Returns True if deleted, False if not found."""
        abs_path = self.resolve(relative_path)
        try:
            await asyncio.to_thread(os.remove, abs_path)
            return True
        except FileNotFoundError:
            return False
