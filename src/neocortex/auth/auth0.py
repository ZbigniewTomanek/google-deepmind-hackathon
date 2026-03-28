"""Auth0 OAuth provider for NeoCortex MCP server."""

from fastmcp.server.auth import AuthProvider
from fastmcp.server.auth.providers.auth0 import Auth0Provider

from neocortex.mcp_settings import MCPSettings


def create_auth0_auth(settings: MCPSettings) -> AuthProvider:
    """Create an Auth0 provider for FastMCP.

    Uses FastMCP's built-in Auth0Provider which handles:
    - OIDC discovery from Auth0's well-known config
    - JWT token verification via Auth0's JWKS endpoint
    - OAuth authorization flow proxy
    """
    if not settings.auth0_domain:
        raise ValueError("NEOCORTEX_AUTH0_DOMAIN is required for auth0 mode")
    if not settings.auth0_client_id:
        raise ValueError("NEOCORTEX_AUTH0_CLIENT_ID is required for auth0 mode")
    if not settings.auth0_client_secret:
        raise ValueError("NEOCORTEX_AUTH0_CLIENT_SECRET is required for auth0 mode")
    if not settings.auth0_audience:
        raise ValueError("NEOCORTEX_AUTH0_AUDIENCE is required for auth0 mode")

    config_url = f"https://{settings.auth0_domain}/.well-known/openid-configuration"

    return Auth0Provider(
        config_url=config_url,
        client_id=settings.auth0_client_id,
        client_secret=settings.auth0_client_secret,
        audience=settings.auth0_audience,
        base_url=settings.oauth_base_url,
        required_scopes=["openid", "profile", "email"],
    )
