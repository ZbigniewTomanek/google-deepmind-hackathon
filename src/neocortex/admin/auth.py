from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from neocortex.ingestion.auth import get_agent_id


async def require_admin(
    request: Request,
    agent_id: Annotated[str, Depends(get_agent_id)],
) -> str:
    """Dependency that ensures the caller is an admin. Returns agent_id."""
    permissions = request.app.state.permissions
    if not await permissions.is_admin(agent_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    return agent_id
