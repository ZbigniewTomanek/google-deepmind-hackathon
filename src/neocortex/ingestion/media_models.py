from pydantic import BaseModel

from neocortex.ingestion.models import IngestionResult


class MediaRef(BaseModel):
    """Reference to a stored media file on the filesystem."""

    relative_path: str  # Path relative to media store root ({agent_id}/{uuid}.{ext})
    original_filename: str  # Original upload filename
    content_type: str  # MIME type of original upload
    compressed_size: int  # Size in bytes after compression
    duration_seconds: float | None = None  # Duration if available


class MediaIngestionResult(IngestionResult):
    """Extended result for media ingestion — inherits status/episodes_created/message."""

    media_ref: MediaRef | None = None  # Reference to stored media
