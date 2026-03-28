from fastmcp.server.auth import AuthProvider

from neocortex.mcp_settings import MCPSettings


def create_auth(settings: MCPSettings) -> AuthProvider | None:
    """Create an auth provider for the configured auth mode."""
    if settings.auth_mode == "none":
        return None
    if settings.auth_mode == "dev_token":
        from neocortex.auth.dev import DevTokenAuth

        return DevTokenAuth(settings)
    if settings.auth_mode == "google_oauth":
        from neocortex.auth.google import create_google_auth

        return create_google_auth(settings)
    if settings.auth_mode == "auth0":
        from neocortex.auth.auth0 import create_auth0_auth

        return create_auth0_auth(settings)
    raise ValueError(
        f"Unknown auth_mode: {settings.auth_mode!r}. " "Use 'none', 'dev_token', 'google_oauth', or 'auth0'."
    )
