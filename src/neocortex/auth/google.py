from fastmcp.server.auth import AuthProvider
from fastmcp.server.auth.providers.google import GoogleProvider

from neocortex.mcp_settings import MCPSettings


def create_google_auth(settings: MCPSettings) -> AuthProvider:
    """Create a Google auth provider for FastMCP."""
    return GoogleProvider(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        base_url=settings.oauth_base_url,
    )
