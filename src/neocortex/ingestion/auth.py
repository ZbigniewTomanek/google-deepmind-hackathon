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

    # Auth0 mode: validate JWT
    if settings.auth_mode == "auth0":
        verifier = request.app.state.auth0_verifier
        try:
            claims = verifier.verify(credentials.credentials)
            sub = claims.get("sub")
            if not sub:
                raise HTTPException(status_code=401, detail="Token missing sub claim")
            agent_id = str(sub)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc

        # Auto-provision Auth0 identity into permission system
        from neocortex.auth.provisioning import ensure_agent_provisioned

        permissions = request.app.state.permissions
        auth0_perms = claims.get("permissions", [])
        await ensure_agent_provisioned(
            permissions=permissions,
            agent_id=agent_id,
            auth0_permissions=auth0_perms,
        )
        return agent_id

    # Dev-token mode: static lookup
    token_map: dict[str, str] = request.app.state.token_map
    agent_id = token_map.get(credentials.credentials)
    if agent_id is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    return agent_id


def get_auth0_permissions(request: Request, credentials: HTTPAuthorizationCredentials) -> list[str]:
    """Extract Auth0 permissions from the JWT. Returns empty list for non-auth0 modes."""
    settings: MCPSettings = request.app.state.settings
    if settings.auth_mode != "auth0":
        return []
    verifier = request.app.state.auth0_verifier
    try:
        claims = verifier.verify(credentials.credentials)
        return claims.get("permissions", [])
    except Exception:
        return []
