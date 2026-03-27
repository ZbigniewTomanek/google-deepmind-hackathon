from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from neocortex.mcp_settings import MCPSettings

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_agent_id(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
) -> str:
    """Resolve a bearer token to an agent ID.

    Returns ``"anonymous"`` when ``auth_mode="none"``.
    Raises ``HTTPException(401)`` for invalid or missing tokens.

    The token map is loaded once at startup and cached in ``app.state.token_map``.
    """
    settings: MCPSettings = request.app.state.settings

    if settings.auth_mode == "none":
        return "anonymous"

    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization token")

    token_map: dict[str, str] = request.app.state.token_map
    agent_id = token_map.get(credentials.credentials)
    if agent_id is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    return agent_id
