import json
from pathlib import Path

from fastmcp.server.auth import AccessToken, AuthProvider

from neocortex.mcp_settings import MCPSettings


class DevTokenAuth(AuthProvider):
    """JSON-backed bearer-token auth for development and agent testing."""

    def __init__(self, settings: MCPSettings):
        super().__init__(base_url=settings.oauth_base_url)
        self._token_map: dict[str, str] = {}

        if settings.dev_tokens_file:
            tokens_path = Path(settings.dev_tokens_file)
            if tokens_path.exists():
                raw_value = json.loads(tokens_path.read_text())
                if isinstance(raw_value, dict):
                    self._token_map = {str(token): str(agent_id) for token, agent_id in raw_value.items()}

        if not self._token_map:
            self._token_map = {settings.dev_token: settings.dev_user_id}

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
