from fastmcp.server.auth import AccessToken, AuthProvider

from neocortex.mcp_settings import MCPSettings


class DevTokenAuth(AuthProvider):
    """Static bearer-token auth for development and agent testing."""

    def __init__(self, settings: MCPSettings):
        super().__init__(base_url=settings.oauth_base_url)
        self._token = settings.dev_token
        self._user_id = settings.dev_user_id

    async def verify_token(self, token: str) -> AccessToken | None:
        if token != self._token:
            return None

        return AccessToken(
            token=token,
            client_id="neocortex-dev-client",
            scopes=["openid"],
            claims={"sub": self._user_id},
        )
