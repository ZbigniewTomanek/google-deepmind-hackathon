from __future__ import annotations

from fastmcp import Context
from fastmcp.server.dependencies import get_access_token

from neocortex.mcp_settings import MCPSettings


def get_agent_id_from_context(ctx: Context) -> str:
    """Extract the current agent identity from the FastMCP context."""
    settings = ctx.lifespan_context.get("settings")
    if isinstance(settings, MCPSettings):
        if settings.auth_mode == "none":
            return "anonymous"
        if settings.auth_mode == "dev_token":
            token = get_access_token()
            if token is None:
                return settings.dev_user_id
            return str(token.claims.get("sub", settings.dev_user_id))
        if settings.auth_mode == "auth0":
            token = get_access_token()
            if token is None:
                return "anonymous"
            sub = token.claims.get("sub")
            if sub:
                # Auth0 sub format: "auth0|abc123" or "google-oauth2|123"
                # Use the full sub as agent_id for uniqueness
                return str(sub)
            return "anonymous"

    token = get_access_token()
    if token is not None:
        subject = token.claims.get("sub")
        if subject:
            return str(subject)

    return "anonymous"


async def ensure_provisioned(ctx: Context, agent_id: str) -> None:
    """Auto-provision agent on first access (Auth0 mode only)."""
    settings = ctx.lifespan_context.get("settings")
    if not isinstance(settings, MCPSettings) or settings.auth_mode != "auth0":
        return
    permissions = ctx.lifespan_context.get("permissions")
    if permissions is None:
        return

    from neocortex.auth.provisioning import ensure_agent_provisioned

    token = get_access_token()
    auth0_perms = token.claims.get("permissions", []) if token else None
    await ensure_agent_provisioned(
        permissions=permissions,
        agent_id=agent_id,
        auth0_permissions=auth0_perms,
    )
