from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile

from neocortex.ingestion.auth import get_agent_id
from neocortex.ingestion.models import EventsIngestionRequest, IngestionResult, TextIngestionRequest

router = APIRouter(prefix="/ingest", tags=["ingestion"])

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
_ACCEPTED_CONTENT_TYPES = {
    "text/plain",
    "application/json",
    "text/markdown",
    "text/csv",
}


@router.post("/text", response_model=IngestionResult)
async def ingest_text(
    body: TextIngestionRequest,
    request: Request,
    agent_id: Annotated[str, Depends(get_agent_id)],
) -> IngestionResult:
    processor = request.app.state.processor
    return await processor.process_text(agent_id, body.text, body.metadata)


@router.post("/document", response_model=IngestionResult)
async def ingest_document(
    file: UploadFile,
    request: Request,
    agent_id: Annotated[str, Depends(get_agent_id)],
    metadata: str | None = None,
) -> IngestionResult:
    # Validate content type
    content_type = file.content_type or "application/octet-stream"
    if content_type not in _ACCEPTED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported content type '{content_type}'. Accepted: {', '.join(sorted(_ACCEPTED_CONTENT_TYPES))}",
        )

    # Read and validate size
    content_bytes = await file.read()
    if len(content_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum upload size of {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )

    parsed_metadata: dict = {}
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid metadata JSON: {exc}") from exc

    processor = request.app.state.processor
    return await processor.process_document(
        agent_id, file.filename or "unknown", content_bytes, content_type, parsed_metadata
    )


@router.post("/events", response_model=IngestionResult)
async def ingest_events(
    body: EventsIngestionRequest,
    request: Request,
    agent_id: Annotated[str, Depends(get_agent_id)],
) -> IngestionResult:
    processor = request.app.state.processor
    return await processor.process_events(agent_id, body.events, body.metadata)
