from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from neocortex.auth.tokens import load_token_map
from neocortex.mcp_settings import MCPSettings

_bearer_scheme = HTTPBearer(auto_error=False)


def _get_settings(request: Request) -> MCPSettings:
    return request.app.state.settings


async def get_agent_id(
    request: Request,
    settings: Annotated[MCPSettings, Depends(_get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
) -> str:
    """Resolve a bearer token to an agent ID.

    Returns ``"anonymous"`` when ``auth_mode="none"``.
    Raises ``HTTPException(401)`` for invalid or missing tokens.
    """
    if settings.auth_mode == "none":
        return "anonymous"

    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization token")

    token_map = load_token_map(settings)
    agent_id = token_map.get(credentials.credentials)
    if agent_id is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    return agent_id
