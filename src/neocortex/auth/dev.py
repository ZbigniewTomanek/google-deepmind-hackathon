from fastmcp.server.auth import AccessToken, AuthProvider

from neocortex.auth.tokens import load_token_map
from neocortex.mcp_settings import MCPSettings


class DevTokenAuth(AuthProvider):
    """JSON-backed bearer-token auth for development and agent testing."""

    def __init__(self, settings: MCPSettings):
        super().__init__(base_url=settings.oauth_base_url)
        self._token_map: dict[str, str] = load_token_map(settings)

    async def verify_token(self, token: str) -> AccessToken | None:
        agent_id = self._token_map.get(token)
        if agent_id is None:
            return None

        return AccessToken(
            token=token,
            client_id="neocortex-dev-client",
            scopes=["openid"],
            claims={"sub": agent_id},
        )
